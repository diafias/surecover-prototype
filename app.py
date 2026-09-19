import streamlit as st
from dotenv import load_dotenv

from core.db import init_db, seed_policies
from core.policy_db import SEED_POLICIES

load_dotenv()
st.set_page_config(page_title="SureCover Claims AI", page_icon="🛫", layout="wide")

init_db()
seed_policies(SEED_POLICIES)

st.title("🛫 SureCover — AI-Assisted Flight Delay Claims")
st.caption("Prototype: document intake → AI extraction → policy rules → human-in-the-loop review")

st.markdown(
    """
Use the sidebar to navigate:

- **📥 Submit Claim** — simulates a customer emailing in a claim with attachments
- **🧑‍💼 Ops Review** — the operations dashboard where a human makes the final call

---

### How it works
"""
)

st.code(
    """
Customer submission (web form simulating an email + attachments)
        ↓
PDF text extraction — pdfplumber → Gemini native PDF read (fallback for scanned docs)
        ↓
AI structured extraction  — Gemini 3.6 Flash → Groq GPT-OSS 120B → rule-based fallback
        ↓
Deterministic Policy Rules (Python)
    • claim type covered?      • delay ≥ 3 hours?
    • within 30-day window?    • flight date within policy coverage period?
        ↓
Completeness & Consistency Check
    • all 4 required documents present & readable?
    • data consistent across documents?
    • policy number recognized?    • duplicate submission?
        ↓
AI Recommendation: APPROVE / REJECT / REQUEST_INFO  (+ reasons)
        ↓
🧑‍💼 Ops Review Dashboard → human decision (Approve / Reject / Request Info)
    """,
    language="text",
)

st.info(
    "Design principle: the LLM only ever does unstructured **document understanding**. "
    "Every eligibility decision (approve/reject/request info) is computed by deterministic "
    "Python rules, so the outcome is explainable and reproducible — the LLM is not asked "
    "'should this be approved?', only 'what does this document say?'"
)

with st.expander("Seeded dummy policies (for the coverage-period check)"):
    for p in SEED_POLICIES:
        st.write(
            f"**{p['policy_number']}** — {p['customer_name']} — "
            f"{p['product_type']} — valid {p['start_date']} to {p['end_date']}"
        )