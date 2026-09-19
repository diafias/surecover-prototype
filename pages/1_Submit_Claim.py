import streamlit as st
from dotenv import load_dotenv

from core.models import DocumentBundle
from core.extraction import extract_text_from_pdf, gemini_pdf_to_text, extract_claim_data
from core.policy import evaluate_policy, check_completeness, build_recommendation
from core.models import ClaimAssessment
from core.db import init_db, get_policy, find_duplicate, save_claim
from core.sample_data import SAMPLES

load_dotenv()
init_db()
st.set_page_config(page_title="Submit Claim", page_icon="📥", layout="wide")

st.title("📥 Submit a Flight Delay Claim")
st.caption(
    "This form simulates the claims@surecover.com.sg inbox. In production, this intake step "
    "would be an automated email listener; for this prototype, submission happens via this "
    "web form instead."
)

use_sample = st.selectbox(
    "Quick demo: load a sample claim (or choose 'None' to upload your own PDFs)",
    ["None"] + list(SAMPLES.keys()),
)

col1, col2 = st.columns(2)
with col1:
    customer_name_input = st.text_input("Customer name")
with col2:
    policy_number_input = st.text_input(
        "Policy number", placeholder="e.g. SC-2026-00123"
    )

st.subheader("Required documents")
bundle_texts = {"claim_form": None, "itinerary": None, "boarding_pass": None, "delay_letter": None}
unreadable = []

if use_sample != "None":
    sample = SAMPLES[use_sample]
    st.success(f"Loaded sample scenario: **{use_sample}**")
    for key, label in [
        ("claim_form", "Claim form"),
        ("itinerary", "Itinerary"),
        ("boarding_pass", "Boarding pass"),
        ("delay_letter", "Delay letter"),
    ]:
        content = sample.get(key, "")
        bundle_texts[key] = content if content else None
        with st.expander(f"{label} {'✅' if content else '❌ (missing in this sample)'}"):
            st.text(content or "(not provided)")
else:
    doc_labels = {
        "claim_form": "Claim form (PDF)",
        "itinerary": "Itinerary — scheduled & revised (PDF)",
        "boarding_pass": "Boarding pass (PDF)",
        "delay_letter": "Airline delay letter (PDF)",
    }
    for key, label in doc_labels.items():
        uploaded = st.file_uploader(label, type=["pdf"], key=f"upload_{key}")
        if uploaded is not None:
            file_bytes = uploaded.getvalue()  # getvalue() so the stream can be read again if needed
            text = extract_text_from_pdf(file_bytes)
            if text is None:
                st.info("Text layer not found (likely a scanned document) — trying Gemini native PDF reading...")
                text = gemini_pdf_to_text(file_bytes)
            if text is None:
                unreadable.append(key)
                st.warning("Could not extract text from this PDF — flagged as unreadable.")
            else:
                st.success("Document read successfully.")
            bundle_texts[key] = text

if st.button("Submit Claim", type="primary"):
    bundle = DocumentBundle(
        claim_form_text=bundle_texts["claim_form"],
        itinerary_text=bundle_texts["itinerary"],
        boarding_pass_text=bundle_texts["boarding_pass"],
        delay_letter_text=bundle_texts["delay_letter"],
        unreadable_documents=unreadable,
    )

    combined_text = "\n\n".join(
        f"=== {name.upper()} ===\n{text}"
        for name, text in bundle_texts.items()
        if text
    )
    # Fold in the manually-typed name/policy number as extra context for the LLM
    combined_text = (
        f"Customer name (as entered in form): {customer_name_input}\n"
        f"Policy number (as entered in form): {policy_number_input}\n\n" + combined_text
    )

    with st.spinner("Extracting structured data from documents..."):
        extracted = extract_claim_data(combined_text)

    # Prefer form-entered values if the LLM/extraction missed them
    extracted.customer_name = extracted.customer_name or customer_name_input or None
    extracted.policy_number = extracted.policy_number or policy_number_input or None

    policy_record = get_policy(extracted.policy_number)
    policy_assessment = evaluate_policy(extracted, policy_record=policy_record)
    completeness = check_completeness(bundle, extracted, policy_record=policy_record)
    recommendation, reason = build_recommendation(policy_assessment, completeness)

    duplicate_id = find_duplicate(extracted.policy_number, extracted.flight_number)
    duplicate_warning = None
    if duplicate_id:
        duplicate_warning = f"Possible duplicate of existing claim {duplicate_id}"
        recommendation, reason = "REQUEST_INFO", duplicate_warning

    assessment = ClaimAssessment(
        claim_id="",  # filled by db
        customer_name=extracted.customer_name,
        policy_number=extracted.policy_number,
        flight_number=extracted.flight_number,
        claim_type=extracted.claim_type,
        delay_hours=extracted.delay_hours,
        documents_complete=completeness.documents_complete,
        policy_covered=policy_assessment.policy_covered,
        information_consistent=completeness.information_consistent,
        missing_documents=completeness.missing_documents,
        inconsistencies=completeness.inconsistencies,
        policy_reasons=policy_assessment.reasons,
        ai_recommendation=recommendation,
        recommendation_reason=reason,
        extraction_source=extracted.source,
        duplicate_warning=duplicate_warning,
    )

    claim_id = save_claim(extracted, assessment, bundle)

    st.success(f"Claim submitted! Claim ID: **{claim_id}**")
    badge = {"APPROVE": "🟢", "REJECT": "🔴", "REQUEST_INFO": "🟡"}[recommendation]
    st.markdown(f"### {badge} AI Recommendation: **{recommendation}**")
    st.write(reason)
    st.caption(f"Extraction source: {extracted.source}")
    st.info("This claim now appears in the Ops Review dashboard for a human decision.")