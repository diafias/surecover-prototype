"""
Canned sample claims so the demo doesn't depend on having real scanned
insurance PDFs on hand. Covers the three interesting paths panels usually
ask about: clean approve, missing document, and inconsistent/borderline case.
"""

SAMPLES = {
    "Clean approve": {
        "claim_form": (
            "SureCover Claim Form\nName: John Tan\nPolicy Number: SC-2026-00123\n"
            "Flight Number: SQ123\nClaim Type: Flight Delay\nReturn to Singapore Date: 2026-09-01\n"
        ),
        "itinerary": (
            "Flight Itinerary\nFlight Number: SQ123\nScheduled Departure: 2026-08-20 08:00\n"
            "Airline: Singapore Airlines\n"
        ),
        "boarding_pass": "Boarding Pass\nFlight SQ123\nPassenger: John Tan\nDate: 2026-08-20\n",
        "delay_letter": (
            "To whom it may concern,\nFlight SQ123 on 2026-08-20 was delayed by 4.5 hours "
            "due to technical issue. Actual Departure: 2026-08-20 12:30.\n- Singapore Airlines\n"
        ),
    },
    "Missing document": {
        "claim_form": (
            "SureCover Claim Form\nName: Mei Ling\nPolicy Number: SC-2026-00456\n"
            "Flight Number: TR889\nClaim Type: Flight Delay\nReturn to Singapore Date: 2026-09-05\n"
        ),
        "itinerary": "Flight Itinerary\nFlight Number: TR889\nScheduled Departure: 2026-08-25 14:00\n",
        "boarding_pass": "",  # missing on purpose
        "delay_letter": "Flight TR889 delayed 5 hours due to weather.\n",
    },
    "Inconsistent / below threshold": {
        "claim_form": (
            "SureCover Claim Form\nName: Ahmad Rahman\nPolicy Number: SC-2026-00789\n"
            "Flight Number: MH603\nClaim Type: Flight Delay\nReturn to Singapore Date: 2026-08-30\n"
        ),
        "itinerary": "Flight Itinerary\nFlight Number: MH603\nScheduled Departure: 2026-08-18 09:00\n",
        "boarding_pass": "Boarding Pass\nFlight MH603\nPassenger: Ahmad Rahman\n",
        "delay_letter": (
            "Flight MH603 delayed by 1.5 hours due to air traffic control.\n"
            "Actual Departure: 2026-08-18 10:30.\n"
        ),
    },
}
