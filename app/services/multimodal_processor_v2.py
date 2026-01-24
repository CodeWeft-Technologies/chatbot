"""
Multimodal RAG processing using Unstructured library.

Architecture:
1. Extract: partition_pdf/partition_image → raw elements
2. Chunk: chunk_by_title → intelligent semantic chunks
3. Enrich: Analyze content types (text, tables, images)
4. Convert: LangChain Document with rich metadata
"""

import io
import logging
import hashlib
import os
import json
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum
from pathlib import Path

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# For AI summaries
_openai_client = None


def _get_openai_client():
    """Get or create OpenAI client"""
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client: {e}")
    return _openai_client


class DocumentType(Enum):
    """Supported document types"""
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    CSV = "csv"
    TXT = "txt"
    IMAGE = "image"
    UNKNOWN = "unknown"


def detect_file_type(filename: str, file_bytes: Optional[bytes] = None) -> DocumentType:
    """
    Detect document type by extension and file signature.
    
    Args:
        filename: Filename with extension
        file_bytes: Optional file bytes for magic number detection
    
    Returns:
        DocumentType enum
    """
    ext = Path(filename).suffix.lower()
    
    ext_map = {
        ".pdf": DocumentType.PDF,
        ".docx": DocumentType.DOCX,
        ".doc": DocumentType.DOCX,
        ".pptx": DocumentType.PPTX,
        ".ppt": DocumentType.PPTX,
        ".csv": DocumentType.CSV,
        ".txt": DocumentType.TXT,
        ".png": DocumentType.IMAGE,
        ".jpg": DocumentType.IMAGE,
        ".jpeg": DocumentType.IMAGE,
        ".gif": DocumentType.IMAGE,
        ".webp": DocumentType.IMAGE,
    }
    
    if ext in ext_map:
        return ext_map[ext]
    
    if file_bytes:
        if file_bytes.startswith(b"%PDF"):
            return DocumentType.PDF
        if file_bytes.startswith(b"PK"):
            try:
                import zipfile
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    if "[Content_Types].xml" in zf.namelist():
                        for name in zf.namelist():
                            if name.startswith("ppt/"):
                                return DocumentType.PPTX
                            if name.startswith("word/"):
                                return DocumentType.DOCX
            except Exception:
                pass
        if file_bytes.startswith(b"\xff\xd8\xff"):
            return DocumentType.IMAGE
        if file_bytes.startswith(b"\x89PNG"):
            return DocumentType.IMAGE
    
    return DocumentType.UNKNOWN


async def extract_elements_from_file(
    filename: str,
    file_bytes: bytes,
    doc_type: Optional[DocumentType] = None,
) -> Union[List[Any], Tuple[List[Any], Dict[str, Any]]]:
    """
    Extract structured elements from document using Unstructured library.
    
    Args:
        filename: Original filename
        file_bytes: File contents
        doc_type: Optional pre-detected document type
    
    Returns:
        For standalone images: Tuple of (elements, image_metadata)
        For other docs: List of unstructured Element objects
    """
    if doc_type is None:
        doc_type = detect_file_type(filename, file_bytes)
    
    logger.info(f"[EXTRACT] {filename} (type: {doc_type.value})")
    
    try:
        if doc_type == DocumentType.PDF:
            return await _extract_pdf(file_bytes, filename)
        elif doc_type == DocumentType.DOCX:
            return await _extract_docx(file_bytes)
        elif doc_type == DocumentType.PPTX:
            return await _extract_pptx(file_bytes)
        elif doc_type == DocumentType.CSV:
            return await _extract_csv(file_bytes)
        elif doc_type == DocumentType.IMAGE:
            return await _extract_image(file_bytes)  # Returns (elements, metadata)
        elif doc_type == DocumentType.TXT:
            return await _extract_txt(file_bytes)
        else:
            raise ValueError(f"Unsupported document type: {doc_type.value}")
    
    except Exception as e:
        logger.error(f"[EXTRACT-ERROR] Failed to extract {filename}: {e}")
        raise


async def _extract_pdf(file_bytes: bytes, filename: str) -> List[Any]:
    """Extract PDF elements using unstructured partition_pdf with hi_res only"""
    try:
        from unstructured.partition.pdf import partition_pdf
        
        # Try to locate poppler on Windows
        import sys
        if sys.platform == "win32":
            # Check common poppler installation paths
            poppler_paths = [
                r"C:\ProgramData\chocolatey\lib\poppler\tools\poppler-26.01.0\Library\bin",
                r"C:\Program Files\poppler\Library\bin",
                r"C:\Program Files (x86)\poppler\Library\bin",
                os.path.expandvars(r"%APPDATA%\poppler\Library\bin"),
            ]
            for poppler_bin in poppler_paths:
                if os.path.exists(poppler_bin):
                    os.environ["PATH"] = f"{poppler_bin};{os.environ.get('PATH', '')}"
                    logger.info(f"[EXTRACT-PDF] Found poppler at: {poppler_bin}")
                    break
        
        # Save to temp file (unstructured requires file path)
        temp_path = f"/tmp/{hashlib.md5(file_bytes).hexdigest()}.pdf"
        os.makedirs("/tmp", exist_ok=True)
        
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        
        # Use hi_res strategy only - minimal parameters to avoid decorator issues
        logger.info(f"[EXTRACT-PDF] Using hi_res strategy for {filename}...")
        elements = partition_pdf(
            filename=temp_path,
            strategy="hi_res",
            infer_table_structure=True,
            extract_image_block_types=["Image", "Table"],
            extract_image_block_to_payload=True,
        )
        logger.info(f"[EXTRACT] PDF (hi_res): {len(elements)} elements from {filename}")
        return elements
    
    except Exception as e:
        logger.error(f"[EXTRACT-PDF] Hi_res extraction failed: {e}")
        raise


async def _extract_docx(file_bytes: bytes) -> List[Any]:
    """Extract DOCX elements using unstructured"""
    try:
        from unstructured.partition.docx import partition_docx
        
        temp_path = f"/tmp/{hashlib.md5(file_bytes).hexdigest()}.docx"
        os.makedirs("/tmp", exist_ok=True)
        
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        
        elements = partition_docx(filename=temp_path)
        logger.info(f"[EXTRACT] DOCX: {len(elements)} elements")
        return elements
    
    except Exception as e:
        logger.error(f"[EXTRACT-DOCX] Error: {e}")
        raise


async def _extract_pptx(file_bytes: bytes) -> List[Any]:
    """Extract PPTX elements using unstructured"""
    try:
        from unstructured.partition.pptx import partition_pptx
        
        temp_path = f"/tmp/{hashlib.md5(file_bytes).hexdigest()}.pptx"
        os.makedirs("/tmp", exist_ok=True)
        
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        
        elements = partition_pptx(filename=temp_path)
        logger.info(f"[EXTRACT] PPTX: {len(elements)} elements")
        return elements
    
    except Exception as e:
        logger.error(f"[EXTRACT-PPTX] Error: {e}")
        raise


async def _extract_csv(file_bytes: bytes) -> List[Any]:
    """Extract CSV elements using unstructured"""
    try:
        from unstructured.partition.csv import partition_csv
        
        temp_path = f"/tmp/{hashlib.md5(file_bytes).hexdigest()}.csv"
        os.makedirs("/tmp", exist_ok=True)
        
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        
        elements = partition_csv(filename=temp_path)
        logger.info(f"[EXTRACT] CSV: {len(elements)} elements")
        return elements
    
    except Exception as e:
        logger.error(f"[EXTRACT-CSV] Error: {e}")
        raise


async def _extract_image(file_bytes: bytes) -> Tuple[List[Any], Dict[str, Any]]:
    """Extract standalone image as base64 for direct LLM processing
    
    Returns:
        Tuple of (elements, image_metadata) where image_metadata contains:
        - base64_image: Base64 encoded image
        - image_format: Image format (jpg, png, etc.)
        - dimensions: Image dimensions
        - processing_mode: 'direct_llm' for standalone images
    """
    try:
        from unstructured.documents.elements import Text as TextElement
        import base64
        
        logger.info("[EXTRACT-IMAGE] Preparing standalone image for LLM processing...")
        
        # Encode image as base64
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        # Detect image format
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes))
            img_format = img.format.lower() if img.format else "jpg"
            dimensions = f"{img.size[0]}×{img.size[1]}"
        except:
            img_format = "jpg"
            dimensions = "unknown"
        
        logger.info(f"[EXTRACT-IMAGE] Image format: {img_format}, dimensions: {dimensions}")
        
        # Create simple text element for placeholder
        placeholder = TextElement(text=f"Standalone image ({dimensions}, {img_format})")
        
        # Return both element and metadata
        image_metadata = {
            "base64_image": base64_image,
            "image_format": img_format,
            "dimensions": dimensions,
            "processing_mode": "direct_llm"
        }
        
        logger.info("[EXTRACT-IMAGE] ✅ Image prepared for direct LLM summarization")
        return [placeholder], image_metadata
    
    except Exception as e:
        logger.error(f"[EXTRACT-IMAGE] Error: {e}")
        raise


async def _extract_txt(file_bytes: bytes) -> List[Any]:
    """Extract TXT elements"""
    try:
        from unstructured.partition.text import partition_text
        
        content = file_bytes.decode("utf-8", errors="replace")
        temp_path = f"/tmp/{hashlib.md5(file_bytes).hexdigest()}.txt"
        os.makedirs("/tmp", exist_ok=True)
        
        with open(temp_path, "w") as f:
            f.write(content)
        
        elements = partition_text(filename=temp_path)
        logger.info(f"[EXTRACT] TXT: {len(elements)} elements")
        return elements
    
    except Exception as e:
        logger.error(f"[EXTRACT-TXT] Error: {e}")
        raise


def chunk_elements_by_title(
    elements: List[Any],
    max_characters: int = 1200,
    new_after_n_chars: int = 1000,
    combine_text_under_n_chars: int = 300,
) -> List[Any]:
    """
    Create intelligent chunks using title-based semantic strategy.
    
    This respects document structure (titles, sections) and creates
    meaningful, smaller chunks.
    
    Args:
        elements: Extracted document elements
        max_characters: Hard limit for chunk size
        new_after_n_chars: Try to start new chunk after this many chars
        combine_text_under_n_chars: Merge tiny chunks under this size
    
    Returns:
        List of chunked elements
    """
    try:
        from unstructured.chunking.title import chunk_by_title
        
        chunks = chunk_by_title(
            elements,
            max_characters=max_characters,
            new_after_n_chars=new_after_n_chars,
            combine_text_under_n_chars=combine_text_under_n_chars,
        )
        
        logger.info(f"[CHUNK] Created {len(chunks)} chunks using title-based strategy")
        return chunks
    
    except Exception as e:
        logger.error(f"[CHUNK-ERROR] Failed to chunk elements: {e}")
        raise


def separate_content_types(chunk: Any) -> Dict[str, Any]:
    """
    Analyze what types of content are in a chunk.
    
    Returns dict with:
    - text: Main text content
    - tables: List of table HTML
    - images: List of image base64
    - types: List of content types found
    
    Args:
        chunk: Unstructured chunk object
    
    Returns:
        Dict with separated content
    """
    content_data = {
        'text': chunk.text,
        'tables': [],
        'images': [],
        'types': set(['text'])
    }
    
    try:
        # Check for tables and images in original elements
        if hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'orig_elements'):
            for element in chunk.metadata.orig_elements:
                element_type = type(element).__name__
                
                # Handle tables
                if element_type == 'Table':
                    content_data['types'].add('table')
                    
                    # Try to get HTML representation
                    if hasattr(element, 'metadata') and hasattr(element.metadata, 'text_as_html'):
                        table_html = element.metadata.text_as_html
                    else:
                        table_html = element.text
                    
                    content_data['tables'].append(table_html)
                    logger.debug(f"[CONTENT] Found table in chunk")
                
                # Handle images
                elif element_type == 'Image':
                    content_data['types'].add('image')
                    
                    if hasattr(element, 'metadata') and hasattr(element.metadata, 'image_base64'):
                        image_b64 = element.metadata.image_base64
                        content_data['images'].append(image_b64)
                        logger.debug(f"[CONTENT] Found image in chunk")
    
    except Exception as e:
        logger.warning(f"[CONTENT-ERROR] Error analyzing chunk content: {e}")
    
    content_data['types'] = list(content_data['types'])
    return content_data


def create_ai_enhanced_summary(
    text: str,
    tables: List[str],
    images: List[str],
) -> str:
    """
    Create AI-enhanced summary for chunks with images/tables using GPT-4 Vision.
    
    Args:
        text: Text content
        tables: List of table HTML
        images: List of image base64
    
    Returns:
        Enhanced summary optimized for search and retrieval
    """
    try:
        client = _get_openai_client()
        if not client:
            logger.debug("[SUMMARY] No OpenAI client - skipping AI summary")
            return text
        
        # Build the text prompt
        prompt_text = f"""You are creating a comprehensive, searchable description for RAG document retrieval.

TEXT CONTENT:
{text}
"""
        
        # Add tables if present
        if tables:
            prompt_text += "\nTABLES:\n"
            for i, table in enumerate(tables):
                prompt_text += f"Table {i+1}:\n{table}\n\n"
        
        prompt_text += """
YOUR TASK:
Generate a detailed, searchable description that includes:
1. Key facts, numbers, and data points from text and tables
2. Main topics and concepts discussed
3. Questions this content could answer
4. Visual content analysis (charts, diagrams, patterns in images)
5. Alternative search terms users might use

Make it comprehensive and findable - optimize for search relevance.

DESCRIPTION:"""

        # Build message content
        message_content = [{"type": "text", "text": prompt_text}]
        
        # Add images to the message for vision analysis
        for image_base64 in images:
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
        
        # Call GPT-4 Turbo with vision
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "user",
                    "content": message_content
                }
            ],
            max_tokens=800,
        )
        
        summary = response.choices[0].message.content
        logger.info(f"[SUMMARY] AI summary created: {len(summary)} chars")
        return summary
    
    except Exception as e:
        logger.debug(f"[SUMMARY] AI summary failed: {e} - using original text")
        # Fallback to original text with metadata hints
        summary = text
        if tables:
            summary += f"\n\n[Contains {len(tables)} table(s)]"
        if images:
            summary += f"\n[Contains {len(images)} image(s)]"
        return summary


def create_langchain_documents(
    chunks: List[Any],
    source_file: str,
    file_hash: str,
    content_type: str,
    standalone_image_meta: Optional[Dict[str, Any]] = None,
) -> List[Document]:
    """
    Convert unstructured chunks to LangChain Documents with rich metadata.
    
    Args:
        chunks: List of chunked elements from unstructured
        source_file: Original filename
        file_hash: SHA-256 hash of file for deduplication
        content_type: Document type (pdf, docx, etc.)
    
    Returns:
        List of LangChain Document objects
    """
    documents = []
    
    logger.info(f"[LANGCHAIN] Converting {len(chunks)} chunks to LangChain Documents")
    
    # Handle standalone images separately
    if standalone_image_meta:
        logger.info("[LANGCHAIN] Processing standalone image with LLM...")
        base64_image = standalone_image_meta.get('base64_image')
        image_format = standalone_image_meta.get('image_format', 'jpg')
        
        try:
            logger.info("[LANGCHAIN] Summarizing image with GPT-4 Turbo...")
            from openai import OpenAI
            client = OpenAI()
            
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Provide a comprehensive, detailed description of this image that would be useful for search and retrieval. Include: main subjects, text visible, layout, colors, any diagrams or charts, and key details."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
            )
            
            enhanced_content = response.choices[0].message.content
            logger.info(f"[LANGCHAIN] LLM generated {len(enhanced_content)} char summary for image")
            
            # Create single LangChain document for standalone image
            metadata = {
                "source_file": source_file,
                "file_hash": file_hash,
                "content_type": content_type,
                "chunk_id": 0,
                "is_standalone_image": True,
                "image_format": image_format,
                "dimensions": standalone_image_meta.get('dimensions', 'unknown'),
            }
            
            doc = Document(
                page_content=enhanced_content,
                metadata=metadata,
            )
            documents.append(doc)
            logger.info("[LANGCHAIN] ✅ Created LangChain Document for standalone image")
            return documents
        
        except Exception as llm_err:
            logger.error(f"[LANGCHAIN] LLM processing failed: {llm_err}")
            # Fallback: create document with basic metadata
            metadata = {
                "source_file": source_file,
                "file_hash": file_hash,
                "content_type": content_type,
                "chunk_id": 0,
                "is_standalone_image": True,
                "error": str(llm_err),
            }
            doc = Document(
                page_content=f"Image ({standalone_image_meta.get('dimensions', 'unknown')})",
                metadata=metadata,
            )
            documents.append(doc)
            return documents
    
    # Regular chunk processing for non-image documents
    for idx, chunk in enumerate(chunks):
        try:
            # Regular chunk processing
            content_data = separate_content_types(chunk)
            
            # Create AI summary if chunk has tables/images
            if content_data['tables'] or content_data['images']:
                logger.info(f"[LANGCHAIN] Creating AI summary for chunk {idx} (tables={len(content_data['tables'])}, images={len(content_data['images'])})")
                enhanced_content = create_ai_enhanced_summary(
                    content_data['text'],
                    content_data['tables'],
                    content_data['images'],
                )
            else:
                enhanced_content = content_data['text']
            
            # Create metadata
            metadata = {
                "source_file": source_file,
                "file_hash": file_hash,
                "content_type": content_type,
                "chunk_id": idx,
                "content_types": content_data['types'],
                "has_tables": len(content_data['tables']) > 0,
                "has_images": len(content_data['images']) > 0,
            }
            
            # Store original content as JSON string
            original_content = {
                "raw_text": content_data['text'],
                "tables_html": content_data['tables'],
                "images_base64": content_data['images'],
                "enhanced_summary": enhanced_content if (content_data['tables'] or content_data['images']) else None,
            }
            metadata["original_content"] = json.dumps(original_content)
            
            # Add page/slide info if available
            if hasattr(chunk, 'metadata'):
                if hasattr(chunk.metadata, 'page_number'):
                    metadata['page'] = chunk.metadata.page_number
                if hasattr(chunk.metadata, 'slide_number'):
                    metadata['slide'] = chunk.metadata.slide_number
            
            # Create LangChain Document with enhanced content
            doc = Document(
                page_content=enhanced_content,
                metadata=metadata
            )
            
            documents.append(doc)
            logger.debug(f"[LANGCHAIN] Created Document #{idx + 1}: types={content_data['types']}")
        
        except Exception as e:
            logger.error(f"[LANGCHAIN-ERROR] Failed to create document for chunk {idx}: {e}")
            continue
    
    logger.info(f"[LANGCHAIN] ✅ Created {len(documents)} LangChain Documents with AI summaries")
    return documents


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file for deduplication"""
    return hashlib.sha256(file_bytes).hexdigest()


async def process_multimodal_file(
    filename: str,
    file_bytes: bytes,
) -> Tuple[List[Document], Dict[str, Any]]:
    """
    Complete pipeline: Extract → Chunk → Convert to LangChain Documents
    
    Args:
        filename: Original filename
        file_bytes: File contents
    
    Returns:
        Tuple of (documents, metadata)
    """
    logger.info(f"[PIPELINE] Starting multimodal processing for {filename}")
    
    try:
        # Step 1: Detect file type
        doc_type = detect_file_type(filename, file_bytes)
        logger.info(f"[PIPELINE] Detected type: {doc_type.value}")
        
        # Step 2: Extract elements
        extract_result = await extract_elements_from_file(filename, file_bytes, doc_type)
        
        # Handle standalone images differently
        standalone_image_meta = None
        if doc_type == DocumentType.IMAGE and isinstance(extract_result, tuple):
            elements, standalone_image_meta = extract_result
            logger.info(f"[PIPELINE] Extracted standalone image - will process directly with LLM")
        else:
            elements = extract_result
            logger.info(f"[PIPELINE] Extracted {len(elements)} elements")
        
        # Check if extraction failed (empty elements)
        if not elements:
            logger.warning(f"[PIPELINE] No elements extracted from {filename}")
            return [], {"error": "No content extracted from file", "filename": filename}
        
        # Step 3: Chunk by title (skip for standalone images)
        if standalone_image_meta:
            logger.info(f"[PIPELINE] Skipping chunking for standalone image - direct LLM processing")
            chunks = elements  # Use as-is
        else:
            chunks = chunk_elements_by_title(elements)
            logger.info(f"[PIPELINE] Created {len(chunks)} chunks")
            
            # Check if chunking produced results
            if not chunks:
                logger.warning(f"[PIPELINE] Chunking produced no chunks for {filename}")
                return [], {"error": "No chunks created after processing", "filename": filename}
        
        # Step 4: Convert to LangChain Documents
        file_hash = compute_file_hash(file_bytes)
        documents = create_langchain_documents(
            chunks,
            source_file=filename,
            file_hash=file_hash,
            content_type=doc_type.value,
            standalone_image_meta=standalone_image_meta,
        )
        
        # Summary metadata
        metadata = {
            "filename": filename,
            "file_hash": file_hash,
            "content_type": doc_type.value,
            "total_elements": len(elements),
            "total_chunks": len(chunks),
            "total_documents": len(documents),
            "file_size": len(file_bytes),
        }
        
        logger.info(f"[PIPELINE] ✅ Complete: {len(documents)} documents ready for embedding")
        return documents, metadata
    
    except Exception as e:
        logger.error(f"[PIPELINE-ERROR] Processing failed: {e}")
        raise
