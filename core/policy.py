from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from dateutil import parser as dateparser 
from core.models import ExtractedClaimData, DocumentBundle, PolicyAssessment, CompletenessCheck
from core.logging_config import get_logger

logger = get_logger(__name__)

# Simplified policy configuration (edit these to simulate different products)
COVERED_CLAIM_TYPES = {"Flight Delay"}
MIN_DELAY_HOURS = 3.0
CLAIM_WINDOW_DAYS = 30 

REQUIRED_DOCUMENTS = ["claim_form", "itinerary", "boarding_pass", "delay_letter"]


def _safe_parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return dateparser.parse(value, fuzzy=True).date()
    except Exception:
        return None


def evaluate_policy(
    claim: ExtractedClaimData,
    policy_record: Optional[dict] = None,
    today: Optional[date] = None,
) -> PolicyAssessment:
    today = today or date.today()
    reasons: list[str] = []

    claim_type_covered = claim.claim_type in COVERED_CLAIM_TYPES
    if not claim_type_covered:
        reasons.append(f"Claim type '{claim.claim_type}' is not a covered benefit.")

    delay_threshold_met = (claim.delay_hours or 0) >= MIN_DELAY_HOURS
    if not delay_threshold_met:
        if claim.delay_hours is None:
            reasons.append("Delay duration could not be determined from documents.")
        else:
            reasons.append(
                f"Delay of {claim.delay_hours}h is below the {MIN_DELAY_HOURS}h minimum required."
            )

    within_claim_window = True
    return_date = _safe_parse_date(claim.return_to_singapore_date)
    if return_date:
        days_elapsed = (today - return_date).days
        within_claim_window = 0 <= days_elapsed <= CLAIM_WINDOW_DAYS
        if not within_claim_window:
            reasons.append(
                f"Claim submitted {days_elapsed} days after return; exceeds the "
                f"{CLAIM_WINDOW_DAYS}-working-day window."
            )
    else:
        reasons.append("Return-to-Singapore date not found; claim window could not be verified.")

    # Coverage period check: is the policy active on the flight's scheduled date?
    policy_active = False
    if policy_record is None:
        reasons.append("Policy number not found in the policy master records.")
    else:
        flight_date = _safe_parse_date(claim.scheduled_departure) or _safe_parse_date(
            claim.actual_departure
        )
        start = _safe_parse_date(policy_record.get("start_date"))
        end = _safe_parse_date(policy_record.get("end_date"))
        if flight_date and start and end:
            policy_active = start <= flight_date <= end
            if not policy_active:
                reasons.append(
                    f"Flight date {flight_date} falls outside the policy's coverage period "
                    f"({start} to {end})."
                )
        else:
            reasons.append("Flight date could not be determined; coverage period not verified.")

    if claim_type_covered and delay_threshold_met and within_claim_window and policy_active and not reasons:
        reasons.append("Claim type, delay duration, claim window, and coverage period all satisfy policy conditions.")

    result = PolicyAssessment(
        claim_type_covered=claim_type_covered,
        delay_threshold_met=delay_threshold_met,
        within_claim_window=within_claim_window,
        policy_active=policy_active,
        reasons=reasons,
    )
    logger.info(
        "Policy evaluation: covered=%s, claim_type=%s, delay_threshold=%s, claim_window=%s, policy_active=%s",
        result.policy_covered,
        result.claim_type_covered,
        result.delay_threshold_met,
        result.within_claim_window,
        result.policy_active,
    )
    return result


def check_completeness(
    bundle: DocumentBundle, claim: ExtractedClaimData, policy_record: Optional[dict] = None
) -> CompletenessCheck:
    missing = []
    doc_map = {
        "claim_form": bundle.claim_form_text,
        "itinerary": bundle.itinerary_text,
        "boarding_pass": bundle.boarding_pass_text,
        "delay_letter": bundle.delay_letter_text,
    }
    for doc_name in REQUIRED_DOCUMENTS:
        if not doc_map.get(doc_name):
            missing.append(doc_name)
    missing.extend(f"{d} (unreadable)" for d in bundle.unreadable_documents if d not in missing)

    inconsistencies = []

    # Cross-document flight number consistency check
    flight_mentions = []
    for label, text in doc_map.items():
        if text and claim.flight_number and claim.flight_number.replace(" ", "").lower() not in text.replace(" ", "").lower():
            flight_mentions.append(label)
    if claim.flight_number and flight_mentions:
        inconsistencies.append(
            f"Flight number '{claim.flight_number}' not found in: {', '.join(flight_mentions)}."
        )

    if claim.delay_hours is not None and claim.delay_hours < 0:
        inconsistencies.append("Delay duration is negative - likely a data extraction error.")

    if claim.policy_number and policy_record is None:
        inconsistencies.append(
            f"Policy number '{claim.policy_number}' was not found in our records - "
            "could be a typo or an unregistered policy. Needs verification, not an automatic rejection."
        )
    elif not claim.policy_number:
        inconsistencies.append("Policy number could not be extracted from the claim form.")

    result = CompletenessCheck(
        documents_complete=len(missing) == 0,
        missing_documents=missing,
        information_consistent=len(inconsistencies) == 0,
        inconsistencies=inconsistencies,
    )
    logger.info(
        "Completeness check: documents_complete=%s, information_consistent=%s, missing_count=%d, inconsistency_count=%d",
        result.documents_complete,
        result.information_consistent,
        len(result.missing_documents),
        len(result.inconsistencies),
    )
    return result


def build_recommendation(policy: PolicyAssessment, completeness: CompletenessCheck) -> tuple[str, str]:
    """Returns (recommendation, reason). Pure deterministic decision tree."""
    if not completeness.documents_complete:
        logger.info("Recommendation selected: REQUEST_INFO due to incomplete documents")
        return "REQUEST_INFO", "Missing required document(s): " + ", ".join(completeness.missing_documents)

    if not completeness.information_consistent:
        logger.info("Recommendation selected: REQUEST_INFO due to inconsistencies")
        return "REQUEST_INFO", "Inconsistencies found across documents: " + "; ".join(completeness.inconsistencies)

    if not policy.policy_covered:
        logger.info("Recommendation selected: REJECT due to policy failure")
        return "REJECT", " ".join(policy.reasons)

    logger.info("Recommendation selected: APPROVE")
    return "APPROVE", "All policy conditions met; documents complete and consistent."
