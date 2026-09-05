"""
NexusRisk AI - Customer behavioral baseline.

Splits history into a "historical" period and a "recent" evaluation window
(config.RECENT_WINDOW_DAYS). The baseline is built ONLY from the historical
period so that established habits are never mistaken for new behavior, and
risk rules only ever evaluate the recent window against that baseline.

Debit/transfer transactions are used for amount statistics; salary/credit
transactions are excluded so they don't inflate the "normal" range.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Set
import pandas as pd

from .config import RECENT_WINDOW_DAYS
from .utils import median, percentile


CREDIT_TYPES = {"credit", "salary", "income", "deposit", "refund"}


@dataclass
class CustomerBaseline:
    historical_count: int
    recent_count: int
    median_amount: float | None
    p25_amount: float | None
    p75_amount: float | None
    p95_amount: float | None
    iqr: float | None
    max_amount: float | None
    typical_range_low: float | None
    typical_range_high: float | None
    typical_hour_start: int | None
    typical_hour_end: int | None
    common_channels: List[str] = field(default_factory=list)
    known_beneficiaries: Set[str] = field(default_factory=set)
    known_payees: Set[str] = field(default_factory=set)
    avg_daily_transactions: float | None = None
    history_span_days: int = 0

    def to_dict(self) -> dict:
        return {
            "historical_count": self.historical_count,
            "recent_count": self.recent_count,
            "median_amount": self.median_amount,
            "p25_amount": self.p25_amount,
            "p75_amount": self.p75_amount,
            "p95_amount": self.p95_amount,
            "iqr": self.iqr,
            "max_amount": self.max_amount,
            "typical_range_low": self.typical_range_low,
            "typical_range_high": self.typical_range_high,
            "typical_hour_start": self.typical_hour_start,
            "typical_hour_end": self.typical_hour_end,
            "common_channels": self.common_channels,
            "known_beneficiaries_count": len(self.known_beneficiaries),
            "avg_daily_transactions": self.avg_daily_transactions,
            "history_span_days": self.history_span_days,
        }


def split_recent_historical(df: pd.DataFrame, recent_days: int = RECENT_WINDOW_DAYS):
    if df.empty:
        return df, df
    max_date = df["_parsed_date"].max()
    cutoff = max_date - timedelta(days=recent_days)
    historical = df[df["_parsed_date"] < cutoff].copy()
    recent = df[df["_parsed_date"] >= cutoff].copy()
    # Guard against tiny histories: if there's no real "historical" period,
    # treat everything except the very last transaction as historical.
    if historical.empty and len(df) > 1:
        historical = df.iloc[:-1].copy()
        recent = df.iloc[-1:].copy()
    return historical, recent


def build_baseline(historical_df: pd.DataFrame) -> CustomerBaseline:
    debit_mask = ~historical_df["transaction_type"].str.lower().isin(CREDIT_TYPES)
    debit_df = historical_df[debit_mask]
    amounts = debit_df["_parsed_amount"].tolist()

    med = median(amounts)
    p25 = percentile(amounts, 25)
    p75 = percentile(amounts, 75)
    p95 = percentile(amounts, 95)
    iqr = (p75 - p25) if (p75 is not None and p25 is not None) else None
    max_amt = max(amounts) if amounts else None

    hours = historical_df["_parsed_date"].apply(lambda d: d.hour).tolist()
    if hours:
        hour_low = int(pd.Series(hours).quantile(0.05))
        hour_high = int(pd.Series(hours).quantile(0.95))
    else:
        hour_low = hour_high = None

    channel_counts = historical_df["channel"].value_counts()
    common_channels = channel_counts.head(3).index.tolist()

    known_beneficiaries = set(b for b in historical_df["beneficiary_id"].tolist() if b)
    known_payees = set(p for p in historical_df["payee"].tolist() if p)

    span_days = 0
    if not historical_df.empty:
        span_days = max(1, (historical_df["_parsed_date"].max() - historical_df["_parsed_date"].min()).days)
    avg_daily = (len(historical_df) / span_days) if span_days else None

    typical_low = p25 if p25 is not None else (med * 0.25 if med else None)
    typical_high = p75 if p75 is not None else (med * 2 if med else None)

    return CustomerBaseline(
        historical_count=len(historical_df),
        recent_count=0,
        median_amount=med,
        p25_amount=p25,
        p75_amount=p75,
        p95_amount=p95,
        iqr=iqr,
        max_amount=max_amt,
        typical_range_low=typical_low,
        typical_range_high=typical_high,
        typical_hour_start=hour_low,
        typical_hour_end=hour_high,
        common_channels=common_channels,
        known_beneficiaries=known_beneficiaries,
        known_payees=known_payees,
        avg_daily_transactions=avg_daily,
        history_span_days=span_days,
    )
