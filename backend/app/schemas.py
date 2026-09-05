from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CodeSubmissionRequest(BaseModel):
    language: str = Field(..., examples=["python", "javascript", "java", "go"])
    code: str = Field(..., min_length=1)


class ReviewResponse(BaseModel):
    id: int
    language: str
    quality_rating: float
    bug_report: str
    best_practices: str
    optimization_notes: str
    matched_rules: List[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewHistoryItem(BaseModel):
    id: int
    language: str
    quality_rating: float
    created_at: datetime

    class Config:
        from_attributes = True


class HistoricalRuleOut(BaseModel):
    id: int
    rule_type: str
    description: str

    class Config:
        from_attributes = True


class IngestSummary(BaseModel):
    rules_ingested: int
    message: str
