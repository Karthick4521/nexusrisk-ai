"""
NexusRisk AI - Evidence chain construction.

Every finding must be traceable to actual input transactions. This module
never fabricates evidence: it only reads back rows that risk_engine already
attached transaction IDs to.
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd

from .risk_engine import RiskFinding
from .baseline import CustomerBaseline


def build_evidence_chain(category: str, findings: List[RiskFinding]) -> Dict[str, Any]:
    """Rule -> Transaction tree, rooted at the overall category."""
    tree = {"label": category, "children": []}
    for f in findings:
        tree["children"].append({
            "label": f"{f.rule_id} {f.title}",
            "rule_id": f.rule_id,
            "children": [{"label": tid, "transaction_id": tid} for tid in f.evidence_ids],
        })
    return tree


def build_evidence_viewer(transaction_id: str, df: pd.DataFrame, findings: List[RiskFinding],
                           baseline: CustomerBaseline) -> Dict[str, Any] | None:
    row_matches = df[df["transaction_id"] == transaction_id]
    if row_matches.empty:
        return None
    row = row_matches.iloc[0]

    triggered = [f for f in findings if transaction_id in f.evidence_ids]
    reasons = []
    for f in triggered:
        if f.rule_id == "R01":
            reasons.append("unusually large amount")
        elif f.rule_id == "R02":
            reasons.append("part of a transaction burst")
        elif f.rule_id == "R03":
            reasons.append("newly observed beneficiary")
        elif f.rule_id == "R04":
            reasons.append("occurred during odd hours")
        elif f.rule_id == "R05":
            reasons.append("deviates from established behavior")
        elif f.rule_id == "R06":
            reasons.append("part of a related transaction sequence")

    return {
        "transaction_id": row["transaction_id"],
        "date": row["_parsed_date"].isoformat(),
        "amount": row["_parsed_amount"],
        "payee": row.get("payee") or row.get("description") or "Unknown",
        "description": row.get("description", ""),
        "channel": row.get("channel", ""),
        "beneficiary_id": row.get("beneficiary_id", ""),
        "transaction_type": row.get("transaction_type", ""),
        "triggered_rules": [f.rule_id for f in triggered],
        "why_selected": reasons,
        "baseline_comparison": {
            "typical_range_low": baseline.typical_range_low,
            "typical_range_high": baseline.typical_range_high,
            "median_amount": baseline.median_amount,
            "observed_amount": row["_parsed_amount"],
        },
    }
