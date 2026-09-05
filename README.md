# Nightshift — The 24/7 Intelligent Code Reviewer

An always-on, multi-language, AI-powered code review platform. Authenticated
users submit source code and receive a bug report, architectural best-practice
guidance, optimization insights, and a standardized **1–10 quality rating** —
grounded in a growing set of historical review rules.

Built entirely on Google Cloud.

## Architecture

```
 ┌────────────┐        ┌──────────────────────┐        ┌────────────────────┐
 │  Frontend  │  HTTPS │   Cloud Run (API)    │        │   Vertex AI          │
 │ (static)   │ ─────► │   FastAPI backend    │ ─────► │   Gemini (review)    │
 └────────────┘        │                      │        │   text-embedding-004 │
                        │  - Auth check        │        └────────────────────┘
 Identity Platform ────►│  - Review orchestration
   (Firebase Auth)      │  - Vector similarity
                        │    search over rules  │        ┌────────────────────┐
                        └─────────┬────────────┘ ─────► │   Cloud SQL         │
                                  │                       │  (Postgres)        │
                                  ▼                       │  users / reviews / │
                        ┌──────────────────────┐          │  historical_rules  │
                        │   Cloud Storage       │          └────────────────────┘
                        │ (raw CSV / artifacts)│
                        └──────────────────────┘
```

## How it works

1. **Auth** — Users sign in via Firebase Authentication / Identity Platform.
   Every API request carries a Firebase ID token, verified server-side.
2. **Historical learning** — An admin uploads the historical rules CSV
   (`id, type, description`) via `/api/v1/historical-rules/ingest`. Each rule
   description is embedded once using the Vertex AI `text-embedding-004`
   model and stored in Cloud SQL alongside its vector.
3. **Review flow** — When a user submits code:
   - The code is embedded and compared (cosine similarity) against every
     stored historical rule to retrieve the top-K most relevant ones.
   - Those rules are injected into a structured prompt sent to **Gemini**
     (via Vertex AI), which returns a strict JSON review: bug report, best
     practices, optimization notes, and a 1–10 quality rating.
   - The full review is persisted in Cloud SQL under the user's account.
4. **History** — Users can fetch their full review history at any time to
   track quality trends and recurring issues over time.

## Repository structure

```
backend/
  app/
    main.py            FastAPI app + all routes
    config.py          Environment-driven settings
    database.py         SQLAlchemy models (users, reviews, historical_rules)
    auth.py             Firebase / Identity Platform token verification
    gemini_service.py   Vertex AI Gemini + embedding calls
    history_engine.py   CSV ingestion + vector similarity search
    schemas.py          Pydantic request/response models
  Dockerfile
  requirements.txt
  .env.example
frontend/
  index.html            Single-page UI (submit code, view history, ingest CSV)
sample_data/
  historical_rules.csv  Example dataset matching the required schema
```

## Running locally

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # defaults use SQLite + auth bypass for local dev
uvicorn app.main:app --reload --port 8080
```

Open `frontend/index.html` in a browser (or serve it statically) — it talks
to `http://localhost:8080` by default.

> Local dev mode (`USE_SQLITE_FALLBACK=true`, `DISABLE_AUTH_FOR_LOCAL_DEV=true`)
> lets the whole flow run without any live GCP resources, using a local
> SQLite file and a fixed demo user. Switch both to `false` for production.

## Deploying to Google Cloud

1. **Enable APIs**: Cloud Run, Vertex AI, Cloud SQL Admin, Cloud Storage,
   Identity Platform.
2. **Cloud SQL**: create a Postgres instance and database; note the
   connection name (`PROJECT:REGION:INSTANCE`).
3. **Cloud Storage**: create a bucket for raw CSV / code artifacts.
4. **Identity Platform**: enable it in your GCP project and configure a
   sign-in provider for the frontend.
5. **Build & deploy**:

```bash
cd backend
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/code-reviewer

gcloud run deploy code-reviewer \
  --image gcr.io/YOUR_PROJECT_ID/code-reviewer \
  --platform managed \
  --region us-central1 \
  --add-cloudsql-instances YOUR_PROJECT_ID:us-central1:YOUR_INSTANCE \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1,USE_SQLITE_FALLBACK=false,DISABLE_AUTH_FOR_LOCAL_DEV=false,CLOUD_SQL_CONNECTION_NAME=YOUR_PROJECT_ID:us-central1:YOUR_INSTANCE,DB_USER=postgres,DB_PASS=YOUR_PASSWORD,DB_NAME=code_reviewer,FIREBASE_PROJECT_ID=YOUR_PROJECT_ID \
  --allow-unauthenticated
```

6. Host `frontend/index.html` on Cloud Storage (static website) or Firebase
   Hosting, pointing `API_BASE` at your Cloud Run URL.

## Ingesting historical review data

```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/api/v1/historical-rules/ingest \
  -H "Authorization: Bearer <firebase_id_token>" \
  -F "file=@sample_data/historical_rules.csv"
```

## Why these GCP choices

- **Gemini on Vertex AI** — single managed model for multi-language code
  understanding, bug detection, and structured JSON generation.
- **Vertex AI text-embedding-004** — turns historical rule text and
  submitted code into comparable vectors, enabling semantic (not just
  keyword) grounding.
- **Cloud SQL** — durable, relational storage for user accounts, review
  history, and historical rules; simple to query for growth analytics.
- **Cloud Run** — stateless, auto-scaling container hosting with pay-per-use
  pricing, ideal for an "always-on" but bursty review workload.
- **Identity Platform / Firebase Auth** — managed, secure authentication
  without building a custom auth system.
