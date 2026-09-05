"""
Database layer.

Production target: Cloud SQL for PostgreSQL, connected from Cloud Run
via the Cloud SQL Auth Proxy unix socket (CLOUD_SQL_CONNECTION_NAME).

For local development / grading environments without a live Cloud SQL
instance, the app transparently falls back to a local SQLite file so
the whole system still runs end to end.
"""

from datetime import datetime

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Float,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from app.config import settings


def _build_database_url() -> str:
    if settings.CLOUD_SQL_CONNECTION_NAME and not settings.USE_SQLITE_FALLBACK:
        # Cloud Run -> Cloud SQL via unix socket created by the Auth Proxy sidecar
        socket_path = f"/cloudsql/{settings.CLOUD_SQL_CONNECTION_NAME}"
        return (
            f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASS}"
            f"@/{settings.DB_NAME}?host={socket_path}"
        )
    if not settings.USE_SQLITE_FALLBACK:
        return (
            f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASS}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )
    return "sqlite:///./code_reviewer_local.db"


DATABASE_URL = _build_database_url()

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """Represents an authenticated user (identity comes from Firebase / Identity Platform)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String(128), unique=True, index=True, nullable=False)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")


class Review(Base):
    """A single code review session, persisted for historical tracking."""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    language = Column(String(64), nullable=False)
    code_snippet = Column(Text, nullable=False)

    quality_rating = Column(Float, nullable=False)
    bug_report = Column(Text, nullable=True)
    best_practices = Column(Text, nullable=True)
    optimization_notes = Column(Text, nullable=True)
    raw_model_response = Column(Text, nullable=True)

    matched_rule_ids = Column(String(255), nullable=True)  # comma separated ids used for grounding
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reviews")


class HistoricalRule(Base):
    """
    Historical review knowledge ingested from the CSV dataset
    (id, type, description). Embeddings are stored so we can run
    similarity search at review time to ground Gemini's output.
    """

    __tablename__ = "historical_rules"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, nullable=False)  # original id from CSV
    rule_type = Column(String(64), nullable=False)  # formatting | performance | security | ...
    description = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=True)  # JSON-encoded float vector


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
