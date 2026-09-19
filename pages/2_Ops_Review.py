import json
import streamlit as st
from dotenv import load_dotenv

from core.db import init_db, list_claims, get_claim, update_decision

load_dotenv()
init_db()
st.set_page_config(page_title="Ops Review", page_icon="🧑‍💼", layout="wide")

st.title("🧑‍💼 Ops Review Dashboard")
st.caption("Human-in-the-loop: every claim requires an operator decision, regardless of the AI recommendation.")

status_filter = st.selectbox(
    "Filter by status", ["ALL", "PENDING", "APPROVED", "REJECTED", "REQUEST_INFO"]
)
claims = list_claims(status=status_filter)

if not claims:
    st.info("No claims match this filter yet. Submit one from the 'Submit Claim' page.")
    st.stop()

st.subheader(f"Claims ({len(claims)})")
table_rows = [
    {
        "Claim ID": c["claim_id"],
        "Customer": c["customer_name"],
        "Policy #": c["policy_number"],
        "Flight": c["flight_number"],
        "AI Recommendation": c["ai_recommendation"],
        "Ops Decision": c["ops_decision"],
        "Submitted": c["created_at"][:19],
    }
    for c in claims
]
st.dataframe(table_rows, use_container_width=True, hide_index=True)

st.divider()
selected_id = st.selectbox("Select a claim to review in detail", [c["claim_id"] for c in claims])
claim = get_claim(selected_id)

extracted = json.loads(claim["extracted_json"])
assessment = json.loads(claim["assessment_json"])
documents = json.loads(claim["documents_json"])

# --- Summary -------------------------------------------------------------
st.markdown(f"## Claim {claim['claim_id']}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Customer", claim["customer_name"] or "—")
c2.metric("Policy #", claim["policy_number"] or "—")
c3.metric("Flight", claim["flight_number"] or "—")
c4.metric("Ops Decision", claim["ops_decision"])

badge = {"APPROVE": "🟢", "REJECT": "🔴", "REQUEST_INFO": "🟡"}.get(claim["ai_recommendation"], "⚪")
st.markdown(f"### {badge} AI Recommendation: **{claim['ai_recommendation']}**")
st.write(claim["recommendation_reason"])
if assessment.get("duplicate_warning"):
    st.warning(assessment["duplicate_warning"])

# --- Extraction results ----------------------------------------------------
with st.expander("📄 Extracted data (structured)", expanded=True):
    st.caption(f"Extraction source: **{extracted.get('source')}**")
    field_cols = st.columns(2)
    fields = [
        ("Customer name", extracted.get("customer_name")),
        ("Policy number", extracted.get("policy_number")),
        ("Flight number", extracted.get("flight_number")),
        ("Airline", extracted.get("airline")),
        ("Claim type", extracted.get("claim_type")),
        ("Delay (hours)", extracted.get("delay_hours")),
        ("Scheduled departure", extracted.get("scheduled_departure")),
        ("Actual departure", extracted.get("actual_departure")),
        ("Delay reason", extracted.get("delay_reason")),
        ("Return to Singapore date", extracted.get("return_to_singapore_date")),
    ]
    for i, (label, value) in enumerate(fields):
        field_cols[i % 2].write(f"**{label}:** {value if value is not None else '—'}")
    if extracted.get("extraction_notes"):
        st.caption("Notes: " + "; ".join(extracted["extraction_notes"]))

# --- Reasoning ---------------------------------------------------------
with st.expander("🧠 Reasoning / justification", expanded=True):
    st.write("**Policy conditions:**")
    for reason in assessment.get("policy_reasons", []):
        st.write(f"- {reason}")

    st.write(f"**Documents complete:** {'✅' if assessment.get('documents_complete') else '❌'}")
    if assessment.get("missing_documents"):
        st.write("Missing: " + ", ".join(assessment["missing_documents"]))

    st.write(f"**Information consistent:** {'✅' if assessment.get('information_consistent') else '❌'}")
    for inc in assessment.get("inconsistencies", []):
        st.write(f"- {inc}")

# --- Original documents ----------------------------------------------------
with st.expander("📎 Original submitted documents"):
    doc_display = {
        "Claim form": documents.get("claim_form_text"),
        "Itinerary": documents.get("itinerary_text"),
        "Boarding pass": documents.get("boarding_pass_text"),
        "Delay letter": documents.get("delay_letter_text"),
    }
    for label, text in doc_display.items():
        st.write(f"**{label}**")
        st.text(text if text else "(not provided / unreadable)")
    if documents.get("unreadable_documents"):
        st.warning("Unreadable: " + ", ".join(documents["unreadable_documents"]))

# --- Action --------------------------------------------------------------
st.divider()
st.subheader("Ops decision")
notes = st.text_area("Notes (optional — required if overriding the AI recommendation)")
b1, b2, b3 = st.columns(3)
if b1.button("✅ Approve", use_container_width=True):
    update_decision(claim["claim_id"], "APPROVED", notes)
    st.rerun()
if b2.button("❌ Reject", use_container_width=True):
    update_decision(claim["claim_id"], "REJECTED", notes)
    st.rerun()
if b3.button("✉️ Request Information", use_container_width=True):
    update_decision(claim["claim_id"], "REQUEST_INFO", notes)
    st.rerun()

if claim["ops_decision"] != "PENDING":
    st.success(
        f"Decision recorded: **{claim['ops_decision']}** at {claim['decided_at']}"
        + (f" — Notes: {claim['ops_notes']}" if claim["ops_notes"] else "")
    )
