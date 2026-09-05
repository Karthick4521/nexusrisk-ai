"""
NexusRisk AI - Transaction CSV validation and cleaning.

Handles the messy realities of uploaded CSVs without ever crashing:
empty files, bad dates, bad amounts, missing columns, duplicate IDs,
duplicate rows, NaN coercion, negative amounts, tiny histories.
"""
from __future__ import annotations
import io
from dataclasses import dataclass, field
from typing import List
import pandas as pd

from .utils import clean_str, parse_datetime, safe_float, new_id

REQUIRED_ANY_OF = ["description", "payee"]
REQUIRED_COLS = ["date", "amount", "channel"]
OPTIONAL_COLS = ["transaction_id", "transaction_type", "beneficiary_id", "description", "payee"]
ALL_KNOWN_COLS = REQUIRED_COLS + OPTIONAL_COLS


@dataclass
class ValidationResult:
    ok: bool
    dataframe: pd.DataFrame
    messages: List[str] = field(default_factory=list)
    rows_in: int = 0
    rows_out: int = 0
    error: str | None = None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def validate_and_clean(raw_bytes: bytes) -> ValidationResult:
    messages: List[str] = []

    if raw_bytes is None or len(raw_bytes.strip()) == 0:
        return ValidationResult(
            ok=False, dataframe=pd.DataFrame(), messages=["The uploaded file is empty."],
            error="EMPTY_FILE",
        )

    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:
        return ValidationResult(
            ok=False, dataframe=pd.DataFrame(),
            messages=[f"The file could not be parsed as CSV: {exc}"],
            error="MALFORMED_CSV",
        )

    if df.empty:
        return ValidationResult(
            ok=False, dataframe=pd.DataFrame(),
            messages=["The CSV contains a header but no transaction rows."],
            error="EMPTY_FILE",
        )

    df = _normalize_columns(df)
    rows_in = len(df)

    missing_required = [c for c in REQUIRED_COLS if c not in df.columns]
    has_desc_or_payee = any(c in df.columns for c in REQUIRED_ANY_OF)
    if not has_desc_or_payee:
        missing_required.append("description_or_payee")

    if missing_required:
        return ValidationResult(
            ok=False, dataframe=pd.DataFrame(),
            messages=[f"Required column(s) missing: {', '.join(missing_required)}."],
            error="MISSING_REQUIRED_COLUMNS",
        )

    # Ensure optional columns exist so downstream code never KeyErrors
    for c in OPTIONAL_COLS:
        if c not in df.columns:
            df[c] = None

    if "description" not in df.columns:
        df["description"] = None
    if "payee" not in df.columns:
        df["payee"] = None

    # --- Clean transaction_id: assign synthetic IDs where missing, dedupe ---
    df["transaction_id"] = df["transaction_id"].apply(clean_str)
    seen_ids = set()
    new_ids = []
    for tid in df["transaction_id"]:
        if not tid:
            tid = new_id("TXN")
        if tid in seen_ids:
            tid = f"{tid}_{new_id('DUP')}"
        seen_ids.add(tid)
        new_ids.append(tid)
    dupes_found = len(df) - len(set(df["transaction_id"].tolist()) - {""})
    df["transaction_id"] = new_ids

    # --- Parse dates ---
    df["_parsed_date"] = df["date"].apply(parse_datetime)
    bad_dates = int(df["_parsed_date"].isna().sum())
    if bad_dates:
        messages.append(f"{bad_dates} row(s) contain invalid dates and were excluded from analysis.")
    df = df[df["_parsed_date"].notna()].copy()

    # --- Parse amounts ---
    df["_parsed_amount"] = df["amount"].apply(lambda v: safe_float(v, None))
    bad_amounts = int(df["_parsed_amount"].isna().sum())
    if bad_amounts:
        messages.append(f"{bad_amounts} row(s) contain missing or invalid amounts and were excluded from analysis.")
    df = df[df["_parsed_amount"].notna()].copy()

    neg_count = int((df["_parsed_amount"] < 0).sum())
    if neg_count:
        messages.append(f"{neg_count} row(s) have negative amounts (treated as debit-reversal/credit context, not excluded).")

    # --- Clean text fields ---
    df["description"] = df["description"].apply(clean_str)
    df["payee"] = df["payee"].apply(clean_str)
    df["channel"] = df["channel"].apply(lambda v: clean_str(v) or "Unknown")
    df["transaction_type"] = df["transaction_type"].apply(lambda v: clean_str(v) or "debit")
    df["beneficiary_id"] = df["beneficiary_id"].apply(clean_str)

    missing_payee_desc = int(((df["description"] == "") & (df["payee"] == "")).sum())
    if missing_payee_desc:
        messages.append(f"{missing_payee_desc} row(s) have neither description nor payee; labeled as 'Unknown'.")
        mask = (df["description"] == "") & (df["payee"] == "")
        df.loc[mask, "description"] = "Unknown"

    missing_beneficiary = int((df["beneficiary_id"] == "").sum())
    if missing_beneficiary:
        # fall back to payee/description as a pseudo-beneficiary key so grouping still works
        mask = df["beneficiary_id"] == ""
        df.loc[mask, "beneficiary_id"] = (
            "PSEUDO_" + (df.loc[mask, "payee"].replace("", "UNKNOWN") + "_" + df.loc[mask, "description"].replace("", "UNKNOWN"))
        )
        messages.append(f"{missing_beneficiary} row(s) had no beneficiary_id; a derived key was used for grouping.")

    # --- Duplicate full rows ---
    dedupe_cols = ["date", "amount", "channel", "payee", "description", "beneficiary_id"]
    before = len(df)
    df = df.drop_duplicates(subset=dedupe_cols, keep="first")
    dup_rows = before - len(df)
    if dup_rows:
        messages.append(f"{dup_rows} duplicate row(s) were removed.")

    if dupes_found > 0:
        messages.append(f"{dupes_found} duplicate transaction_id value(s) were detected and re-keyed.")

    df = df.sort_values("_parsed_date").reset_index(drop=True)

    if len(df) == 0:
        return ValidationResult(
            ok=False, dataframe=df, messages=messages + ["No valid rows remained after cleaning."],
            rows_in=rows_in, rows_out=0, error="NO_VALID_ROWS",
        )

    if len(df) == 1:
        messages.append("Only a single valid transaction is available; baseline statistics will be minimal and low-confidence.")
    elif len(df) < 10:
        messages.append("Very small transaction history; baseline statistics may be low-confidence.")

    return ValidationResult(
        ok=True, dataframe=df, messages=messages, rows_in=rows_in, rows_out=len(df),
    )
