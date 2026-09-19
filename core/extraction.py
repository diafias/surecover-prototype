"""
Document understanding layer.

Pipeline: PDF/text -> raw text -> structured ExtractedClaimData

Fallback chain (this is the bit worth highlighting in the presentation):
    1. Gemini (primary) - multimodal, cheap, fast
    2. Groq / GPT-OSS (secondary) - used if Gemini errors or rate-limits (429)
    3. Rule-based regex extraction (last resort) - guarantees the demo
       NEVER hard-fails just because an API quota ran out.

This mirrors a real production pattern: probabilistic extraction should
degrade gracefully, not take the whole pipeline down.
"""

from __future__ import annotations
import json
import os
import re
from typing import Optional

from core.models import ExtractedClaimData

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


# --------------------------------------------------------------------------
# PDF -> text
# --------------------------------------------------------------------------
def extract_text_from_pdf(file_bytes: bytes) -> Optional[str]:
    """Returns None if the PDF couldn't be read (scanned/corrupt/no text layer)."""
    if pdfplumber is None:
        return None
    try:
        import io
        text_chunks = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_chunks.append(t)
        text = "\n".join(text_chunks).strip()
        return text if text else None
    except Exception:
        return None


def gemini_pdf_to_text(file_bytes: bytes) -> Optional[str]:
    """
    Last-resort fallback for documents pdfplumber couldn't read (e.g. scanned
    images with no text layer). Sends the raw PDF to Gemini's multimodal
    endpoint and asks it to transcribe the readable content as plain text.

    This is deliberately kept OUT of the main extraction fallback chain
    (Gemini -> Groq -> rule-based) because it solves a different problem:
    pdfplumber failing at the text-layer stage, not the LLM provider being
    unavailable. It's a per-document repair step, tried once per document,
    before that document is given up on and flagged unreadable.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"),
                "Transcribe all readable text from this document as plain text. "
                "No commentary, just the transcription.",
            ],
        )
        text = (response.text or "").strip()
        return text if text else None
    except Exception as e:
        print(f"[extraction] Gemini native PDF read failed: {e}")
        return None


# --------------------------------------------------------------------------
# LLM prompt (shared across providers)
# --------------------------------------------------------------------------
EXTRACTION_PROMPT_TEMPLATE = """You are a document-understanding assistant for a travel insurance claims desk.
Extract the following fields from the claim documents below. Respond with ONLY a JSON object,
no markdown fences, no commentary. Use null for any field you cannot find.

Fields:
- customer_name (string)
- policy_number (string)
- flight_number (string)
- scheduled_departure (string, best-effort date/time as written)
- actual_departure (string, best-effort date/time as written)
- delay_hours (number, hours of delay - compute from scheduled vs actual if both present)
- delay_reason (string, e.g. "technical issue", "weather")
- claim_type (string, default "Flight Delay")
- return_to_singapore_date (string, if mentioned)
- airline (string)

DOCUMENTS:
---
{documents}
---

JSON:"""


def _build_prompt(documents_text: str) -> str:
    return EXTRACTION_PROMPT_TEMPLATE.format(documents=documents_text[:12000])


def _parse_json_response(raw: str) -> Optional[dict]:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # try to grab the first {...} blob
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
        return None


# --------------------------------------------------------------------------
# Provider 1: Gemini
# --------------------------------------------------------------------------
def _try_gemini(documents_text: str) -> Optional[dict]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=_build_prompt(documents_text),
        )
        return _parse_json_response(response.text)
    except Exception as e:
        print(f"[extraction] Gemini failed, falling back: {e}")
        return None


# --------------------------------------------------------------------------
# Provider 2: Groq (GPT-OSS)
# --------------------------------------------------------------------------
def _try_groq(documents_text: str) -> Optional[dict]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": _build_prompt(documents_text)}],
            temperature=0,
        )
        raw = completion.choices[0].message.content
        return _parse_json_response(raw)
    except Exception as e:
        print(f"[extraction] Groq failed, falling back: {e}")
        return None


# --------------------------------------------------------------------------
# Provider 3: rule-based fallback (regex) - guarantees the demo always works
# --------------------------------------------------------------------------
def _rule_based_extract(documents_text: str) -> dict:
    text = documents_text

    def find(pattern, default=None, flags=re.IGNORECASE):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else default

    flight_number = find(r"\b([A-Z]{2}\s?\d{2,4})\b", flags=0)
    policy_number = find(r"(?:policy\s*(?:no\.?|number)?[:\s]*)([A-Z0-9\-]{5,})")
    delay_hours_str = find(r"delay(?:ed)?\s*(?:of|for|by)?\s*([\d.]+)\s*hours?")
    customer_name = find(r"(?:name|customer)[:\s]+([A-Za-z .]{3,40})")

    scheduled_departure = find(r"Scheduled Departure:\s*([\d\-: ]{8,20})")
    actual_departure = find(r"Actual Departure:\s*([\d\-: ]{8,20})")
    return_date = find(r"Return to Singapore Date:\s*([\d\-]{8,12})")
    delay_reason = find(r"due to ([a-zA-Z ]{3,40})")

    return {
        "customer_name": customer_name,
        "policy_number": policy_number,
        "flight_number": flight_number,
        "scheduled_departure": scheduled_departure,
        "actual_departure": actual_departure,
        "delay_hours": float(delay_hours_str) if delay_hours_str else None,
        "delay_reason": delay_reason,
        "claim_type": "Flight Delay",
        "return_to_singapore_date": return_date,
        "airline": None,
    }


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def extract_claim_data(documents_text: str) -> ExtractedClaimData:
    """Runs the fallback chain and returns a validated ExtractedClaimData."""
    notes: list[str] = []

    data = _try_gemini(documents_text)
    source = "gemini"

    if data is None:
        notes.append("Gemini unavailable/rate-limited, used Groq fallback")
        data = _try_groq(documents_text)
        source = "groq"

    if data is None:
        notes.append("No LLM provider available, used rule-based extraction")
        data = _rule_based_extract(documents_text)
        source = "rule_based"

    data = dict(data or {})
    data["source"] = source
    data["extraction_notes"] = notes + list(data.get("extraction_notes", []))

    try:
        return ExtractedClaimData(**data)
    except Exception as e:
        notes.append(f"Validation error, some fields defaulted: {e}")
        return ExtractedClaimData(source=source, extraction_notes=notes)