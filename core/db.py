from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from core.logging_config import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "surecover.db"


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    logger.info("Initializing SQLite database: path=%s", DB_PATH)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                claim_id TEXT PRIMARY KEY,
                created_at TEXT,
                customer_name TEXT,
                policy_number TEXT,
                flight_number TEXT,
                claim_type TEXT,
                delay_hours REAL,
                extraction_source TEXT,
                extracted_json TEXT,
                assessment_json TEXT,
                documents_json TEXT,
                ai_recommendation TEXT,
                recommendation_reason TEXT,
                ops_decision TEXT DEFAULT 'PENDING',
                ops_notes TEXT DEFAULT '',
                decided_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS policies (
                policy_number TEXT PRIMARY KEY,
                customer_name TEXT,
                product_type TEXT,
                start_date TEXT,
                end_date TEXT
            )
            """
        )
        conn.commit()
    logger.info("SQLite database initialized")


def seed_policies(records: list[dict]):
    logger.info("Seeding policies: count=%d", len(records))
    with get_conn() as conn:
        for r in records:
            conn.execute(
                """
                INSERT OR IGNORE INTO policies
                    (policy_number, customer_name, product_type, start_date, end_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (r["policy_number"], r["customer_name"], r["product_type"], r["start_date"], r["end_date"]),
            )
        conn.commit()


def get_policy(policy_number: Optional[str]) -> Optional[dict]:
    if not policy_number:
        logger.warning("Policy lookup skipped: empty policy number")
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM policies WHERE policy_number = ?", (policy_number,)
        ).fetchone()
        policy = dict(row) if row else None
        logger.info("Policy lookup completed: found=%s", policy is not None)
        return policy


def find_duplicate(policy_number: Optional[str], flight_number: Optional[str]) -> Optional[str]:
    """Returns an existing claim_id if the same policy+flight was already submitted."""
    if not policy_number or not flight_number:
        logger.info("Duplicate check skipped: policy or flight number is empty")
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT claim_id FROM claims WHERE policy_number = ? AND flight_number = ? "
            "ORDER BY created_at ASC LIMIT 1",
            (policy_number, flight_number),
        ).fetchone()
        duplicate_id = row["claim_id"] if row else None
        logger.info("Duplicate check completed: found=%s", duplicate_id is not None)
        return duplicate_id


def save_claim(extracted, assessment, bundle) -> str:
    claim_id = f"SC-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    logger.info(
        "Saving claim: claim_id=%s, policy_present=%s, flight_present=%s",
        claim_id,
        bool(extracted.policy_number),
        bool(extracted.flight_number),
    )
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO claims (
                claim_id, created_at, customer_name, policy_number, flight_number,
                claim_type, delay_hours, extraction_source, extracted_json,
                assessment_json, documents_json, ai_recommendation, recommendation_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                datetime.utcnow().isoformat(),
                extracted.customer_name,
                extracted.policy_number,
                extracted.flight_number,
                extracted.claim_type,
                extracted.delay_hours,
                extracted.source,
                extracted.model_dump_json(),
                assessment.model_dump_json(),
                bundle.model_dump_json(),
                assessment.ai_recommendation,
                assessment.recommendation_reason,
            ),
        )
        conn.commit()
    logger.info("Claim saved: claim_id=%s", claim_id)
    return claim_id


def list_claims(status: Optional[str] = None):
    logger.info("Listing claims: status=%s", status or "ALL")
    with get_conn() as conn:
        if status and status != "ALL":
            rows = conn.execute(
                "SELECT * FROM claims WHERE ops_decision = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM claims ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_claim(claim_id: str):
    logger.info("Loading claim detail: claim_id=%s", claim_id)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        return dict(row) if row else None


def update_decision(claim_id: str, decision: str, notes: str = ""):
    logger.info(
        "Updating Ops decision: claim_id=%s, decision=%s, has_notes=%s",
        claim_id,
        decision,
        bool(notes.strip()),
    )
    with get_conn() as conn:
        conn.execute(
            "UPDATE claims SET ops_decision = ?, ops_notes = ?, decided_at = ? WHERE claim_id = ?",
            (decision, notes, datetime.utcnow().isoformat(), claim_id),
        )
        conn.commit()
