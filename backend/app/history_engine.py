"""
Historical Learning Engine.

Ingests the historical review dataset (CSV: id, type, description),
embeds each rule with Vertex AI, and stores both the raw rule and its
embedding in Cloud SQL (HistoricalRule table).

At review time, the user's submitted code is embedded and compared
against every stored rule embedding using cosine similarity, so the
top-K most relevant historical rules can be injected into the Gemini
prompt for grounding.

Note: for the scale of this dataset (hundreds-thousands of rules),
in-process cosine similarity over vectors pulled from Cloud SQL is
fast and simple. For very large rule sets this same interface can be
swapped to call Vertex AI Vector Search (matching engine) without
changing any calling code.
"""

import io
import json
from typing import List, Dict, Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.database import HistoricalRule
from app.gemini_service import embed_texts_batch, embed_text
from app.config import settings

REQUIRED_COLUMNS = {"id", "type", "description"}


def ingest_csv(db: Session, csv_bytes: bytes) -> int:
    """
    Parses the historical rules CSV, embeds every description in a
    batch call, and persists rows + embeddings to Cloud SQL.
    Returns the number of rules ingested.
    """
    df = pd.read_csv(io.BytesIO(csv_bytes))
    df.columns = [c.strip().lower() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    descriptions = df["description"].astype(str).tolist()
    embeddings = embed_texts_batch(descriptions)

    count = 0
    for row, vector in zip(df.itertuples(index=False), embeddings):
        rule = HistoricalRule(
            source_id=int(row.id),
            rule_type=str(row.type).strip().lower(),
            description=str(row.description).strip(),
            embedding_json=json.dumps(vector),
        )
        db.add(rule)
        count += 1

    db.commit()
    return count


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def retrieve_relevant_rules(
    db: Session, code: str, top_k: int = None
) -> List[Dict[str, Any]]:
    """
    Embeds the submitted code and returns the top_k most semantically
    similar historical rules, used to ground the Gemini review prompt.
    """
    top_k = top_k or settings.TOP_K_HISTORICAL_RULES

    all_rules = db.query(HistoricalRule).all()
    if not all_rules:
        return []

    query_vector = np.array(embed_text(code))

    scored = []
    for rule in all_rules:
        if not rule.embedding_json:
            continue
        rule_vector = np.array(json.loads(rule.embedding_json))
        score = _cosine_similarity(query_vector, rule_vector)
        scored.append((score, rule))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    return [
        {
            "id": rule.source_id,
            "rule_type": rule.rule_type,
            "description": rule.description,
            "similarity": round(score, 4),
        }
        for score, rule in top
    ]
