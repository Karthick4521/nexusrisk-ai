"""
NexusRisk AI - FastAPI application entry point.

Run with:
    python app.py

Serves the frontend dashboard and all API endpoints from a single process.
NOTE: the default port was changed from 8000 to 8010 (see src/config.py,
override with the PORT environment variable / .env file).
"""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from src.config import HOST, PORT, DEMO_DIR, BASE_DIR, DISCLAIMER
from src.database import init_db, get_investigation
from src.investigation_service import run_investigation
from src.evidence_engine import build_evidence_viewer
from src.risk_engine import RiskFinding
from src.baseline import CustomerBaseline
from src.report_generator import generate_report_text

FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="NexusRisk AI", description="Banking Transaction Risk Investigation Assistant")


@app.on_event("startup")
def _startup():
    init_db()


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "NexusRisk AI", "disclaimer": DISCLAIMER}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), customer_id: str = Form("CUST001")):
    try:
        raw_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {exc}")

    result = run_investigation(raw_bytes, customer_id)
    if not result["ok"]:
        # Return 200 with a structured validation failure, not a 500 - the UI
        # needs to display validation messages gracefully, never crash.
        return {"ok": False, "validation_error": result["error"], "messages": result["messages"]}
    return result


@app.post("/api/analyze-demo")
def analyze_demo(case: str = Form("normal_case")):
    filename = "normal_case.csv" if case == "normal_case" else "difficult_case.csv"
    demo_path = DEMO_DIR / filename
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail=f"Demo file {filename} not found")
    raw_bytes = demo_path.read_bytes()
    customer_id = "CUST-DEMO-NORMAL" if case == "normal_case" else "CUST-DEMO-DIFFICULT"
    result = run_investigation(raw_bytes, customer_id)
    if not result["ok"]:
        return {"ok": False, "validation_error": result["error"], "messages": result["messages"]}
    return result


# ---------------------------------------------------------------------------
# Investigation retrieval
# ---------------------------------------------------------------------------

@app.get("/api/investigation/{investigation_id}")
def get_investigation_endpoint(investigation_id: str):
    investigation = get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


@app.get("/api/evidence/{investigation_id}/{transaction_id}")
def get_evidence(investigation_id: str, transaction_id: str):
    investigation = get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    import pandas as pd
    txns = investigation["transactions"]
    if not txns:
        raise HTTPException(status_code=404, detail="No transactions stored for this investigation")

    df = pd.DataFrame(txns)
    df["_parsed_date"] = pd.to_datetime(df["date"])
    df["_parsed_amount"] = df["amount"]
    df["transaction_id"] = df["transaction_id"]

    findings = [
        RiskFinding(
            rule_id=f["rule_id"], title=f["title"], severity=f["severity"],
            explanation=f["explanation"], evidence_ids=f["evidence_ids"], details=f.get("details", {}),
        )
        for f in investigation["risk_findings"]
    ]

    baseline_dict = investigation["baseline"]
    baseline = CustomerBaseline(
        historical_count=baseline_dict.get("historical_count", 0),
        recent_count=baseline_dict.get("recent_count", 0),
        median_amount=baseline_dict.get("median_amount"),
        p25_amount=baseline_dict.get("p25_amount"),
        p75_amount=baseline_dict.get("p75_amount"),
        p95_amount=baseline_dict.get("p95_amount"),
        iqr=baseline_dict.get("iqr"),
        max_amount=baseline_dict.get("max_amount"),
        typical_range_low=baseline_dict.get("typical_range_low"),
        typical_range_high=baseline_dict.get("typical_range_high"),
        typical_hour_start=baseline_dict.get("typical_hour_start"),
        typical_hour_end=baseline_dict.get("typical_hour_end"),
        common_channels=baseline_dict.get("common_channels", []),
    )

    viewer = build_evidence_viewer(transaction_id, df, findings, baseline)
    if viewer is None:
        raise HTTPException(status_code=404, detail="Transaction not found in this investigation")
    return viewer


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

@app.post("/api/generate-report")
def generate_report(investigation_id: str = Form(...)):
    investigation = get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    report_text = generate_report_text(investigation)
    return PlainTextResponse(report_text)


if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=False)
