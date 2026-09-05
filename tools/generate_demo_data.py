"""
NexusRisk AI - Synthetic demo data generator.

Run with:  python tools/generate_demo_data.py

Regenerates data/demo/normal_case.csv and data/demo/difficult_case.csv.
All data is synthetic; no real customer information is used.
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_DIR = BASE_DIR / "data" / "demo"
DEMO_DIR.mkdir(parents=True, exist_ok=True)

FIELDNAMES = [
    "transaction_id", "date", "description", "payee", "amount",
    "channel", "transaction_type", "beneficiary_id",
]

PAYEES = [
    ("Grocery Mart", "BNF001"), ("City Utilities", "BNF002"), ("Landlord Co-op", "BNF003"),
    ("Food Court", "BNF004"), ("Fuel Station", "BNF005"), ("Mobile Recharge", "BNF006"),
    ("Streaming Service", "BNF007"),
]

CHANNELS_NORMAL = ["Card", "Card", "Card", "UPI", "Net Banking"]


def _row(idx, dt, desc, payee, amount, channel, ttype, bnf):
    return {
        "transaction_id": f"TXN{idx:05d}",
        "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "description": desc,
        "payee": payee,
        "amount": round(amount, 2),
        "channel": channel,
        "transaction_type": ttype,
        "beneficiary_id": bnf,
    }


def generate_normal_case():
    random.seed(42)
    rows = []
    start = datetime(2026, 4, 1, 9, 0, 0)
    idx = 1
    day = start
    for month in range(4):
        for d in range(30):
            current_day = start + timedelta(days=month * 30 + d)
            # salary once a month
            if d == 1:
                rows.append(_row(idx, current_day.replace(hour=10, minute=0), "Salary Credit",
                                  "Employer Pvt Ltd", 65000.0, "Net Banking", "salary", "BNF000"))
                idx += 1
            # 1-3 routine transactions per day, most days
            if random.random() < 0.7:
                for _ in range(random.randint(1, 3)):
                    payee, bnf = random.choice(PAYEES)
                    hour = random.randint(8, 21)
                    minute = random.randint(0, 59)
                    amount = random.uniform(150, 6500)
                    channel = random.choice(CHANNELS_NORMAL)
                    dt = current_day.replace(hour=hour, minute=minute)
                    rows.append(_row(idx, dt, f"Payment to {payee}", payee, amount, channel, "debit", bnf))
                    idx += 1
            # rent once a month
            if d == 3:
                rows.append(_row(idx, current_day.replace(hour=11, minute=0), "Monthly Rent",
                                  "Landlord Co-op", 18000.0, "Net Banking", "debit", "BNF003"))
                idx += 1
    return rows


def generate_difficult_case():
    rows = generate_normal_case()
    # continue idx numbering from where normal case left off, but keep IDs distinct (TXN9xxx cluster)
    last_date = datetime(2026, 4, 1, 9, 0, 0) + timedelta(days=4 * 30 - 1)

    cluster_day = last_date + timedelta(days=2)

    # TXN9042 - unusually large transfer to a brand-new beneficiary, odd hour
    rows.append(_row(9042, cluster_day.replace(hour=2, minute=13), "Urgent Transfer",
                      "ABC Services", 75000.0, "Bank Transfer", "debit", "BNF009"))
    # TXN9043 - second large transaction to same new beneficiary within hours (burst)
    rows.append(_row(9043, cluster_day.replace(hour=5, minute=40), "Urgent Transfer 2",
                      "ABC Services", 80000.0, "Bank Transfer", "debit", "BNF009"))
    # TXN9044 - third large transaction, still within 24h window
    rows.append(_row(9044, (cluster_day + timedelta(hours=18)).replace(minute=5), "Urgent Transfer 3",
                      "ABC Services", 95000.0, "Bank Transfer", "debit", "BNF009"))

    rows.sort(key=lambda r: r["date"])
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    normal_rows = generate_normal_case()
    difficult_rows = generate_difficult_case()
    write_csv(DEMO_DIR / "normal_case.csv", normal_rows)
    write_csv(DEMO_DIR / "difficult_case.csv", difficult_rows)
    print(f"normal_case.csv: {len(normal_rows)} rows")
    print(f"difficult_case.csv: {len(difficult_rows)} rows")
