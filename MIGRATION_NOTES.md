# RAG Enhancement Migration Notes

## Overview
Enhanced the web scraping and RAG ingestion pipeline with production-grade features for better content extraction, chunking, and deduplication.

## What Changed

### 1. Dependencies Added (`requirements.txt`)
- **playwright==1.47.0** - JavaScript rendering for modern web apps (React, Vue, Angular)
- **readability-lxml==0.8.1** - Clean content extraction using Mozilla's Readability algorithm
- **langdetect==1.0.9** - Automatic language detection for multilingual content
- **nltk==3.9.1** - Sentence tokenization for semantic chunking

### 2. New Modules

#### `app/services/enhanced_scraper.py`
Enhanced web scraping with:
- **Playwright Integration**: Renders JavaScript-heavy sites (fallback to requests if unavailable)
- **Readability Extraction**: Removes navigation, ads, and boilerplate using Mozilla's algorithm
- **Metadata Extraction**: Title, description, canonical URL, language detection
- **Automatic Fallback**: Gracefully degrades to BeautifulSoup if Playwright unavailable

#### `app/services/enhanced_rag.py`
Enhanced RAG utilities with:
- **Semantic Chunking**: Splits on sentence boundaries (NLTK) instead of fixed character counts
  - Configurable min/max chunk size (default: 200-1500 chars)
  - Sentence overlap between chunks for context continuity
  - Falls back to fixed-size chunking if NLTK unavailable
- **Content Deduplication**: SHA-256 hash-based duplicate detection
  - Prevents storing identical content multiple times
  - Normalizes content before hashing (whitespace, case)
  - Stores hash in metadata for efficient lookups
- **Boilerplate Removal**: Regex patterns for common noise (cookie notices, newsletter prompts, social media)

### 3. Updated Routes (`app/routes/ingest.py`)

All ingestion endpoints now use enhanced services:

#### `/ingest/url/{bot_id}` (URL scraping)
- Uses `scrape_url()` with Playwright + Readability
- Returns additional metadata: `skipped_duplicates`, `total_chunks`, `language`
- Stores canonical URLs and language in metadata

#### `/ingest/{bot_id}` (Text ingestion)
- Now uses semantic chunking
- Deduplication enabled
- Returns `skipped_duplicates` count

#### `/ingest/pdf/{bot_id}` (PDF ingestion)
- Now uses semantic chunking
- Deduplication enabled
- Returns `skipped_duplicates` count

## Installation

### 1. Install Python dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Install Playwright browsers (for JS rendering)
```bash
playwright install chromium
```

### 3. Download NLTK data (for semantic chunking)
```bash
python -c "import nltk; nltk.download('punkt')"
```
*Note: The code auto-downloads this on first import, but you can pre-install it.*

## Configuration

### Environment Variables (Optional)
No new environment variables required. The system automatically detects available features:

- If Playwright unavailable → Falls back to requests
- If Readability unavailable → Falls back to BeautifulSoup selectors
- If NLTK unavailable → Falls back to fixed-size chunking
- If langdetect unavailable → Language detection disabled

### Feature Toggles
To disable Playwright (force fallback to requests):
```python
scraped = scrape_url(url, use_playwright=False)
```

## API Response Changes

### Before
```json
{
  "inserted": 15
}
```

### After
```json
{
  "inserted": 12,
  "skipped_duplicates": 3,
  "total_chunks": 15,
  "language": "en"
}
```

## Database Schema
No schema changes required! Deduplication uses existing `metadata` JSONB column:
```sql
metadata->>'content_hash'  -- SHA-256 hash of normalized content
```

Existing metadata preserved:
- `source_url`
- `page_title`
- `description` (new)
- `canonical_url`
- `language` (new)
- `source_file` (PDF uploads)

## Backward Compatibility

✅ **Fully backward compatible** - old `app/rag.py` functions still work:
- `chunk_text()` now calls semantic chunking internally
- `store_embedding()` signature unchanged (deduplication optional)
- Existing embeddings unaffected

## Performance Considerations

### Playwright
- **Pros**: Handles JS-rendered content (SPAs), dynamic content, lazy loading
- **Cons**: ~2-3x slower than requests, higher memory usage
- **When to use**: Modern web apps (React, Vue, Angular), content behind JS

### Semantic Chunking
- **Pros**: Preserves sentence boundaries, better context for embeddings
- **Cons**: Slightly slower than fixed-size (negligible for most use cases)
- **Trade-off**: Better chunk quality vs. minimal speed impact

### Deduplication
- **Cost**: One additional SELECT query per chunk
- **Benefit**: Prevents duplicate storage, reduces database size, improves search quality
- **Note**: Hash check is fast (indexed JSONB column)

## Testing

### Test URL Scraping
```bash
curl -X POST http://localhost:8000/ingest/url/{bot_id} \
  -H "Content-Type: application/json" \
  -H "x-bot-key: YOUR_API_KEY" \
  -d '{"org_id": "test-org", "url": "https://example.com"}'
```

Expected response:
```json
{
  "inserted": 8,
  "skipped_duplicates": 0,
  "total_chunks": 8,
  "language": "en"
}
```

### Test Deduplication
Run the same request twice - second response should show:
```json
{
  "inserted": 0,
  "skipped_duplicates": 8,
  "total_chunks": 8,
  "language": "en"
}
```

## Troubleshooting

### Playwright Installation Issues
If `playwright install` fails:
1. Install system dependencies: [Playwright System Requirements](https://playwright.dev/docs/intro#system-requirements)
2. Or disable Playwright: Set `use_playwright=False` in scraper calls

### NLTK Download Issues
If automatic download fails:
```bash
python -c "import nltk; nltk.download('punkt', download_dir='/path/to/nltk_data')"
```
Or set `NLTK_DATA` environment variable.

### Memory Issues (Playwright)
For limited memory environments, disable Playwright or increase timeout:
```python
scraped = scrape_url(url, use_playwright=False)  # Disable
# OR
scraped = scrape_url(url, timeout=60)  # Increase timeout
```

## Future Enhancements

Potential improvements for consideration:
- [ ] Sitemap crawling for bulk ingestion
- [ ] Image/video content extraction
- [ ] PDF OCR for scanned documents
- [ ] Rate limiting per domain
- [ ] Retry logic with exponential backoff
- [ ] Progress tracking for long scrapes
- [ ] Webhook notifications on completion

## Rollback Plan

If issues arise, revert to old implementation:

1. Restore old ingest route:
```python
from app.rag import chunk_text, embed_text, store_embedding
```

2. Remove enhanced imports from `ingest.py`

3. Old dependencies still work (BeautifulSoup, requests)

No database rollback needed (schema unchanged).
