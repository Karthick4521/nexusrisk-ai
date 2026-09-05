"""
NexusRisk AI - Configuration
Loads environment variables and defines global constants.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Server ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8010"))  # changed from the original 8000

# --- Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# --- Paths ---
DATA_DIR = BASE_DIR / "data"
DEMO_DIR = DATA_DIR / "demo"
POLICY_DIR = DATA_DIR / "policies"
DB_PATH = BASE_DIR / "nexusrisk.db"

# --- Risk engine tuning ---
RECENT_WINDOW_DAYS = 14          # last N days treated as "recent" / evaluated
ODD_HOUR_START = 0                # 12:00 AM
ODD_HOUR_END = 5                  # 5:00 AM (exclusive)
BURST_WINDOW_HOURS = 24
BURST_MIN_COUNT = 2
LARGE_TXN_PERCENTILE = 95
LARGE_TXN_IQR_MULTIPLIER = 1.5
R05_MIN_DEVIATION_DIMENSIONS = 2
R06_LINK_WINDOW_HOURS = 48

# --- Scoring ---
RULE_WEIGHTS = {
    "R01": 30,  # Unusually Large Transaction
    "R02": 20,  # Transaction Burst
    "R03": 25,  # New Beneficiary
    "R04": 10,  # Odd-Hour Activity
    "R05": 20,  # Customer Behavior Deviation
    "R06": 15,  # Related Transaction Pattern
}

SCORE_THRESHOLDS = {
    "LOW": 0,
    "MEDIUM": 25,
    "HIGH": 55,
    "HIGH_PRIORITY_HUMAN_REVIEW": 90,
}

DISCLAIMER = (
    "NexusRisk AI identifies and explains potential transaction risk signals. "
    "It does not determine whether fraud has occurred. Final judgement belongs "
    "to a qualified human investigator."
)
