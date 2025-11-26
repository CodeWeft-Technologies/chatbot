# Backend API

FastAPI backend with Postgres + pgvector for retrieval and Groq for chat completion.

## Prerequisites
- Python 3.10+
- Postgres with `pgvector` extension
- Environment file `.env` with connection and API keys

## Install
```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
```

## Configure
Create `.env` in `backend/` or project root:

```bash
SUPABASE_DB_DSN=postgresql://user:pass@localhost:5432/dbname
SUPABASE_URL=https://your-supabase-url
SUPABASE_ANON_KEY=anon-key
SUPABASE_SERVICE_ROLE_KEY=service-role-key
GROQ_API_KEY=your-groq-key
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
MAX_CONTEXT_CHUNKS=6
MIN_SIMILARITY=0.25
CORS_ALLOWED_ORIGINS=http://localhost:3000
PUBLIC_API_BASE_URL=http://localhost:8000
```

## Database
- Enable `pgvector` and apply schema:

```bash
python backend/apply_schema.py
```

- Table `rag_embeddings` stores chunks and embeddings scoped by `org_id` and `bot_id`.
- Usage metrics recorded in `bot_usage_daily`.

## Run
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend --reload
```

Open `http://localhost:8000/docs` for API docs.

## Key Endpoints
- `POST /api/ingest/text` add text; chunks and embeds are stored.
- `POST /api/chat/stream/{bot_id}` chat with streaming Server-Sent Events.
- `GET /api/usage/{org_id}/{bot_id}` daily activity (auth required).
- `GET /api/usage/summary/{org_id}/{bot_id}` summary (auth required).
- `POST /api/ingest/clear/{bot_id}` remove all stored content for a bot (auth or public key).

## Embeddings
- Local small models recommended for deployment:
  - `sentence-transformers/all-MiniLM-L6-v2` (384‑dim)
  - `BAAI/bge-small-en-v1.5` (384‑dim)
- Ensure `rag_embeddings.embedding` dimension matches the model.

## Security
- All data access is scoped by `org_id` and `bot_id`.
- Public embeds can use per-bot public API keys; dashboard uses bearer tokens.

