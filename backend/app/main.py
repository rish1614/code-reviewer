"""
The 24/7 Intelligent Code Reviewer -- FastAPI backend.

Endpoints:
  POST /api/v1/reviews            -> submit code, get a structured review
  GET  /api/v1/reviews             -> get the authenticated user's review history
  GET  /api/v1/reviews/{id}        -> get one full review
  POST /api/v1/historical-rules/ingest  -> upload the historical CSV dataset
  GET  /api/v1/historical-rules    -> list ingested historical rules
  GET  /healthz                    -> Cloud Run health check
"""

import logging
from typing import List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import init_db, get_db, User, Review, HistoricalRule
from app.auth import get_current_user
from app.schemas import (
    CodeSubmissionRequest,
    ReviewResponse,
    ReviewHistoryItem,
    HistoricalRuleOut,
    IngestSummary,
)
from app.history_engine import ingest_csv, retrieve_relevant_rules
from app.gemini_service import review_code

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("code-reviewer")

app = FastAPI(
    title="The 24/7 Intelligent Code Reviewer",
    description="Always-on, multi-language, Gemini-powered code review engine.",
    version="1.0.0",
)

# Allow the frontend (served separately, e.g. Firebase Hosting / Cloud Storage) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your deployed frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized. Ready to serve reviews.")


@app.get("/healthz", tags=["infra"])
def health_check():
    return {"status": "ok"}


@app.post("/api/v1/reviews", response_model=ReviewResponse, tags=["reviews"])
def submit_code_for_review(
    payload: CodeSubmissionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(payload.code) > settings.MAX_CODE_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Code exceeds max allowed size of {settings.MAX_CODE_CHARS} characters.",
        )

    # 1. Retrieve semantically relevant historical rules to ground the review.
    relevant_rules = retrieve_relevant_rules(db, code=payload.code)

    # 2. Call Gemini (Vertex AI) for the structured review.
    result = review_code(
        language=payload.language, code=payload.code, historical_rules=relevant_rules
    )

    applied_ids = result.get("applied_historical_rules", []) or []

    # 3. Persist the review for historical tracking / growth analytics.
    review = Review(
        user_id=user.id,
        language=payload.language,
        code_snippet=payload.code,
        quality_rating=float(result.get("quality_rating", 5.0)),
        bug_report=result.get("bug_report", ""),
        best_practices=result.get("best_practices", ""),
        optimization_notes=result.get("optimization_notes", ""),
        raw_model_response=result.get("_raw_model_response", ""),
        matched_rule_ids=",".join(str(i) for i in applied_ids),
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    return ReviewResponse(
        id=review.id,
        language=review.language,
        quality_rating=review.quality_rating,
        bug_report=review.bug_report,
        best_practices=review.best_practices,
        optimization_notes=review.optimization_notes,
        matched_rules=[str(i) for i in applied_ids],
        created_at=review.created_at,
    )


@app.get("/api/v1/reviews", response_model=List[ReviewHistoryItem], tags=["reviews"])
def get_review_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persistent session history: track a user's development growth over time."""
    reviews = (
        db.query(Review)
        .filter(Review.user_id == user.id)
        .order_by(Review.created_at.desc())
        .all()
    )
    return reviews


@app.get("/api/v1/reviews/{review_id}", response_model=ReviewResponse, tags=["reviews"])
def get_review_detail(
    review_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = (
        db.query(Review)
        .filter(Review.id == review_id, Review.user_id == user.id)
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    matched_ids = review.matched_rule_ids.split(",") if review.matched_rule_ids else []
    return ReviewResponse(
        id=review.id,
        language=review.language,
        quality_rating=review.quality_rating,
        bug_report=review.bug_report,
        best_practices=review.best_practices,
        optimization_notes=review.optimization_notes,
        matched_rules=[m for m in matched_ids if m],
        created_at=review.created_at,
    )


@app.post(
    "/api/v1/historical-rules/ingest",
    response_model=IngestSummary,
    tags=["historical-learning"],
)
def ingest_historical_rules(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uploads the historical review dataset CSV (id, type, description),
    embeds each rule via Vertex AI, and stores it for use as grounding
    context in future reviews.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = file.file.read()
    try:
        count = ingest_csv(db, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestSummary(
        rules_ingested=count,
        message=f"Successfully ingested {count} historical rules.",
    )


@app.get(
    "/api/v1/historical-rules",
    response_model=List[HistoricalRuleOut],
    tags=["historical-learning"],
)
def list_historical_rules(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rules = db.query(HistoricalRule).all()
    return [
        HistoricalRuleOut(id=r.id, rule_type=r.rule_type, description=r.description)
        for r in rules
    ]
