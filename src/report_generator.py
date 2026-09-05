"""
NexusRisk AI - Investigation report generation.

Always includes the human-review disclaimer. Never states that fraud
has occurred.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any

from .config import DISCLAIMER


ASSESSMENT_LABELS = {
    "NO_SIGNIFICANT_SIGNALS": "NO SIGNIFICANT RISK SIGNALS",
    "REVIEW_RECOMMENDED": "REVIEW RECOMMENDED",
    "HIGH_PRIORITY_REVIEW": "HIGH PRIORITY HUMAN REVIEW",
}


def generate_report_text(investigation: Dict[str, Any]) -> str:
    ai = investigation.get("ai_result", {})
    baseline = investigation.get("baseline", {})
    findings = investigation.get("risk_findings", [])
    score = {
        "review_priority_score": investigation.get("review_priority_score"),
        "category": investigation.get("category"),
    }
    assessment_label = ASSESSMENT_LABELS.get(ai.get("assessment"), ai.get("assessment", "UNKNOWN"))

    lines = []
    lines.append("=" * 60)
    lines.append("NEXUSRISK AI")
    lines.append("TRANSACTION INVESTIGATION REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Investigation ID: {investigation.get('investigation_id')}")
    lines.append(f"Customer ID: {investigation.get('customer_id')}")
    lines.append(f"Analysis Date: {datetime.now(timezone.utc).strftime('%d-%b-%Y %H:%M UTC')}")
    lines.append(f"Transactions Analyzed: {investigation.get('transactions_analyzed')}")
    lines.append("")
    lines.append(f"OVERALL ASSESSMENT: {assessment_label}")
    lines.append(f"Review Priority Score: {score.get('review_priority_score')} ({score.get('category')})")
    lines.append("")
    lines.append("SUMMARY")
    lines.append("-" * 60)
    lines.append(ai.get("summary", "No summary available."))
    lines.append("")

    lines.append("RISK SIGNALS")
    lines.append("-" * 60)
    if findings:
        for f in findings:
            lines.append(f"[{f['rule_id']}] {f['title']} (severity: {f['severity']})")
            lines.append(f"    {f['explanation']}")
            lines.append(f"    Evidence: {', '.join(f['evidence_ids'])}")
            lines.append("")
    else:
        lines.append("No risk signals were identified in the supplied transaction history.")
        lines.append("")

    lines.append("CUSTOMER BASELINE")
    lines.append("-" * 60)
    lines.append(f"Median Transaction: Rs {baseline.get('median_amount') or 0:,.2f}")
    lines.append(
        f"Typical Range: Rs {baseline.get('typical_range_low') or 0:,.2f} - "
        f"Rs {baseline.get('typical_range_high') or 0:,.2f}"
    )
    lines.append(
        f"Typical Active Hours: {baseline.get('typical_hour_start', '-')}:00 - "
        f"{baseline.get('typical_hour_end', '-')}:00"
    )
    lines.append(f"Common Channels: {', '.join(baseline.get('common_channels', []) or ['-'])}")
    lines.append(f"Known Beneficiaries: {baseline.get('known_beneficiaries_count', 0)}")
    lines.append(f"Average Daily Transactions: {round(baseline.get('avg_daily_transactions') or 0, 2)}")
    lines.append("")

    lines.append("TRANSACTION RELATIONSHIPS")
    lines.append("-" * 60)
    r06 = [f for f in findings if f["rule_id"] == "R06"]
    if r06:
        for f in r06:
            lines.append(f"    {' -> '.join(f['evidence_ids'])}")
    else:
        lines.append("No related transaction sequences were identified.")
    lines.append("")

    lines.append("INVESTIGATOR FOCUS")
    lines.append("-" * 60)
    for item in ai.get("investigator_focus", []) or ["No specific focus items identified."]:
        lines.append(f"  - {item}")
    lines.append("")

    lines.append("MISSING INFORMATION / UNCERTAINTY")
    lines.append("-" * 60)
    for item in ai.get("uncertainties", []) or ["No uncertainties flagged."]:
        lines.append(f"  - {item}")
    lines.append("")

    lines.append("RECOMMENDED NEXT STEP")
    lines.append("-" * 60)
    if ai.get("assessment") == "NO_SIGNIFICANT_SIGNALS":
        lines.append("No escalation is recommended based on the supplied transaction history.")
    else:
        lines.append("Escalate to a qualified investigator for detailed manual review of the evidence above.")
    lines.append("")

    lines.append("HUMAN REVIEW REQUIREMENT")
    lines.append("-" * 60)
    lines.append("HUMAN REVIEW REQUIRED: " + ("YES" if ai.get("human_review_required") else "AT INVESTIGATOR DISCRETION"))
    lines.append("")

    lines.append("SYSTEM DISCLAIMER")
    lines.append("-" * 60)
    lines.append(DISCLAIMER)
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
