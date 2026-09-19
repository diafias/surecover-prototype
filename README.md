# SureCover — AI-Assisted Flight Delay Claims (Prototype)

A working prototype for the SureCover technical test: claim intake → AI document
extraction → deterministic policy validation → completeness/consistency check →
human-in-the-loop ops review.

---

## 1. What you need to do (setup)

**Requirements:** Python 3.10+ installed on your machine.

```bash
# 1. Unzip and enter the project folder
cd surecover-prototype

# 2. (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up API keys (OPTIONAL — the app works without them)
cp .env.example .env
# Open .env and paste your GEMINI_API_KEY and/or GROQ_API_KEY
# If you leave both blank, extraction falls back to a rule-based
# regex extractor automatically — the app still runs end-to-end.

# 5. Run it
streamlit run app.py
```

Your browser opens automatically at `http://localhost:8501` with two pages in
the sidebar: **Submit Claim** and **Ops Review**.

**For the demo:** on the Submit Claim page, use the "Quick demo: load a sample
claim" dropdown — no need to prepare real PDFs. There are 3 canned scenarios
covering the three outcomes (APPROVE / REJECT / REQUEST_INFO).

A SQLite file (`data/surecover.db`) is created automatically on first run —
no database server to install. Delete this file any time to reset all data.

---

## 2. Architecture

```
Customer submission (web form simulating the claims@surecover.com.sg inbox)
        │
        ▼
PDF → text extraction (pdfplumber)
        │
        ▼
AI structured extraction
  Gemini 3.6 Flash (primary)
      → Groq GPT-OSS 120B (fallback on error/429)
          → rule-based regex (last-resort fallback)
        │
        ▼
Deterministic Policy Rules (plain Python)
  • claim type covered?
  • delay ≥ 3 hours?
  • submitted within 30-day claim window?
  • flight date within the policy's coverage period (dummy policy DB)?
        │
        ▼
Completeness & Consistency Check
  • all 4 required documents present & readable?
  • flight number / dates consistent across documents?
  • policy number recognized in our records?
  • duplicate claim (same policy + flight already submitted)?
        │
        ▼
AI Recommendation: APPROVE / REJECT / REQUEST_INFO (+ explicit reasons)
        │
        ▼
🧑‍💼 Ops Review Dashboard
  • claim summary, extracted data, AI reasoning, original documents
  • human decision: Approve / Reject / Request Information (mandatory)
```

### Key design decision: AI does NOT decide eligibility

The LLM is only ever asked "what does this document say?" (extraction).
Every eligibility rule (delay threshold, claim window, coverage period,
document completeness) is enforced by **deterministic Python code**, not by
asking the LLM to judge. This is the single most important architectural
point to make in the presentation:

> "I intentionally separate probabilistic AI tasks from deterministic
> business rules. The LLM handles unstructured document understanding,
> while policy eligibility is enforced through deterministic rules to
> improve reliability and explainability."

### Why the 3-provider fallback chain

Gemini free-tier quota can be rate-limited (429) — this happened during
development. Rather than risk the demo failing mid-presentation, extraction
degrades gracefully: Gemini → Groq → regex. The regex fallback is
deliberately weak (last resort only) but guarantees the pipeline never
hard-crashes just because an API quota ran out.

---

## 3. Business rules implemented (simplified policy structure)

| Rule | Value |
|---|---|
| Covered claim type | Flight Delay only |
| Minimum delay | ≥ 3 hours |
| Claim submission window | ≤ 30 days from return to Singapore |
| Coverage period | Flight date must fall within the policy's start/end date |
| Required documents | Claim form, itinerary, boarding pass, delay letter |
| Consistency check | Flight number must appear consistently across all documents |
| Duplicate check | Same policy number + flight number already submitted |

### Decision logic (in order — completeness is checked before eligibility)

1. **REQUEST_INFO** if any required document is missing/unreadable, any
   information is inconsistent across documents, the policy number isn't
   recognized, or it looks like a duplicate submission.
2. **REJECT** if documents are complete and consistent, but the claim fails
   a policy rule (wrong claim type, delay too short, outside claim window,
   or outside the policy's coverage period).
3. **APPROVE** if documents are complete, consistent, and all policy
   conditions are satisfied.

This ordering matters: a claim is never auto-rejected just because
information is missing — it's routed back for clarification instead.

A dummy policy master table (`core/policy_db.py`) seeds 3 policies so the
coverage-period rule has real data to check against — in production this
would be a live query to SureCover's policy admin system.

---

## 4. What happens on REQUEST_INFO (designed, partially implemented)

Fully implemented in this prototype:
1. Claim is flagged and appears in the Ops queue with status REQUEST_INFO
   and the specific reason (missing doc / inconsistency / unknown policy).
2. Ops reviews it manually (never auto-executed) and can override the AI.
3. Ops can record the decision with notes (audit trail).

Designed but out of scope for the 1-week build (mentioned in the
presentation as the production extension):
4. An outbound email (LLM-drafted, ops-approved) is sent to the customer
   listing exactly what's missing.
5. Claim status becomes `PENDING_CUSTOMER_RESPONSE` for SLA tracking.
6. Customer resubmits → pipeline re-runs automatically → new assessment,
   old assessment kept as audit history.
7. If no response within N days, the claim is auto-flagged as stale for
   ops follow-up.

---

## 5. Edge cases handled

- **Unreadable PDF** (scanned image, no text layer): flagged as
  `unreadable` rather than silently failing; treated as a missing document
  → routes to REQUEST_INFO.
- **Ambiguous / missing data** (e.g. delay duration not stated anywhere):
  never guessed by the LLM — treated as incomplete → REQUEST_INFO.
- **Unrecognized policy number**: routed to REQUEST_INFO (could be a typo),
  not an automatic REJECT.
- **Inconsistent flight numbers across documents**: flagged explicitly by
  name, so ops can see exactly which document disagrees.
- **Duplicate submissions**: detected via policy number + flight number
  match against existing claims.
- **LLM provider outage / rate limit**: automatic fallback chain, pipeline
  never hard-fails.

---

## 6. Scalability & risk — talking points for production

- **Intake**: replace the web form with a real email listener (IMAP polling
  or provider webhook) — the pipeline itself doesn't care how the raw
  documents arrived.
- **Multi-flight claims**: current MVP scopes to one flight; production
  needs to loop the same pipeline per affected flight and aggregate.
- **Database**: SQLite → Postgres, with proper migrations and concurrent
  write handling.
- **Auth & access control**: Ops dashboard needs real authentication and
  role-based access (currently open — fine for a local demo only).
- **PII / data protection**: claim documents contain personal data —
  production needs encryption at rest, access logging, and a retention
  policy, since this is regulated insurance data.
- **Workflow orchestration**: plain Python functions are enough for this
  linear pipeline; if branching/retry logic grows more complex (e.g.
  multi-step agent behaviour), LangGraph or a similar orchestrator becomes
  worth the added complexity — deliberately not used here to avoid
  over-engineering a 1-week prototype.
- **Model cost/quota at scale**: the free-tier fallback chain works for a
  prototype; production volume would need paid API tiers with proper rate
  limiting and monitoring, not just a fallback to a weaker free model.
- **Human accountability**: the AI never auto-executes a decision — this is
  non-negotiable both per the brief and for insurance regulatory reasons
  (an automated denial of a claim needs a human decision-maker of record).

---

## 7. Project structure

```
surecover-prototype/
├── app.py                    # Landing page / architecture overview
├── pages/
│   ├── 1_Submit_Claim.py     # Customer-facing intake form
│   └── 2_Ops_Review.py       # Ops dashboard: list + detail + decision
├── core/
│   ├── models.py             # Pydantic schemas (extraction, policy, assessment)
│   ├── extraction.py         # PDF text extraction + LLM fallback chain
│   ├── policy.py             # Deterministic policy rules + completeness check
│   ├── policy_db.py          # Dummy policy master data
│   ├── db.py                 # SQLite persistence
│   └── sample_data.py        # 3 canned demo scenarios
├── data/                     # SQLite DB created here at runtime
├── requirements.txt
└── .env.example
```
