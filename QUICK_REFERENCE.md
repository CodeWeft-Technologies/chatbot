# Multimodal RAG - Quick Reference Card

## 🚀 Quick Start (5 minutes)

```bash
# 1. Install
pip install -r MULTIMODAL_REQUIREMENTS.txt

# 2. Test
python test_multimodal_examples.py test-all

# 3. Upload
curl -X POST "http://localhost:8000/ingest/file/my-bot" \
  -F "org_id=my-org" \
  -F "file=@document.pdf" \
  -H "x-bot-key: your-key"
```

## 📁 Supported File Types

| Format | Support | Features |
|--------|---------|----------|
| 📄 PDF | ✅ | Text extract + OCR |
| 📝 DOCX | ✅ | Text + tables |
| 🎤 PPTX | ✅ | Slides + text |
| 📊 CSV | ✅ | Rows + headers |
| 📃 TXT | ✅ | Plain text |
| 🖼️ PNG/JPG | ✅ | OCR extract |

## 🔌 API Endpoint

```
POST /ingest/file/{bot_id}
```

### Request
```bash
curl -X POST "http://localhost:8000/ingest/file/{bot_id}" \
  -F "org_id={org_id}" \
  -F "file=@{file}" \
  -H "x-bot-key: {api_key}"
```

### Response
```json
{
  "inserted": 42,
  "skipped_duplicates": 3,
  "total_chunks": 45,
  "file_type": "pdf",
  "file_name": "research.pdf"
}
```

## 📚 Documentation Files

| File | Purpose | Time |
|------|---------|------|
| [README_MULTIMODAL.md](README_MULTIMODAL.md) | **Start here** | 5 min |
| [MULTIMODAL_SUMMARY.md](MULTIMODAL_SUMMARY.md) | What was done | 10 min |
| [MULTIMODAL_RAG_GUIDE.md](MULTIMODAL_RAG_GUIDE.md) | How to use | 15 min |
| [MULTIMODAL_API_REFERENCE.md](MULTIMODAL_API_REFERENCE.md) | API docs | 20 min |
| [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) | Deployment | 30 min |
| [MULTIMODAL_IMPLEMENTATION_CHECKLIST.md](MULTIMODAL_IMPLEMENTATION_CHECKLIST.md) | Checklist | 15 min |

## 🛠️ Installation

```bash
# Install all dependencies
pip install -r MULTIMODAL_REQUIREMENTS.txt

# Verify installation
python -c "import paddleocr; print('✓')"

# System dependencies (Linux only)
apt-get install tesseract-ocr
```

## ✅ Testing

```bash
# Run all tests
python test_multimodal_examples.py test-all

# Run specific test
python test_multimodal_examples.py test-text

# Upload a file
python test_multimodal_examples.py upload-pdf research.pdf
```

## 🗂️ Code Structure

```
app/services/
├── multimodal_processor.py ← NEW
│   ├── detect_file_type()
│   ├── extract_elements_from_file()
│   └── chunk_elements_by_title()
├── enhanced_rag.py (enhanced)
│   └── process_multimodal_file()
└── rag.py ✓ unchanged

app/routes/
└── ingest.py (enhanced)
    └── POST /ingest/file/{bot_id}
```

## 📊 Processing Pipeline

```
File Upload
    ↓
Type Detection
    ↓
Element Extraction
    ↓
Title-Based Chunking
    ↓
Deduplication
    ↓
Embedding (OpenAI)
    ↓
Storage (PostgreSQL)
    ↓
Response
```

## 🔐 Authentication

**Option 1: API Key**
```bash
curl -H "x-bot-key: sk_live_abc123" ...
```

**Option 2: JWT Token**
```bash
curl -H "authorization: Bearer eyJhbGc..." ...
```

## ⚡ Performance Tips

| Task | Action |
|------|--------|
| Large PDFs | Install tesseract: `apt-get install tesseract-ocr` |
| Memory issues | Reduce chunk size: `max_chunk_chars = 1500` |
| Slow ingestion | Check OPENAI_API_KEY is valid |
| Rate limited | Wait 60 seconds before retry |

## 🐛 Debugging

```bash
# Check logs
grep "[INGEST-FILE]" app.log

# Test file type detection
python -c "from app.services.multimodal_processor import detect_file_type; print(detect_file_type('test.pdf'))"

# Verify OCR
python -c "from paddleocr import PaddleOCR; print('OK')"

# Check embeddings
python -c "from app.services.enhanced_rag import embed_text; print(len(embed_text('test')))"
```

## 🚨 Common Errors

| Error | Solution |
|-------|----------|
| `Unsupported file type` | Check file extension is supported |
| `Empty file` | Ensure file has content |
| OCR failing | Install tesseract: `apt-get install tesseract-ocr` |
| Rate limited | Wait 60 seconds, retry |
| Memory error | Increase server RAM or reduce chunk size |

## 📝 Examples

### Python
```python
import requests

response = requests.post(
    "http://localhost:8000/ingest/file/my-bot",
    data={"org_id": "my-org"},
    files={"file": open("research.pdf", "rb")},
    headers={"x-bot-key": "your-key"}
)
print(response.json())
```

### JavaScript
```javascript
const form = new FormData();
form.append('org_id', 'my-org');
form.append('file', document.querySelector('input[type=file]').files[0]);

const response = await fetch('http://localhost:8000/ingest/file/my-bot', {
  method: 'POST',
  body: form,
  headers: { 'x-bot-key': 'your-key' }
});

console.log(await response.json());
```

### cURL
```bash
curl -X POST "http://localhost:8000/ingest/file/my-bot" \
  -F "org_id=my-org" \
  -F "file=@document.pdf" \
  -H "x-bot-key: your-key"
```

## 🚀 Deployment

```bash
# 1. Install deps
pip install -r MULTIMODAL_REQUIREMENTS.txt

# 2. Run tests
python test_multimodal_examples.py test-all

# 3. Start server
python -m uvicorn app.main:app

# 4. Test endpoint
curl -X POST "http://localhost:8000/ingest/file/test-bot" \
  -F "org_id=test-org" \
  -F "file=@test.pdf" \
  -H "x-bot-key: test-key"
```

## 📊 Metadata

Chunks stored with metadata:
```json
{
  "source_file": "research.pdf",
  "file_hash": "abc123...",
  "content_hash": "def456...",
  "content_type": "pdf",
  "page": 5,
  "extraction_method": "pdf_text"
}
```

## ⚙️ Configuration

```python
# In multimodal_processor.py
max_chunk_chars = 3000          # Hard limit
merge_threshold_chars = 500     # Merge small chunks

# In ingest.py
max_file_size = 25 * 1024 * 1024  # 25MB
max_concurrent_ingests = 1         # Lock count
rate_limit = 120                   # Requests per minute
```

## 🔄 Backward Compatibility

✅ All existing endpoints still work:
- `POST /ingest/{bot_id}` - Text
- `POST /ingest/pdf/{bot_id}` - PDF only
- `POST /ingest/url/{bot_id}` - URL scraping

✅ Database schema unchanged
✅ Retrieval logic unchanged
✅ Authentication unchanged

## 📈 Monitoring

```sql
-- Check chunk count
SELECT COUNT(*) FROM rag_embeddings 
WHERE bot_id = 'my-bot';

-- See chunk sources
SELECT metadata->>'source_file', COUNT(*)
FROM rag_embeddings
GROUP BY metadata->>'source_file';

-- Find duplicates
SELECT content_hash, COUNT(*)
FROM rag_embeddings, jsonb_each_text(metadata)
WHERE key = 'content_hash'
GROUP BY content_hash
HAVING COUNT(*) > 1;
```

## 🎯 Next Steps

1. ✅ Read [README_MULTIMODAL.md](README_MULTIMODAL.md)
2. ✅ Install dependencies
3. ✅ Run tests
4. ✅ Try uploading a file
5. ✅ Check logs
6. ✅ Deploy to staging
7. ✅ Update frontend
8. ✅ Deploy to production

## 📞 Support

- Check [MULTIMODAL_RAG_GUIDE.md](MULTIMODAL_RAG_GUIDE.md) for detailed help
- Run `python test_multimodal_examples.py test-all` to verify setup
- Check logs: `grep "[INGEST-FILE]" app.log`
- Review error codes in [MULTIMODAL_API_REFERENCE.md](MULTIMODAL_API_REFERENCE.md)

---

**✨ Ready to use! Start with README_MULTIMODAL.md**
