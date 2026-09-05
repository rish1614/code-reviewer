"""
Central configuration for The 24/7 Intelligent Code Reviewer.
All values are read from environment variables so the same image
can be deployed to Cloud Run across dev / staging / prod without
code changes.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- GCP project settings ---
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "your-gcp-project-id")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")

    # --- Vertex AI / Gemini ---
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro-002")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-004")

    # --- Cloud SQL (Postgres) ---
    # In Cloud Run, connect via the Cloud SQL Auth Proxy unix socket:
    #   /cloudsql/<PROJECT>:<REGION>:<INSTANCE>
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASS: str = os.getenv("DB_PASS", "postgres")
    DB_NAME: str = os.getenv("DB_NAME", "code_reviewer")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    CLOUD_SQL_CONNECTION_NAME: str = os.getenv("CLOUD_SQL_CONNECTION_NAME", "")
    # Fallback for local development so the project runs with zero setup.
    USE_SQLITE_FALLBACK: bool = os.getenv("USE_SQLITE_FALLBACK", "true").lower() == "true"

    # --- Cloud Storage ---
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "code-reviewer-artifacts")

    # --- Auth (Firebase / Identity Platform) ---
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", GCP_PROJECT_ID)
    DISABLE_AUTH_FOR_LOCAL_DEV: bool = os.getenv("DISABLE_AUTH_FOR_LOCAL_DEV", "true").lower() == "true"

    # --- App ---
    MAX_CODE_CHARS: int = int(os.getenv("MAX_CODE_CHARS", "50000"))
    TOP_K_HISTORICAL_RULES: int = int(os.getenv("TOP_K_HISTORICAL_RULES", "5"))


settings = Settings()
