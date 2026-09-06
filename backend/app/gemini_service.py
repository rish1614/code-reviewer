"""
Vertex AI / Gemini integration.
"""

import json
import re
from typing import List, Dict, Any

import vertexai
from vertexai.generative_models import GenerativeModel
from vertexai.language_models import TextEmbeddingModel

from app.config import settings

_initialized = False


def _ensure_init():
    global _initialized
    if not _initialized:
        vertexai.init(project=settings.GCP_PROJECT_ID, location=settings.GCP_REGION)
        _initialized = True


def _mock_embedding(text: str) -> List[float]:
    """Deterministic fake embedding so mock mode still supports similarity search."""
    return [float((hash(text) >> i) % 10) for i in range(16)]


def embed_text(text: str) -> List[float]:
    if settings.USE_MOCK_AI:
        return _mock_embedding(text)
    _ensure_init()
    model = TextEmbeddingModel.from_pretrained(settings.EMBEDDING_MODEL)
    embeddings = model.get_embeddings([text])
    return embeddings[0].values


def embed_texts_batch(texts: List[str]) -> List[List[float]]:
    if settings.USE_MOCK_AI:
        return [_mock_embedding(t) for t in texts]
    _ensure_init()
    model = TextEmbeddingModel.from_pretrained(settings.EMBEDDING_MODEL)
    embeddings = model.get_embeddings(texts)
    return [e.values for e in embeddings]


_JSON_SCHEMA_INSTRUCTIONS = """
You are an expert, multi-language senior code reviewer.
Analyze the submitted code and respond with STRICT JSON ONLY
(no markdown fences, no commentary outside the JSON object) in
exactly this shape:

{
  "quality_rating": <number from 1 to 10, one decimal allowed>,
  "bug_report": "<clear description of bugs / correctness issues found, or 'No significant bugs found.'>",
  "best_practices": "<architectural and style best-practice guidance>",
  "optimization_notes": "<performance / optimization insights>",
  "applied_historical_rules": [<list of the historical rule ids you actually used to inform your review, as integers>]
}
"""


def _build_prompt(language: str, code: str, historical_rules: List[Dict[str, Any]]) -> str:
    rules_block = "\n".join(
        f'- id={r["id"]} [{r["rule_type"]}]: {r["description"]}' for r in historical_rules
    ) or "No historical rules available."

    return f"""{_JSON_SCHEMA_INSTRUCTIONS}

LANGUAGE: {language}

RELEVANT HISTORICAL REVIEW RULES (use these to ground and enrich your review
where applicable; cite their ids in applied_historical_rules only if genuinely relevant):
{rules_block}

SOURCE CODE TO REVIEW:
```{language}
{code}
```
"""


def _mock_review(historical_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Canned review used when USE_MOCK_AI=true."""
    applied = [r["id"] for r in historical_rules[:2]]
    return {
        "quality_rating": 6.5,
        "bug_report": "MOCK MODE: no live model call was made. Example finding: "
        "unsanitized input reaches a query/string build step — verify input handling.",
        "best_practices": "MOCK MODE: consider adding type hints, docstrings, and "
        "consistent naming conventions.",
        "optimization_notes": "MOCK MODE: look for repeated work inside loops that "
        "could be cached or batched.",
        "applied_historical_rules": applied,
        "_raw_model_response": "mock mode - no real Gemini call made",
    }


def review_code(
    language: str, code: str, historical_rules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if settings.USE_MOCK_AI:
        return _mock_review(historical_rules)

    _ensure_init()
    model = GenerativeModel(settings.GEMINI_MODEL)
    prompt = _build_prompt(language, code, historical_rules)

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        },
    )

    raw_text = response.text
    parsed = _safe_parse_json(raw_text)
    parsed["_raw_model_response"] = raw_text
    return parsed


def _safe_parse_json(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```json\s*|```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "quality_rating": 5.0,
            "bug_report": "Model response could not be parsed as JSON. Raw text preserved.",
            "best_practices": "N/A",
            "optimization_notes": "N/A",
            "applied_historical_rules": [],
        }
