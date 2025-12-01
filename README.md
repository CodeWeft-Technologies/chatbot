# Backend API

FastAPI backend with Postgres + pgvector for retrieval and Groq for chat completion.

## 🆕 Enhanced RAG Features

**NEW:** Production-grade web scraping and RAG ingestion pipeline with:
- ✅ **Playwright JS Rendering** - Captures React/Vue/Angular content
- ✅ **Readability Content Extraction** - Removes ads, nav, footers automatically
- ✅ **Semantic Chunking** - Preserves sentence boundaries (NLTK)
- ✅ **Content Deduplication** - SHA-256 hash-based duplicate detection
- ✅ **Boilerplate Removal** - Strips cookie notices, newsletter prompts
- ✅ **Canonical URLs** - URL normalization and tracking
- ✅ **Language Detection** - Automatic language identification
- ✅ **Enhanced Metadata** - Title, description, language, canonical URL

**📖 Documentation:**
- [RAG_ENHANCEMENT_SUMMARY.md](./RAG_ENHANCEMENT_SUMMARY.md) - Feature overview
- [RAG_ARCHITECTURE.md](./RAG_ARCHITECTURE.md) - Before/after architecture
- [MIGRATION_NOTES.md](./MIGRATION_NOTES.md) - Installation & troubleshooting

## Prerequisites
- Python 3.10+
- Postgres with `pgvector` extension
- Environment file `.env` with connection and API keys

## Quick Start

### 1. Install Dependencies
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

### 2. Install RAG Enhancements (Optional but Recommended)
```bash
# Windows
.\setup_rag_enhancements.ps1

# Linux/Mac
bash setup_rag_enhancements.sh
```

This installs:
- Playwright (for JS rendering)
- Readability (for clean content extraction)
- NLTK (for semantic chunking)
- langdetect (for language detection)

**Note:** System works without these (automatic fallbacks), but you'll miss JS-rendered content and semantic chunking.

### 3. Configure Environment
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

### 4. Setup Database
Enable `pgvector` and apply schema:

```bash
python backend/apply_schema.py
```

- Table `rag_embeddings` stores chunks and embeddings scoped by `org_id` and `bot_id`.
- Usage metrics recorded in `bot_usage_daily`.

### 5. Run Server
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend --reload
```

Open `http://localhost:8000/docs` for API docs.

### 6. Test Installation (Optional)
```bash
python test_rag_enhancements.py
```

## Key Endpoints

### Ingestion
- `POST /ingest/{bot_id}` - Ingest plain text
- `POST /ingest/url/{bot_id}` - Scrape and ingest URL (✨ enhanced with Playwright + Readability)
- `POST /ingest/pdf/{bot_id}` - Extract and ingest PDF
- `POST /ingest/clear/{bot_id}` - Clear all bot content

### Chat
- `POST /api/chat/stream/{bot_id}` - Chat with streaming Server-Sent Events
- RAG retrieval uses enhanced embeddings with metadata filtering

### Analytics
- `GET /api/usage/{org_id}/{bot_id}` - Daily activity (auth required)
- `GET /api/usage/summary/{org_id}/{bot_id}` - Summary stats (auth required)
- `GET /ingest/analytics/{org_id}/{bot_id}` - Embedding counts
- `GET /ingest/analytics/sources/{org_id}/{bot_id}` - Source breakdown

## Enhanced API Responses

### Before
```json
{
  "inserted": 15
}
```

### After (with enhancements)
```json
{
  "inserted": 12,
  "skipped_duplicates": 3,
  "total_chunks": 15,
  "language": "en"
}
```

Metadata now includes:
- `source_url` - Original URL
- `page_title` - Extracted title
- `description` - Meta description
- `canonical_url` - Canonical link
- `language` - Detected language
- `content_hash` - SHA-256 hash for deduplication

## Embeddings

Local small models recommended for deployment:
- `sentence-transformers/all-MiniLM-L6-v2` (384-dim) - Default, balanced
- `BAAI/bge-small-en-v1.5` (384-dim) - Better quality, slightly slower

Ensure `rag_embeddings.embedding` dimension matches the model.

## Feature Toggles

### Disable Playwright (Force Fallback)
```python
from app.services.enhanced_scraper import scrape_url
scraped = scrape_url(url, use_playwright=False)
```

### Use Legacy Chunking
```python
from app.services.enhanced_rag import chunk_text_fallback
chunks = chunk_text_fallback(text, chunk_size=1000, overlap=200)
```

### Skip Deduplication
```python
from app.services.enhanced_rag import store_embedding
store_embedding(org_id, bot_id, content, emb, metadata, skip_duplicate_check=True)
```

## Security
- All data access is scoped by `org_id` and `bot_id`.
- Public embeds can use per-bot public API keys; dashboard uses bearer tokens.
- Content hashes are stored for deduplication but are not reversible.

## Performance Considerations

### Playwright
- **Speed**: 2-3x slower than requests (~3s vs ~1s per page)
- **Memory**: Higher usage (~150MB vs ~10MB per page)
- **Use when**: Scraping JS-heavy sites (React, Vue, Angular)
- **Skip when**: Scraping static HTML blogs, documentation sites

### Semantic Chunking
- **Speed**: Negligible impact (~1ms vs ~0.1ms per page)
- **Quality**: Better embeddings (no mid-sentence cuts)
- **Fallback**: Automatic if NLTK unavailable

### Deduplication
- **Cost**: One SELECT query per chunk (~1ms)
- **Benefit**: Prevents duplicate storage, reduces DB size
- **Note**: Hash lookups are fast (JSONB indexed)

## Troubleshooting

### Playwright Installation Failed
```bash
# Check system requirements
playwright install --help

# Install specific browser
playwright install chromium

# If fails, disable Playwright (system still works)
```

### NLTK Data Download Failed
```bash
# Manual download
python -c "import nltk; nltk.download('punkt')"

# Set custom data directory
export NLTK_DATA=/path/to/nltk_data
```

### Memory Issues
```bash
# Disable Playwright to reduce memory
# Edit app/routes/ingest.py:
# scraped = scrape_url(body.url, use_playwright=False)
```

### Import Errors
```bash
# Verify installation
python test_rag_enhancements.py

# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings
│   ├── db.py                # Database utilities
│   ├── rag.py               # Legacy RAG (still works)
│   ├── routes/
│   │   ├── chat.py          # Chat endpoints
│   │   └── ingest.py        # ✨ Enhanced ingestion endpoints
│   └── services/
│       ├── enhanced_scraper.py   # ✨ NEW: Playwright + Readability
│       ├── enhanced_rag.py       # ✨ NEW: Semantic chunking + dedup
│       ├── embeddings.py         # Embedding utilities
│       ├── groq_llm.py           # Groq LLM client
│       └── calendar_google.py    # Google Calendar integration
├── requirements.txt              # ✨ Updated with new deps
├── apply_schema.py              # Database schema setup
├── seed_demo.py                 # Demo data seeder
├── test_rag_enhancements.py     # ✨ NEW: Test suite
├── setup_rag_enhancements.sh    # ✨ NEW: Linux/Mac setup
├── setup_rag_enhancements.ps1   # ✨ NEW: Windows setup
├── README.md                    # ✨ This file
├── RAG_ENHANCEMENT_SUMMARY.md   # ✨ NEW: Feature overview
├── RAG_ARCHITECTURE.md          # ✨ NEW: Architecture diagrams
└── MIGRATION_NOTES.md           # ✨ NEW: Migration guide
```

## Backward Compatibility

✅ **100% backward compatible**
- Old `app/rag.py` functions still work
- Existing embeddings unaffected
- No database migration required
- All enhancements are additive

Old code continues to work:
```python
from app.rag import chunk_text, embed_text, store_embedding
# Internally upgraded to use semantic chunking!
```

## Contributing

When adding new features:
1. Maintain backward compatibility
2. Add automatic fallbacks for optional dependencies
3. Update tests in `test_rag_enhancements.py`
4. Document in relevant markdown files

## License

See project root for license information.

