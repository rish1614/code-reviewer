# Nightshift — The 24/7 Intelligent Code Reviewer

An always-on, multi-language, AI-powered code review platform. Authenticated
users submit source code and receive a bug report, architectural best-practice
guidance, optimization insights, and a standardized **1–10 quality rating** —
grounded in a growing set of historical review rules.

Built entirely on Google Cloud.

## Architecture

```
 ┌────────────────┐    HTTPS ┌──────────────────────┐        ┌────────────────────┐
 │  Frontend       │ ───────►│   Cloud Run (API)    │        │   Vertex AI          │
 │ (Streamlit UI   │         │   FastAPI backend    │ ─────► │   Gemini (review)    │
 │  or static HTML)│         │                      │        │   text-embedding-004 │
 └────────────────┘          │  - Auth check        │        └────────────────────┘
 Identity Platform ────────► │  - Review orchestration
   (Firebase Auth)           │  - Vector similarity
                              │    search over rules  │        ┌────────────────────┐
                              └─────────┬────────────┘ ─────► │   Cloud SQL         │
                                        │                       │  (Postgres)        │
                                        ▼                       │  users / reviews / │
                              ┌──────────────────────┐          │  historical_rules  │
                              │   Cloud Storage       │          └────────────────────┘
                              │ (raw CSV / artifacts)│
                              └──────────────────────┘
```

There are two interchangeable frontends included in this repo — pick either one, both talk to the same FastAPI backend:
- `frontend/index.html` — a static single-page UI (vanilla HTML/JS)
- `streamlit_app/streamlit_app.py` — a Streamlit UI with identical features

Both are deployable as their own Cloud Run service, separate from the backend.

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
  index.html            Single-page static UI (submit code, view history, ingest CSV)
streamlit_app/
  streamlit_app.py      Equivalent UI built with Streamlit
  requirements.txt
  Dockerfile
sample_data/
  historical_rules.csv  Example dataset matching the required schema
```

## Running locally

### 1. Start the backend

```bash
cd backend
pip install -r requirements.txt --break-system-packages   # or use a venv
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

Confirm it's alive: open `http://127.0.0.1:8080/healthz` → `{"status":"ok"}`,
or browse the interactive API docs at `http://127.0.0.1:8080/docs`.

> **Note:** `http://127.0.0.1:8080` on its own returns `{"detail":"Not Found"}` —
> that's expected, since the backend is an API only and has no route at `/`.
> The actual app is the separate frontend below.

### 2. Mock mode — run everything without live GCP credentials

For local development and demos before your GCP sandbox is ready, `.env`
includes:

```
USE_SQLITE_FALLBACK=true
DISABLE_AUTH_FOR_LOCAL_DEV=true
USE_MOCK_AI=true
```

With `USE_MOCK_AI=true`, `gemini_service.py` skips real Vertex AI calls and
returns canned (but structurally correct) responses, so the full flow —
CSV ingestion, code submission, history — works end to end with zero GCP
setup. **Note:** mock responses are static and don't actually vary by the
code you submit; they exist only to prove the plumbing works. Set
`USE_MOCK_AI=false` (and authenticate with real GCP — see below) once
you're ready for genuine, code-aware reviews.

### 3. Start a frontend — pick one

**Option A: Streamlit (recommended)**
```bash
cd streamlit_app
pip install -r requirements.txt --break-system-packages
streamlit run streamlit_app.py
```
Opens automatically at `http://localhost:8501`.

**Option B: static HTML**
```bash
cd frontend
python3 -m http.server 5500
```
Then open `http://localhost:5500` in a browser. (Opening `index.html`
directly as a `file://` path also works in most cases, but serving it over
HTTP avoids occasional `fetch` issues with some browsers.)

Both frontends default to talking to `http://localhost:8080` — override
with the `API_BASE` environment variable (Streamlit) or by editing the
`API_BASE` constant at the top of `index.html`'s script (static HTML).

## Deploying to Google Cloud

1. **Authenticate** (do this only once your official GCP sandbox/project is
   ready — don't burn credits on a project you don't intend to keep):
```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```
2. **Enable APIs**:
```bash
gcloud services enable aiplatform.googleapis.com run.googleapis.com \
  sqladmin.googleapis.com storage.googleapis.com
```
3. **Cloud SQL**: create a Postgres instance and database; note the
   connection name (`PROJECT:REGION:INSTANCE`).
4. **Cloud Storage**: create a bucket for raw CSV / code artifacts.
5. **Identity Platform**: enable it in your GCP project and configure a
   sign-in provider for the frontend.

### Deploy the backend

```bash
cd backend
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/code-reviewer

gcloud run deploy code-reviewer \
  --image gcr.io/YOUR_PROJECT_ID/code-reviewer \
  --platform managed \
  --region us-central1 \
  --add-cloudsql-instances YOUR_PROJECT_ID:us-central1:YOUR_INSTANCE \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1,USE_SQLITE_FALLBACK=false,DISABLE_AUTH_FOR_LOCAL_DEV=false,USE_MOCK_AI=false,CLOUD_SQL_CONNECTION_NAME=YOUR_PROJECT_ID:us-central1:YOUR_INSTANCE,DB_USER=postgres,DB_PASS=YOUR_PASSWORD,DB_NAME=code_reviewer,FIREBASE_PROJECT_ID=YOUR_PROJECT_ID \
  --allow-unauthenticated
```

Note the service URL this prints (e.g. `https://code-reviewer-xxxxx.a.run.app`)
— the frontend needs it in the next step.

### Deploy the frontend (Streamlit)

```bash
cd streamlit_app
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/code-reviewer-ui

gcloud run deploy code-reviewer-ui \
  --image gcr.io/YOUR_PROJECT_ID/code-reviewer-ui \
  --platform managed \
  --region us-central1 \
  --set-env-vars API_BASE=https://YOUR_BACKEND_CLOUD_RUN_URL \
  --allow-unauthenticated
```

### Deploy the frontend (static HTML alternative)

Instead of Streamlit, `frontend/index.html` can be hosted on Cloud Storage
(as a static website) or Firebase Hosting — just update the `API_BASE`
constant in its script to your backend's Cloud Run URL before uploading.

## Ingesting historical review data

```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/api/v1/historical-rules/ingest \
  -H "Authorization: Bearer <firebase_id_token>" \
  -F "file=@sample_data/historical_rules.csv"
```

## Troubleshooting

- **`{"detail":"Not Found"}` at the root URL** — expected. The backend has
  no route at `/`; use `/healthz` or `/docs` to confirm it's running.
- **"Failed to fetch" in the frontend on every request** — usually means
  the backend crashed on that request rather than a real network issue.
  Check the terminal running `uvicorn` for a traceback. A `500` response
  raised before the CORS middleware can attach headers shows up in the
  browser as a generic fetch failure rather than the real error — the
  global exception handler in `main.py` fixes this by always returning a
  proper JSON error.
- **`psycopg2-binary` fails to build on `pip install`** — you don't need
  it for local development (`USE_SQLITE_FALLBACK=true` skips Postgres
  entirely). Either install without it, or run
  `sudo apt install libpq-dev python3-dev` first if you do want Postgres
  locally.
- **`google.auth.exceptions.DefaultCredentialsError`** — you're calling
  real Vertex AI without being authenticated. Either run
  `gcloud auth application-default login` with a real GCP project that has
  Vertex AI enabled, or set `USE_MOCK_AI=true` in `.env` to skip real model
  calls during local development.
- **Mock reviews look identical for different code** — by design; see the
  mock mode note above. Switch to `USE_MOCK_AI=false` with real credentials
  for genuine, code-aware output.

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
