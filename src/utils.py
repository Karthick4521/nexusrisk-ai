"""
NexusRisk AI - Utility helpers
"""
from __future__ import annotations
import math
import uuid
from datetime import datetime
import numpy as np
import pandas as pd


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def safe_float(value, default=None):
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def clean_str(value) -> str:
    """Coerce NaN/None/'nan' strings into a clean empty string instead of the literal text 'nan'."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    s = str(value).strip()
    if s.lower() in ("nan", "none", "nat", ""):
        return ""
    return s


def parse_datetime(value):
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except (ValueError, TypeError):
            continue
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    except Exception:
        return None


def fmt_currency(amount) -> str:
    amount = safe_float(amount, 0.0)
    return f"\u20b9{amount:,.2f}"


def fmt_date(dt) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%d-%b-%Y %H:%M")


def percentile(values, p):
    arr = np.array([v for v in values if v is not None], dtype=float)
    if len(arr) == 0:
        return None
    return float(np.percentile(arr, p))


def median(values):
    arr = np.array([v for v in values if v is not None], dtype=float)
    if len(arr) == 0:
        return None
    return float(np.median(arr))
