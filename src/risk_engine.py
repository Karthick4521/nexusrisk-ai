"""
NexusRisk AI - Deterministic Risk Engine.

All numerical/statistical decisions live here in Python. Gemini never
makes rule decisions - it only explains what this module has already found.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Dict, Any
import pandas as pd

from .config import (
    ODD_HOUR_START, ODD_HOUR_END, BURST_WINDOW_HOURS, BURST_MIN_COUNT,
    LARGE_TXN_IQR_MULTIPLIER, R05_MIN_DEVIATION_DIMENSIONS, R06_LINK_WINDOW_HOURS,
    RULE_WEIGHTS, SCORE_THRESHOLDS,
)
from .baseline import CustomerBaseline, CREDIT_TYPES


@dataclass
class RiskFinding:
    rule_id: str
    title: str
    severity: str
    explanation: str
    evidence_ids: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity,
            "explanation": self.explanation,
            "evidence_ids": self.evidence_ids,
            "details": self.details,
        }


RULE_TITLES = {
    "R01": "Unusually Large Transaction",
    "R02": "Transaction Burst",
    "R03": "New Beneficiary",
    "R04": "Odd-Hour Activity",
    "R05": "Customer Behavior Deviation",
    "R06": "Related Transaction Pattern",
}


def _is_debit(row) -> bool:
    return str(row.get("transaction_type", "")).lower() not in CREDIT_TYPES


def rule_r01_large_transaction(recent_df: pd.DataFrame, baseline: CustomerBaseline) -> List[RiskFinding]:
    findings = []
    if baseline.median_amount is None or baseline.iqr is None or baseline.p75_amount is None:
        return findings
    threshold = baseline.p75_amount + LARGE_TXN_IQR_MULTIPLIER * (baseline.iqr or 0)
    threshold = max(threshold, (baseline.p95_amount or threshold))
    for _, row in recent_df.iterrows():
        if not _is_debit(row):
            continue
        amt = row["_parsed_amount"]
        if amt > threshold and amt > (baseline.median_amount or 0):
            findings.append(RiskFinding(
                rule_id="R01",
                title=RULE_TITLES["R01"],
                severity="HIGH",
                explanation=(
                    f"Transaction {row['transaction_id']} amount of \u20b9{amt:,.2f} is significantly "
                    f"above the customer's established transaction pattern (typical range "
                    f"\u20b9{baseline.typical_range_low:,.2f}-\u20b9{baseline.typical_range_high:,.2f}, "
                    f"median \u20b9{baseline.median_amount:,.2f})."
                ),
                evidence_ids=[row["transaction_id"]],
                details={"amount": amt, "threshold": threshold, "median": baseline.median_amount},
            ))
    return findings


def rule_r02_transaction_burst(recent_df: pd.DataFrame, baseline: CustomerBaseline) -> List[RiskFinding]:
    findings = []
    if baseline.p75_amount is None:
        return findings
    high_value_cutoff = max(baseline.p75_amount, (baseline.median_amount or 0) * 2)
    debit_rows = recent_df[recent_df.apply(_is_debit, axis=1)].sort_values("_parsed_date")
    high_rows = debit_rows[debit_rows["_parsed_amount"] > high_value_cutoff]

    high_rows = high_rows.reset_index(drop=True)
    used = set()
    for i in range(len(high_rows)):
        if i in used:
            continue
        window_start = high_rows.loc[i, "_parsed_date"]
        cluster_idx = [i]
        for j in range(i + 1, len(high_rows)):
            if (high_rows.loc[j, "_parsed_date"] - window_start) <= timedelta(hours=BURST_WINDOW_HOURS):
                cluster_idx.append(j)
        if len(cluster_idx) >= BURST_MIN_COUNT:
            used.update(cluster_idx)
            ids = [high_rows.loc[k, "transaction_id"] for k in cluster_idx]
            total = sum(high_rows.loc[k, "_parsed_amount"] for k in cluster_idx)
            findings.append(RiskFinding(
                rule_id="R02",
                title=RULE_TITLES["R02"],
                severity="HIGH",
                explanation=(
                    f"{len(ids)} high-value transactions totaling \u20b9{total:,.2f} occurred within "
                    f"{BURST_WINDOW_HOURS} hours of each other ({', '.join(ids)})."
                ),
                evidence_ids=ids,
                details={"count": len(ids), "total_amount": total, "window_hours": BURST_WINDOW_HOURS},
            ))
    return findings


def rule_r03_new_beneficiary(recent_df: pd.DataFrame, baseline: CustomerBaseline) -> List[RiskFinding]:
    findings = []
    seen_in_recent = set()
    for _, row in recent_df.iterrows():
        bnf = row.get("beneficiary_id", "")
        if not bnf or bnf.startswith("PSEUDO_"):
            continue
        if not _is_debit(row):
            continue
        if bnf not in baseline.known_beneficiaries and bnf not in seen_in_recent:
            seen_in_recent.add(bnf)
            findings.append(RiskFinding(
                rule_id="R03",
                title=RULE_TITLES["R03"],
                severity="MEDIUM",
                explanation=(
                    f"Transaction {row['transaction_id']} involves beneficiary {bnf}, which was not "
                    f"previously observed in this customer's historical transaction data."
                ),
                evidence_ids=[row["transaction_id"]],
                details={"beneficiary_id": bnf},
            ))
        elif bnf not in baseline.known_beneficiaries and bnf in seen_in_recent:
            # subsequent txns to the same newly-seen beneficiary still count as evidence
            for f in findings:
                if f.rule_id == "R03" and f.details.get("beneficiary_id") == bnf:
                    f.evidence_ids.append(row["transaction_id"])
    return findings


def rule_r04_odd_hour(recent_df: pd.DataFrame, baseline: CustomerBaseline) -> List[RiskFinding]:
    findings = []
    for _, row in recent_df.iterrows():
        hour = row["_parsed_date"].hour
        if ODD_HOUR_START <= hour < ODD_HOUR_END:
            findings.append(RiskFinding(
                rule_id="R04",
                title=RULE_TITLES["R04"],
                severity="LOW",
                explanation=(
                    f"Transaction {row['transaction_id']} occurred at "
                    f"{row['_parsed_date'].strftime('%H:%M')}, within the unusual activity period "
                    f"({ODD_HOUR_START:02d}:00-{ODD_HOUR_END:02d}:00). This is a timing signal only, "
                    "not evidence of fraud."
                ),
                evidence_ids=[row["transaction_id"]],
                details={"hour": hour},
            ))
    return findings


def rule_r05_behavior_deviation(recent_df: pd.DataFrame, baseline: CustomerBaseline) -> List[RiskFinding]:
    findings = []
    if baseline.median_amount is None:
        return findings
    for _, row in recent_df.iterrows():
        if not _is_debit(row):
            continue
        dims = []
        amt = row["_parsed_amount"]
        if baseline.typical_range_high and amt > baseline.typical_range_high * 1.5:
            dims.append("amount")
        if baseline.common_channels and row["channel"] not in baseline.common_channels:
            dims.append("channel")
        hour = row["_parsed_date"].hour
        if baseline.typical_hour_start is not None and baseline.typical_hour_end is not None:
            if not (baseline.typical_hour_start <= hour <= baseline.typical_hour_end):
                dims.append("timing")
        bnf = row.get("beneficiary_id", "")
        if bnf and not bnf.startswith("PSEUDO_") and bnf not in baseline.known_beneficiaries:
            dims.append("beneficiary")

        if len(dims) >= R05_MIN_DEVIATION_DIMENSIONS:
            findings.append(RiskFinding(
                rule_id="R05",
                title=RULE_TITLES["R05"],
                severity="HIGH",
                explanation=(
                    f"Transaction {row['transaction_id']} differs materially from the customer's "
                    f"historical behavior across {len(dims)} dimensions: {', '.join(dims)}."
                ),
                evidence_ids=[row["transaction_id"]],
                details={"deviation_dimensions": dims},
            ))
    return findings


def rule_r06_related_transactions(recent_df: pd.DataFrame, prior_findings: List[RiskFinding]) -> List[RiskFinding]:
    """Links transactions ALREADY flagged by R01/R02/R03/R05 - does not independently
    detect relationships from raw same-beneficiary/time proximity (that caused false
    positives on routine repeat payments to known payees in earlier testing)."""
    findings = []
    flagged_ids = set()
    for f in prior_findings:
        if f.rule_id in ("R01", "R02", "R03", "R05"):
            flagged_ids.update(f.evidence_ids)

    if len(flagged_ids) < 2:
        return findings

    flagged_rows = recent_df[recent_df["transaction_id"].isin(flagged_ids)].sort_values("_parsed_date")
    flagged_rows = flagged_rows.reset_index(drop=True)

    used = set()
    for i in range(len(flagged_rows)):
        if i in used:
            continue
        cluster = [i]
        base_time = flagged_rows.loc[i, "_parsed_date"]
        base_bnf = flagged_rows.loc[i, "beneficiary_id"]
        for j in range(i + 1, len(flagged_rows)):
            if j in used:
                continue
            time_close = (flagged_rows.loc[j, "_parsed_date"] - base_time) <= timedelta(hours=R06_LINK_WINDOW_HOURS)
            same_bnf = base_bnf and flagged_rows.loc[j, "beneficiary_id"] == base_bnf
            if time_close or same_bnf:
                cluster.append(j)
        if len(cluster) >= 2:
            used.update(cluster)
            ids = [flagged_rows.loc[k, "transaction_id"] for k in cluster]
            findings.append(RiskFinding(
                rule_id="R06",
                title=RULE_TITLES["R06"],
                severity="MEDIUM",
                explanation=(
                    f"Transactions {', '.join(ids)} form a related sequence: they were each "
                    "independently flagged and occurred within a short period and/or shared "
                    "payment characteristics."
                ),
                evidence_ids=ids,
                details={"linked_count": len(ids)},
            ))
    return findings


def run_all_rules(recent_df: pd.DataFrame, baseline: CustomerBaseline) -> List[RiskFinding]:
    findings: List[RiskFinding] = []
    findings += rule_r01_large_transaction(recent_df, baseline)
    findings += rule_r02_transaction_burst(recent_df, baseline)
    findings += rule_r03_new_beneficiary(recent_df, baseline)
    findings += rule_r04_odd_hour(recent_df, baseline)
    findings += rule_r05_behavior_deviation(recent_df, baseline)
    findings += rule_r06_related_transactions(recent_df, findings)
    return findings


def compute_score(findings: List[RiskFinding]) -> Dict[str, Any]:
    score = 0
    rule_ids_seen = set()
    for f in findings:
        if f.rule_id not in rule_ids_seen:
            score += RULE_WEIGHTS.get(f.rule_id, 0)
            rule_ids_seen.add(f.rule_id)
        else:
            # additional instances of the same rule add a smaller increment
            score += RULE_WEIGHTS.get(f.rule_id, 0) // 4

    if score >= SCORE_THRESHOLDS["HIGH_PRIORITY_HUMAN_REVIEW"]:
        category = "HIGH_PRIORITY_HUMAN_REVIEW"
    elif score >= SCORE_THRESHOLDS["HIGH"]:
        category = "HIGH"
    elif score >= SCORE_THRESHOLDS["MEDIUM"]:
        category = "MEDIUM"
    else:
        category = "LOW"

    return {"review_priority_score": score, "category": category, "rules_triggered": sorted(rule_ids_seen)}
