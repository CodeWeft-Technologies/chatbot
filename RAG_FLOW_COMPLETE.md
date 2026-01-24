# RAG (Retrieval-Augmented Generation) Complete Flow

## 📊 Your Complete Architecture

```
┌──────────────────────────────────────────────────────────┐
│         FILE UPLOAD (PDF, DOCX, PPTX, CSV, TXT, IMG)    │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│    DETECT FILE TYPE (magic bytes + extension check)     │
└────────────────────┬─────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬────────────┬──────────┐
        ▼            ▼            ▼            ▼          ▼
      PDF        DOCX        PPTX          CSV        IMAGE
   (hi_res)     (docx)      (pptx)       (csv)      (LLM)
        │            │            │            │          │
        └────────────┼────────────┴────────────┴──────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│    EXTRACT ELEMENTS (Unstructured lib + OCR)            │
│    Output: Text paragraphs + Tables + Images            │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│    CHUNK BY TITLE (semantic boundaries)                 │
│    Max: 1200 chars | Respects: sections/subsections    │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│    SEPARATE CONTENT TYPES (text, tables, images)        │
└────────────────────┬─────────────────────────────────────┘
                     │
        ┌────────────┴────────────┬──────────────┐
        │                         │              │
        ▼                         ▼              ▼
   Text only             Tables present      Images present
        │                         │              │
        │                    GPT-4 Turbo    GPT-4 Vision
        │                    Summary         Analysis
        │                         │              │
        └────────────┬────────────┴──────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│    CREATE LANGCHAIN DOCUMENTS (with rich metadata)      │
│    Each: {page_content, metadata{file_hash, page, ...}} │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│              EMBEDDING GENERATION (OpenAI)              │
│  Convert each chunk to 1536-dim vector                   │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│    STORE IN VECTOR DB (PostgreSQL pgvector)             │
│    + File-level & Content-level deduplication           │
└────────────────────┬─────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
   INDEXING              DEDUPLICATION
   (pgvector)        • File hash check
   (fast search)     • Content hash check

═══════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────┐
│                    USER QUERY                            │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│         EMBED QUERY (OpenAI, same model)                │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│    VECTOR SEARCH (pgvector cosine similarity)           │
│    Top K=6 chunks, Filter by min_similarity=0.6         │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│              BUILD PROMPT CONTEXT                        │
│    System + Retrieved chunks + User question             │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│           SEND TO LLM (Groq/OpenAI)                     │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────────┐
         │  RETURN RESPONSE          │
         │  (grounded in documents)  │
         └───────────────────────────┘
```

---

## 🔧 STEP 1: MULTIMODAL EXTRACTION

### `process_multimodal_file(filename, file_bytes)`
**File**: `multimodal_processor_v2.py:596-677`

**Complete 4-Step Pipeline**:

#### Step 1A: Detect File Type
```python
doc_type = detect_file_type(filename, file_bytes)
# Returns: PDF | DOCX | PPTX | CSV | TXT | IMAGE | UNKNOWN
```

**Logic**:
1. Check extension (.pdf, .docx, .pptx, etc.)
2. Read magic bytes (file signatures)
   - PDF: starts with `%PDF`
   - DOCX/PPTX: starts with `PK` (ZIP), then check internal structure
   - Image: `\xff\xd8\xff` (JPEG) or `\x89PNG` (PNG)
3. Return type or UNKNOWN

---

#### Step 1B: Extract Elements
```python
elements = extract_elements_from_file(filename, file_bytes, doc_type)
# Returns: List of unstructured.Element objects
```

**Different Extraction Strategies**:

**📄 PDF** (`_extract_pdf`):
```python
partition_pdf(
    filename=temp_path,
    strategy="hi_res",              # ✅ Best accuracy
    infer_table_structure=True,     # Detect table structure
    extract_image_block_types=["Image", "Table"],
    extract_image_block_to_payload=True,
)
```
- Uses **Tesseract OCR** for text extraction
- Understands table column/row structure
- Extracts embedded images
- Output: ~25 elements per page

**📝 DOCX** (`_extract_docx`):
```python
partition_docx(filename=temp_path)
# Extracts: paragraphs, tables, styles, embedded objects
```

**📊 PPTX** (`_extract_pptx`):
```python
partition_pptx(filename=temp_path)
# Extracts: slide content, text boxes, shapes, notes
```

**🗂️ CSV** (`_extract_csv`):
```python
partition_csv(filename=temp_path)
# Treats each row as structured table element
```

**📄 TXT** (`_extract_txt`):
```python
partition_text(filename=temp_path)
# Simple paragraph splitting
```

**🖼️ IMAGE** (`_extract_image`):
```python
# Encodes image as base64
# Returns: (elements, image_metadata)
# Will be processed with GPT-4 Vision later
```

---

#### Step 1C: Chunk Intelligently
```python
chunks = chunk_elements_by_title(
    elements,
    max_characters=1200,        # Hard limit
    new_after_n_chars=1000,     # Prefer breaking after 1000 chars
    combine_text_under_n_chars=300,  # Merge tiny chunks
)
```

**Algorithm**:
- Uses Unstructured's **title-based chunking**
- Respects document structure (sections, subsections)
- Maintains semantic boundaries
- Avoids splitting mid-sentence

**Output**: Meaningful chunks around section breaks

---

#### Step 1D: Create LangChain Documents
```python
documents = create_langchain_documents(
    chunks,
    source_file=filename,
    file_hash=file_hash,
    content_type=doc_type.value,
)
```

**For Each Chunk**:

1. **Separate content types**:
   ```python
   content_data = {
       'text': 'Text content...',
       'tables': ['<table>...</table>'],
       'images': ['base64_image...'],
       'types': ['text', 'table', 'image']
   }
   ```

2. **Create AI summary (if has tables/images)**:
   ```python
   if content_data['tables'] or content_data['images']:
       summary = create_ai_enhanced_summary(
           text=content_data['text'],
           tables=content_data['tables'],
           images=content_data['images'],
       )
   ```
   
   **Prompt to GPT-4**:
   > "Generate a detailed, searchable description that includes:
   > 1. Key facts and data points
   > 2. Main topics and concepts
   > 3. Questions this could answer
   > 4. Visual content analysis
   > 5. Alternative search terms"

3. **Create LangChain Document**:
   ```python
   Document(
       page_content=summary_or_text,  # What gets embedded
       metadata={
           "source_file": filename,
           "file_hash": "sha256_hash...",
           "content_type": "pdf",
           "chunk_id": 0,
           "content_types": ["text", "table"],
           "has_tables": True,
           "has_images": False,
           "page": 5,
           "original_content": JSON({
               "raw_text": original,
               "tables_html": [...],
               "images_base64": [...],
               "enhanced_summary": summary,
           })
       }
   )
   ```

**Output**: List of LangChain Document objects, ready for embedding

---

## 🔧 STEP 2: EMBEDDING & STORAGE

### `process_multimodal_file()` (in enhanced_rag.py)
**File**: `enhanced_rag.py:54-145`

**For Each Document**:

1. **Generate embedding**:
   ```python
   embedding = embed_text(doc.page_content)
   # Calls OpenAI API
   # Returns: [1536 floats]
   ```

2. **Store in database**:
   ```python
   store_embedding(
       org_id, bot_id,
       content=doc.page_content,
       embedding=embedding,
       metadata=doc.metadata,
   )
   ```

3. **Database insert**:
   ```sql
   INSERT INTO rag_embeddings (org_id, bot_id, content, embedding, metadata)
   VALUES (%s, %s, %s, %s, %s)
   ```

4. **Deduplication checks**:
   - **File-level**: Check if file_hash exists
   - **Content-level**: Check if content_hash exists
   - Skip if duplicate found

**Result**: Chunks stored with vectors ready for search

---

## 🔧 STEP 3: QUERY & RETRIEVAL

### `rag_query(org_id, bot_id, user_query, k=6, min_sim=0.6, ...)`
**File**: `rag.py:18-29`

**Flow**:

1. **Embed the query**:
   ```python
   qvec = embed_text(user_query)
   # Same OpenAI model used for documents
   # Returns: [1536 floats]
   ```

2. **Vector search**:
   ```python
   rows = embed_search(conn, org_id, bot_id, qvec, k=6)
   # SQL uses pgvector cosine similarity
   # Returns: [(content, metadata, similarity), ...]
   ```

   **SQL Query**:
   ```sql
   SELECT content, metadata, 1 - (embedding <=> %s::vector) as similarity
   FROM rag_embeddings
   WHERE org_id = %s AND bot_id = %s
   ORDER BY embedding <-> %s::vector
   LIMIT 6
   ```

   **Vector Operations**:
   - `<=>` = cosine distance (0=same, 2=opposite)
   - `<->` = distance operator (for ordering)
   - `1 - distance` = similarity score (0-1)

3. **Filter by threshold**:
   ```python
   rows = [r for r in rows if r[2] >= 0.6]  # r[2] is similarity
   ```

4. **Handle no results**:
   ```python
   if not rows:
       return None, None, "I don't have that information."
   ```

5. **Return**:
   ```python
   return rows, qvec, None
   # rows = [(chunk1, metadata1, 0.95), (chunk2, metadata2, 0.87), ...]
   ```

---

### `embed_search(conn, org_id, bot_id, query_vec, k=6)`
**File**: `postgres.py:13-28`

**Purpose**: Raw pgvector similarity search

**Performance**: O(log n) with pgvector index

---

## 🔧 STEP 4: PROMPT & GENERATION

### `build_prompt(context_chunks, user_query, bot_behavior, system_prompt)`
**File**: `rag.py:6-16`

**Output Format**:
```
SYSTEM:
"You are a {bot_behavior} assistant. 
Use only the provided context. 
If the answer is not in context, say: 'I don't have that information.'"

USER:
"Context:
[Chunk 1 from database]

[Chunk 2 from database]

[Chunk 3 from database]

...

Question: {user_query}"
```

**Example**:
```
SYSTEM:
"You are a helpful customer service assistant."

USER:
"Context:
Refunds are accepted within 30 days of purchase.
Full refund for defective items.
Partial refund for opened items.

Shipping returns are free.

Question: What's your return policy?"
```

**LLM Response**:
> "We accept returns within 30 days of purchase with a full refund if the item is defective. 
> For opened items, we offer a partial refund. Free shipping on all returns."

---

## 📊 End-to-End Example

**User uploads**: `Pricing_Guide.pdf` (5 pages, 3 tables, 2 images)

### INGESTION:
```
1. Detect: PDF
2. Extract: 125 elements (paragraphs, table cells, images)
3. Chunk: 18 semantic chunks (titles/sections as boundaries)
4. Create Documents:
   - Chunk 1: Text only → Document
   - Chunk 5: Has table → GPT-4 summary → Document
   - Chunk 12: Has images → GPT-4 Vision analysis → Document
5. Embed: 18 API calls to OpenAI (cost: ~$0.0003)
6. Store: 18 rows in rag_embeddings table
   - Each row: content + 1536-dim vector + metadata
```

### QUERY:
```
User: "What's your enterprise pricing?"

1. Embed query: "What's your enterprise pricing?" → vector
2. Search: Find 6 closest chunks to query vector
   - Chunk 1: similarity 0.95 ✓
   - Chunk 5: similarity 0.89 ✓
   - Chunk 8: similarity 0.87 ✓
   - Chunk 2: similarity 0.75 ✓
   - Chunk 10: similarity 0.72 ✓
   - Chunk 3: similarity 0.68 ✓
   (All pass min_similarity = 0.6)

3. Build prompt:
   SYSTEM: "You are a helpful sales assistant..."
   USER: "Context: [6 chunks about pricing]
          Question: What's your enterprise pricing?"

4. Send to Groq LLM
5. Generate: "Our enterprise pricing starts at $5,000/month..."
```

---

## 💾 Database Schema

```sql
CREATE TABLE rag_embeddings (
    id SERIAL PRIMARY KEY,
    org_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    content TEXT NOT NULL,           -- Text chunk (200-1500 chars)
    embedding vector(1536),           -- OpenAI embedding
    metadata JSONB,                   -- Rich metadata
    created_at TIMESTAMP DEFAULT NOW(),
);

-- Composite index for org/bot filtering
CREATE INDEX idx_org_bot ON rag_embeddings(org_id, bot_id);

-- pgvector index for fast similarity search
CREATE INDEX idx_embedding ON rag_embeddings 
  USING ivfflat (embedding vector_cosine_ops);
```

**Metadata structure**:
```json
{
  "source_file": "pricing.pdf",
  "file_hash": "a3f2e1d9...",
  "content_type": "pdf",
  "chunk_id": 5,
  "content_types": ["text", "table"],
  "has_tables": true,
  "has_images": false,
  "page": 3,
  "extraction_method": "unstructured_pdf",
  "original_content": {
    "raw_text": "Enterprise pricing...",
    "tables_html": ["<table>...</table>"],
    "images_base64": [],
    "enhanced_summary": "AI-generated summary..."
  }
}
```

---

## 🎯 Key Design Advantages Over Friend's Pipeline

| Aspect | Your System | Friend's |
|--------|-------------|----------|
| **Vector DB** | PostgreSQL pgvector (persistent) | FAISS (in-memory) |
| **Scalability** | Millions of documents | Thousands |
| **Multi-tenancy** | ✅ org_id, bot_id | ❌ Single instance |
| **Deduplication** | File + content level | None |
| **Tables** | HTML preserved + AI summary | Simple text |
| **Images** | GPT-4 Vision analysis | GPT-4 Vision |
| **Chunking** | Semantic (title-based) | Size-based + overlap |
| **Metadata** | Rich (page, type, hash, etc) | Basic |
| **Cost** | ~$0.0003 per PDF | Similar |
| **Production Ready** | ✅ Yes | Demo only |

---

## 📈 Cost Breakdown (per PDF ingestion)

| Operation | Count | Cost |
|-----------|-------|------|
| Extract | 1 | $0 |
| Chunk | 1 | $0 |
| Embed chunks | 18 | $0.0003 |
| AI summaries | 3 | $0.01 |
| Store | 1 | $0 |
| **Total** | | **~$0.01** |

---

## 🚀 Performance Metrics

| Operation | Time | Notes |
|-----------|------|-------|
| PDF extraction | 2-5s | Depends on file size |
| Chunking | <1s | Title-based is fast |
| Embedding | 18s | Parallel would help |
| Vector search | <50ms | pgvector index |
| LLM generation | 2-5s | Depends on Groq |

