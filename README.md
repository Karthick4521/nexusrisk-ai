# NexusRisk AI

**From transaction data to explainable investigation — with evidence at every step.**

Hackathon Track: `PS06 — Banking: Transaction Risk Investigation Assistant`

---

## Problem Statement

Banks review thousands of customer transaction histories. Most transactions are
routine; a small percentage may need closer attention. The real challenge isn't
just detecting an unusual transaction — it's explaining **why** it's unusual,
showing the **exact evidence**, comparing it against the customer's own normal
behavior, connecting related transactions, and telling an investigator what to
examine next.

## Solution

NexusRisk AI is an AI-powered banking investigation copilot that turns a raw
customer transaction history into a transparent, evidence-grounded
investigation workflow:

```
CSV Upload → Validation → Customer Baseline → Deterministic Risk Engine (R01-R06)
  → Evidence Chain → Local Policy Retrieval → Gemini Explanation
  → Investigation Report → Human Investigator
```

**NexusRisk AI never claims fraud has occurred.** It flags, explains, connects,
proves, recommends, and escalates — final judgement always belongs to a
qualified human investigator.

## Features

- CSV upload + "Load Demo Case" (normal / difficult), with graceful validation
- Customer-specific behavioral baseline (median, percentiles, IQR, hours, channels)
- Six deterministic risk rules (R01–R06), fully computed in Python — never by the LLM
- Transparent Review Priority Score (LOW / MEDIUM / HIGH / HIGH_PRIORITY_HUMAN_REVIEW)
- Evidence chain: every finding traces back to real transaction IDs, never fabricated
- Per-transaction evidence viewer with baseline comparison
- Local TF-IDF policy retrieval (no external vector DB), fails safe to `[]`
- Gemini-generated, evidence-grounded explanation with strict JSON schema
  validation and a fully-working deterministic fallback if no API key / call fails
- Investigator-ready report generation, always including the human-review disclaimer
- Interactive dashboard: baseline cards, risk signal list, evidence tree,
  transaction timeline chart, normal-vs-flagged comparison chart

## Architecture

| Layer | File | Responsibility |
|---|---|---|
| API | `app.py` | FastAPI app, all endpoints, serves frontend |
| Validation | `src/transaction_parser.py` | CSV cleaning: empty files, bad dates/amounts, dupes, missing cols, NaN coercion |
| Baseline | `src/baseline.py` | Customer behavioral baseline (recent-vs-historical split, debit-only stats) |
| Risk Engine | `src/risk_engine.py` | Deterministic R01–R06 rules + transparent scoring |
| Evidence | `src/evidence_engine.py` | Evidence chain tree + per-transaction viewer payload |
| Policy RAG | `src/retrieval.py` | Local TF-IDF retrieval over `data/policies/*.txt` |
| Gemini | `src/gemini_client.py` | Structured prompt, JSON-schema validation, deterministic fallback |
| Report | `src/report_generator.py` | Investigator-ready text report |
| Orchestration | `src/investigation_service.py` | Ties every layer together per request |
| Persistence | `src/database.py` | SQLite: customers, transactions, investigations, risk_findings, evidence_links |
| Frontend | `frontend/*` | Vanilla JS + Chart.js dashboard, no build step |

## Technology Stack

- **Backend:** Python 3.11, FastAPI, Uvicorn
- **Data:** Pandas, NumPy, SQLite
- **AI:** Gemini API (`google-generativeai`), with a fully deterministic fallback
- **Retrieval:** scikit-learn TF-IDF (local, no external vector DB)
- **Frontend:** HTML, CSS, vanilla JavaScript, Chart.js (via CDN)

## Folder Structure

```
nexusrisk-ai/
├── app.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── data/
│   ├── demo/
│   │   ├── normal_case.csv
│   │   └── difficult_case.csv
│   └── policies/
│       ├── risk_rules.txt
│       ├── investigation_policy.txt
│       └── escalation_policy.txt
├── src/
│   ├── config.py
│   ├── database.py
│   ├── transaction_parser.py
│   ├── baseline.py
│   ├── risk_engine.py
│   ├── evidence_engine.py
│   ├── retrieval.py
│   ├── gemini_client.py
│   ├── investigation_service.py
│   ├── report_generator.py
│   └── utils.py
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── tools/
    └── generate_demo_data.py
```

## Installation

```bash
unzip NexusRisk_AI.zip && cd nexusrisk-ai
pip install -r requirements.txt
```

## Environment Configuration

Copy `.env.example` to `.env` and fill in values as needed:

```bash
cp .env.example .env
```

- `GEMINI_API_KEY` — optional. Without it, the app runs entirely on the
  deterministic fallback path (still fully functional).
- `HOST` / `PORT` — **the port has been changed from the original spec's 8000
  to 8010** to avoid conflicts with other local services. Override either in
  `.env` if you need something else.

## Running the Application

```bash
python app.py
```

Then open: **http://localhost:8010**

One command, no separate frontend build step, no second terminal.

## Demo Instructions

1. Click **Load Normal Case** → expect `NO SIGNIFICANT RISK SIGNALS` (0 findings, LOW).
2. Click **Load Difficult Case** → expect `REVIEW RECOMMENDED` / `HIGH PRIORITY HUMAN REVIEW`
   with R01, R02, R03, R05, R06 firing on the injected transaction cluster.
3. Click any transaction ID in the **Evidence Chain** to open the **Evidence Viewer**.
4. Review the **Gemini Investigation Summary** (or deterministic fallback if no API key).
5. Click **Generate Investigation Report** for a full investigator-ready text report.

To regenerate the synthetic demo CSVs:

```bash
python tools/generate_demo_data.py
```

## Risk Rules (R01–R06)

| Rule | Name | Weight | Summary |
|---|---|---|---|
| R01 | Unusually Large Transaction | +30 | Amount far above the customer's own historical percentile/IQR range |
| R02 | Transaction Burst | +20 | Multiple high-value transactions within 24 hours |
| R03 | New Beneficiary | +25 | Beneficiary never seen in historical data |
| R04 | Odd-Hour Activity | +10 | Transaction between 12:00 AM–5:00 AM (timing signal only) |
| R05 | Customer Behavior Deviation | +20 | ≥2 simultaneous deviation dimensions (amount/channel/timing/beneficiary) |
| R06 | Related Transaction Pattern | +15 | Links transactions **already** flagged by R01/R02/R03/R05 that are also time/beneficiary-linked |

Scores map to: `LOW` (0–24) / `MEDIUM` (25–54) / `HIGH` (55–89) / `HIGH_PRIORITY_HUMAN_REVIEW` (90+).
This is a **Review Priority Score**, never described as a probability of fraud.

## Evidence Chain

Every finding is traceable to real transaction IDs from the uploaded data —
never fabricated:

```
HIGH PRIORITY HUMAN REVIEW
 ├── R01 Unusually Large Transaction
 │     └── TXN09042
 ├── R02 Transaction Burst
 │     ├── TXN09042
 │     ├── TXN09043
 │     └── TXN09044
 └── R06 Related Transaction Pattern
       └── TXN09042 → TXN09043 → TXN09044
```

## Gemini Architecture

Gemini is used **only** for language reasoning, explanation, and
recommendations — it never computes statistics or decides which rules fire.
It receives a structured JSON context (customer baseline, deterministic
findings, evidence transaction IDs, related transaction groups, relevant local
policy excerpts) and must respond with a strict JSON schema separating:

1. Observed facts
2. Rule-based findings
3. AI interpretation
4. Recommendations
5. Uncertainty

If the API key is missing, the call fails, or the response fails schema
validation, `src/gemini_client.py` falls back to a fully deterministic,
rule-based summary — the app never crashes and never blocks on Gemini.

## RAG Architecture

`src/retrieval.py` chunks `data/policies/*.txt` (risk rule definitions,
investigation principles, escalation policy) and retrieves the most relevant
chunks via local TF-IDF cosine similarity (scikit-learn) — no external vector
database. If retrieval fails for any reason, it fails safe to an empty list
and the rest of the pipeline continues unaffected.

## Safety and Limitations

- Synthetic demo data only — no real customer information.
- The system never states that fraud has occurred.
- Every finding must trace to a real transaction ID; evidence is never invented.
- Missing/insufficient information is explicitly surfaced as an uncertainty.
- API keys are never hardcoded or logged; `.env` is git-ignored.

## Human-in-the-Loop

> NexusRisk AI identifies and explains potential transaction risk signals.
> It does not determine whether fraud has occurred. Final judgement belongs
> to a qualified human investigator.

This notice is shown on every case and included in every generated report.

---

`TRACK_ID=PS06`

Demo video: `<ADD DEMO VIDEO LINK>`
