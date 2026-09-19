"""
Pydantic schemas shared across the pipeline.

Design note: the LLM is ONLY ever asked to fill in `ExtractedClaimData`
(unstructured -> structured). Every field below that decides eligibility
(`PolicyAssessment`, `CompletenessCheck`) is computed by deterministic
Python, never by the LLM. The LLM's own free-text reasoning is kept in
`ai_recommendation` / `recommendation_reason` for transparency, but it does
NOT influence the boolean checks.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedClaimData(BaseModel):
    """What we ask the LLM to extract from the raw documents/email."""

    customer_name: Optional[str] = None
    policy_number: Optional[str] = None
    flight_number: Optional[str] = None
    scheduled_departure: Optional[str] = None  # ISO-ish string, best effort
    actual_departure: Optional[str] = None
    delay_hours: Optional[float] = None
    delay_reason: Optional[str] = None
    claim_type: str = "Flight Delay"
    return_to_singapore_date: Optional[str] = None
    airline: Optional[str] = None

    # bookkeeping, filled in by our own code, not the LLM
    source: str = "unknown"  # "gemini" | "groq" | "rule_based"
    extraction_notes: List[str] = Field(default_factory=list)


class DocumentBundle(BaseModel):
    """What documents customer actually attached, and whether we could read them."""

    claim_form_text: Optional[str] = None
    itinerary_text: Optional[str] = None
    boarding_pass_text: Optional[str] = None
    delay_letter_text: Optional[str] = None
    unreadable_documents: List[str] = Field(default_factory=list)


class PolicyAssessment(BaseModel):
    claim_type_covered: bool
    delay_threshold_met: bool
    within_claim_window: bool
    policy_active: bool  # coverage period check against the policy master record
    reasons: List[str] = Field(default_factory=list)

    @property
    def policy_covered(self) -> bool:
        return (
            self.claim_type_covered
            and self.delay_threshold_met
            and self.within_claim_window
            and self.policy_active
        )


class CompletenessCheck(BaseModel):
    documents_complete: bool
    missing_documents: List[str] = Field(default_factory=list)
    information_consistent: bool
    inconsistencies: List[str] = Field(default_factory=list)


class ClaimAssessment(BaseModel):
    claim_id: str
    customer_name: Optional[str]
    policy_number: Optional[str]
    flight_number: Optional[str]
    claim_type: str
    delay_hours: Optional[float]

    documents_complete: bool
    policy_covered: bool
    information_consistent: bool

    missing_documents: List[str] = Field(default_factory=list)
    inconsistencies: List[str] = Field(default_factory=list)
    policy_reasons: List[str] = Field(default_factory=list)

    ai_recommendation: str  # "APPROVE" | "REJECT" | "REQUEST_INFO"
    recommendation_reason: str
    extraction_source: str = "unknown"
    duplicate_warning: Optional[str] = None  # set to an existing claim_id if duplicate detected
