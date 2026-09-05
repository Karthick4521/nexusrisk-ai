"""
NexusRisk AI - Gemini integration.

Gemini is responsible ONLY for language reasoning and explanation. It never
determines numerical rules or the review priority score - those come from
risk_engine.py. This module sends a structured, evidence-grounded context,
validates the JSON response, and falls back to a deterministic explanation
if the API key is missing, the call fails, or the response is invalid.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Any

from .config import GEMINI_API_KEY, GEMINI_MODEL


SYSTEM_INSTRUCTION = """You are an evidence-grounded banking investigation assistant.

Use ONLY the supplied investigation context. Do not invent transactions,
dates, amounts, beneficiaries, rules, evidence, or conclusions.

Distinguish clearly between:
1. Observed facts
2. Rule-based findings
3. AI interpretation
4. Recommendations
5. Uncertainty

Never state that fraud has occurred.

Every factual claim about a transaction must reference its transaction ID
when appropriate.

If evidence is insufficient, explicitly state that the available information
is insufficient and recommend human review.

Respond ONLY with a single JSON object matching this schema:

{
  "assessment": "NO_SIGNIFICANT_SIGNALS" | "REVIEW_RECOMMENDED" | "HIGH_PRIORITY_REVIEW",
  "summary": "string",
  "findings": [
    {
      "rule_id": "string",
      "title": "string",
      "severity": "string",
      "explanation": "string",
      "evidence_ids": ["string"]
    }
  ],
  "investigator_focus": ["string"],
  "uncertainties": ["string"],
  "human_review_required": true
}
"""


REQUIRED_KEYS = {
    "assessment",
    "summary",
    "findings",
    "investigator_focus",
    "uncertainties",
    "human_review_required",
}

VALID_ASSESSMENTS = {
    "NO_SIGNIFICANT_SIGNALS",
    "REVIEW_RECOMMENDED",
    "HIGH_PRIORITY_REVIEW",
}


def _build_user_context(case_context: Dict[str, Any]) -> str:
    return (
        "INVESTIGATION CONTEXT (JSON):\n"
        + json.dumps(case_context, indent=2, default=str)
        + "\n\nProduce the JSON response now."
    )


def _validate_response(data: Any) -> bool:
    if not isinstance(data, dict):
        return False

    if not REQUIRED_KEYS.issubset(data.keys()):
        return False

    if data["assessment"] not in VALID_ASSESSMENTS:
        return False

    if not isinstance(data["findings"], list):
        return False

    if not isinstance(data["investigator_focus"], list):
        return False

    if not isinstance(data["uncertainties"], list):
        return False

    if not isinstance(data["human_review_required"], bool):
        return False

    return True


def _extract_json(text: str) -> Any:
    text = text.strip()

    # Remove optional Markdown JSON fences.
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")

    return json.loads(text[start:end + 1])


def _deterministic_fallback(
    case_context: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:

    findings = case_context.get("risk_findings", [])
    score_info = case_context.get("score", {})
    category = score_info.get("category", "LOW")

    if category == "HIGH_PRIORITY_HUMAN_REVIEW":
        assessment = "HIGH_PRIORITY_REVIEW"
    elif category in ("HIGH", "MEDIUM"):
        assessment = "REVIEW_RECOMMENDED"
    else:
        assessment = "NO_SIGNIFICANT_SIGNALS"

    if findings:
        summary = (
            f"Deterministic analysis identified {len(findings)} risk signal(s) "
            f"({', '.join(sorted(set(f['rule_id'] for f in findings)))}) "
            f"with a review priority score of "
            f"{score_info.get('review_priority_score', 0)} ({category}). "
            f"AI explanation is currently unavailable ({reason}); "
            "deterministic transaction analysis has completed successfully."
        )
    else:
        summary = (
            "Deterministic analysis found no significant risk signals in the "
            "supplied transaction history. AI explanation is currently "
            f"unavailable ({reason}); deterministic transaction analysis "
            "has completed successfully."
        )

    focus = [
        f"Review evidence for {f['rule_id']} "
        f"({', '.join(f['evidence_ids'])})"
        for f in findings[:5]
    ]

    if not focus:
        focus = [
            "No specific transactions require focus based on deterministic analysis."
        ]

    return {
        "assessment": assessment,
        "summary": summary,
        "findings": findings,
        "investigator_focus": focus,
        "uncertainties": [
            "AI-generated natural-language interpretation is unavailable "
            "for this run; only deterministic rule findings are shown."
        ],
        "human_review_required": True,
        "ai_generated": False,
        "fallback_reason": reason,
    }


def generate_explanation(case_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a validated structured explanation dictionary.
    Always succeeds by using deterministic fallback if Gemini fails.
    """

    if not GEMINI_API_KEY:
        return _deterministic_fallback(
            case_context,
            "no GEMINI_API_KEY configured",
        )

    try:
        from google import genai
        from google.genai import types

        # Create the current Gemini API client.
        client = genai.Client(api_key=GEMINI_API_KEY)

        user_context = _build_user_context(case_context)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        raw_text = response.text

        if not raw_text:
            raise ValueError("Gemini returned an empty response")

        data = _extract_json(raw_text)

        if not _validate_response(data):
            return _deterministic_fallback(
                case_context,
                "Gemini response failed schema validation",
            )

        data["ai_generated"] = True

        return data

    except Exception as exc:
        return _deterministic_fallback(
            case_context,
            f"Gemini call failed ({type(exc).__name__}: {exc})",
        )