"""
NexusRisk AI - Investigation orchestration service.

Ties together the full workflow described in the spec:
CSV -> Validation -> Baseline -> Risk Engine -> Evidence Chain ->
Policy Retrieval -> Gemini -> Persistence -> Report.
"""
from __future__ import annotations
from typing import Dict, Any
import pandas as pd

from .transaction_parser import validate_and_clean
from .baseline import split_recent_historical, build_baseline
from .risk_engine import run_all_rules, compute_score
from .evidence_engine import build_evidence_chain
from .retrieval import retrieve_relevant_policies
from .gemini_client import generate_explanation
from .database import save_investigation
from .utils import new_id


def run_investigation(raw_bytes: bytes, customer_id: str) -> Dict[str, Any]:
    validation = validate_and_clean(raw_bytes)

    if not validation.ok:
        return {
            "ok": False,
            "error": validation.error,
            "messages": validation.messages,
            "rows_in": validation.rows_in,
            "rows_out": validation.rows_out,
        }

    df = validation.dataframe
    historical_df, recent_df = split_recent_historical(df)
    baseline = build_baseline(historical_df)
    baseline.recent_count = len(recent_df)

    findings = run_all_rules(recent_df, baseline)
    score_info = compute_score(findings)

    evidence_chain = build_evidence_chain(score_info["category"], findings)

    policy_query = (
        f"rules triggered: {', '.join(score_info['rules_triggered'])} "
        f"category: {score_info['category']}"
    )
    relevant_policies = retrieve_relevant_policies(policy_query)

    case_context = {
        "customer_id": customer_id,
        "transactions_analyzed": len(df),
        "baseline": baseline.to_dict(),
        "risk_findings": [f.to_dict() for f in findings],
        "score": score_info,
        "relevant_policies": relevant_policies,
        "recent_window_transaction_ids": recent_df["transaction_id"].tolist(),
    }

    ai_result = generate_explanation(case_context)

    investigation_id = new_id("INV")
    save_investigation(
        investigation_id=investigation_id,
        customer_id=customer_id,
        df=df,
        findings=findings,
        score_info=score_info,
        baseline_dict=baseline.to_dict(),
        ai_result=ai_result,
        validation_messages=validation.messages,
    )

    timeline = [
        {
            "transaction_id": row["transaction_id"],
            "date": row["_parsed_date"].isoformat(),
            "amount": row["_parsed_amount"],
            "flagged": row["transaction_id"] in {tid for f in findings for tid in f.evidence_ids},
        }
        for _, row in df.iterrows()
    ]

    return {
        "ok": True,
        "investigation_id": investigation_id,
        "customer_id": customer_id,
        "transactions_analyzed": len(df),
        "validation_messages": validation.messages,
        "baseline": baseline.to_dict(),
        "risk_findings": [f.to_dict() for f in findings],
        "score": score_info,
        "evidence_chain": evidence_chain,
        "ai_result": ai_result,
        "timeline": timeline,
        "relevant_policies": relevant_policies,
    }
