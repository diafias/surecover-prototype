"""
Dummy policy master data.

In production this would be a real query to SureCover's policy admin
system (or StarBridge Telecom's subscriber DB, since SureCover is
sold as a telco add-on). For the prototype we seed a handful of
fixed records so "coverage period" validation has something real to
check against.
"""

SEED_POLICIES = [
    {
        "policy_number": "SC-2026-00123",
        "customer_name": "John Tan",
        "product_type": "Travel Insurance",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    },
    {
        "policy_number": "SC-2026-00456",
        "customer_name": "Mei Ling",
        "product_type": "Travel Insurance",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    },
    {
        "policy_number": "SC-2026-00789",
        "customer_name": "Ahmad Rahman",
        "product_type": "Travel Insurance",
        "start_date": "2026-01-01",
        "end_date": "2026-06-30", 
    },
]
