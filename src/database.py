"""
NexusRisk AI - SQLite persistence layer.

Tables: customers, transactions, investigations, risk_findings, evidence_links
No external database required.
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS investigations (
    investigation_id TEXT PRIMARY KEY,
    customer_id TEXT,
    created_at TEXT,
    transactions_analyzed INTEGER,
    review_priority_score INTEGER,
    category TEXT,
    baseline_json TEXT,
    ai_result_json TEXT,
    validation_messages_json TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT,
    transaction_id TEXT,
    date TEXT,
    amount REAL,
    payee TEXT,
    description TEXT,
    channel TEXT,
    transaction_type TEXT,
    beneficiary_id TEXT,
    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id)
);

CREATE TABLE IF NOT EXISTS risk_findings (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT,
    rule_id TEXT,
    title TEXT,
    severity TEXT,
    explanation TEXT,
    details_json TEXT,
    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id)
);

CREATE TABLE IF NOT EXISTS evidence_links (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT,
    finding_id INTEGER,
    transaction_id TEXT,
    FOREIGN KEY (finding_id) REFERENCES risk_findings(finding_id)
);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_investigation(investigation_id: str, customer_id: str, df, findings, score_info,
                        baseline_dict: Dict[str, Any], ai_result: Dict[str, Any],
                        validation_messages: List[str]):
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO customers (customer_id, created_at) VALUES (?, ?)",
            (customer_id, now),
        )
        conn.execute(
            """INSERT INTO investigations
               (investigation_id, customer_id, created_at, transactions_analyzed,
                review_priority_score, category, baseline_json, ai_result_json,
                validation_messages_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                investigation_id, customer_id, now, len(df),
                score_info["review_priority_score"], score_info["category"],
                json.dumps(baseline_dict, default=str),
                json.dumps(ai_result, default=str),
                json.dumps(validation_messages),
            ),
        )
        for _, row in df.iterrows():
            conn.execute(
                """INSERT INTO transactions
                   (investigation_id, transaction_id, date, amount, payee, description,
                    channel, transaction_type, beneficiary_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    investigation_id, row["transaction_id"], row["_parsed_date"].isoformat(),
                    row["_parsed_amount"], row.get("payee", ""), row.get("description", ""),
                    row.get("channel", ""), row.get("transaction_type", ""),
                    row.get("beneficiary_id", ""),
                ),
            )
        for f in findings:
            cur = conn.execute(
                """INSERT INTO risk_findings
                   (investigation_id, rule_id, title, severity, explanation, details_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (investigation_id, f.rule_id, f.title, f.severity, f.explanation,
                 json.dumps(f.details, default=str)),
            )
            finding_id = cur.lastrowid
            for tid in f.evidence_ids:
                conn.execute(
                    """INSERT INTO evidence_links (investigation_id, finding_id, transaction_id)
                       VALUES (?, ?, ?)""",
                    (investigation_id, finding_id, tid),
                )


def get_investigation(investigation_id: str) -> Dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM investigations WHERE investigation_id = ?", (investigation_id,)
        ).fetchone()
        if not row:
            return None
        investigation = dict(row)
        investigation["baseline"] = json.loads(investigation.pop("baseline_json") or "{}")
        investigation["ai_result"] = json.loads(investigation.pop("ai_result_json") or "{}")
        investigation["validation_messages"] = json.loads(investigation.pop("validation_messages_json") or "[]")

        findings_rows = conn.execute(
            "SELECT * FROM risk_findings WHERE investigation_id = ?", (investigation_id,)
        ).fetchall()
        findings = []
        for fr in findings_rows:
            fd = dict(fr)
            fd["details"] = json.loads(fd.pop("details_json") or "{}")
            links = conn.execute(
                "SELECT transaction_id FROM evidence_links WHERE finding_id = ?", (fd["finding_id"],)
            ).fetchall()
            fd["evidence_ids"] = [l["transaction_id"] for l in links]
            findings.append(fd)
        investigation["risk_findings"] = findings

        txn_rows = conn.execute(
            "SELECT * FROM transactions WHERE investigation_id = ? ORDER BY date", (investigation_id,)
        ).fetchall()
        investigation["transactions"] = [dict(t) for t in txn_rows]

        return investigation
