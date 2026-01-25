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
import base64
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum
from pathlib import Path

from langchain_core.documents import Document
import google.generativeai as genai

logger = logging.getLogger(__name__)

# For AI summaries
_openai_client = None
_gemini_model = None


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


def _get_gemini_model():
    """Get or create Gemini model (vision-capable)."""
    global _gemini_model
    if _gemini_model is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set; Gemini features disabled")
            return None
        try:
            genai.configure(api_key=api_key)
            model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-pro")
            _gemini_model = genai.GenerativeModel(
                model_name,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 800
                },
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini model: {e}")
            _gemini_model = None
    return _gemini_model


class DocumentType(Enum):
    """Supported document types"""
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
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
        ".xlsx": DocumentType.XLSX,
        ".xls": DocumentType.XLSX,
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
        elif doc_type == DocumentType.XLSX:
            return await _extract_xlsx(file_bytes)
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


async def _extract_xlsx(file_bytes: bytes) -> List[Any]:
    """Extract XLSX elements using unstructured"""
    try:
        from unstructured.partition.xlsx import partition_xlsx
        
        temp_path = f"/tmp/{hashlib.md5(file_bytes).hexdigest()}.xlsx"
        os.makedirs("/tmp", exist_ok=True)
        
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        
        elements = partition_xlsx(filename=temp_path)
        logger.info(f"[EXTRACT] XLSX: {len(elements)} elements")
        return elements
    
    except Exception as e:
        logger.error(f"[EXTRACT-XLSX] Error: {e}")
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
    
    OPTIMIZATION: Compresses images to reduce token usage with Gemini
    
    Returns:
        Tuple of (elements, image_metadata) where image_metadata contains:
        - base64_image: Base64 encoded image (compressed)
        - image_format: Image format (jpg, png, etc.)
        - dimensions: Original image dimensions
        - compressed_size: Size after compression
        - processing_mode: 'direct_llm' for standalone images
    """
    try:
        from unstructured.documents.elements import Text as TextElement
        from PIL import Image
        
        logger.info("[EXTRACT-IMAGE] Preparing standalone image for LLM processing...")
        
        # Step 1: Open and get original dimensions
        img = Image.open(io.BytesIO(file_bytes))
        img_format = img.format.lower() if img.format else "jpg"
        original_dimensions = f"{img.size[0]}×{img.size[1]}"
        original_size_kb = len(file_bytes) / 1024
        
        logger.info(f"[EXTRACT-IMAGE] Original: {original_dimensions}, {original_size_kb:.1f}KB")
        
        # Step 2: Resize image to reduce tokens (max 1024px on longest side)
        # Gemini tokens scale with image resolution, so resizing saves a lot
        max_dimension = 1024
        if img.size[0] > max_dimension or img.size[1] > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"[EXTRACT-IMAGE] Resized to: {new_size[0]}×{new_size[1]} (reduced tokens)")
        
        # Step 3: Compress image (quality trade-off for token savings)
        # Convert RGBA to RGB for JPEG compression
        if img.mode == 'RGBA':
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3])
            img = rgb_img
        
        # Save compressed to BytesIO
        compressed_bytes = io.BytesIO()
        quality = 80  # Balance between quality and token usage
        img.save(compressed_bytes, format='JPEG', quality=quality, optimize=True)
        compressed_bytes.seek(0)
        compressed_data = compressed_bytes.getvalue()
        
        # Step 4: Encode as base64
        base64_image = base64.b64encode(compressed_data).decode('utf-8')
        compressed_size_kb = len(compressed_data) / 1024
        
        logger.info(f"[EXTRACT-IMAGE] 💰 Compressed: {compressed_size_kb:.1f}KB (saved {original_size_kb - compressed_size_kb:.1f}KB, {100*(1-compressed_size_kb/original_size_kb):.0f}% reduction)")
        
        # Create simple text element for placeholder
        placeholder = TextElement(text=f"Standalone image ({original_dimensions}, {img_format})")
        
        # Return both element and metadata
        image_metadata = {
            "base64_image": base64_image,
            "image_format": "jpg",  # Now always JPEG after compression
            "original_dimensions": original_dimensions,
            "compressed_size_kb": compressed_size_kb,
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


def _detect_image_mime_type(base64_str: str) -> str:
    """
    Detect MIME type from base64 magic bytes.
    
    Args:
        base64_str: Base64 encoded image string
    
    Returns:
        MIME type string (e.g., 'image/jpeg', 'image/png')
    """
    try:
        import base64 as b64_module
        # Decode first few bytes to check magic numbers
        decoded = b64_module.b64decode(base64_str[:100])
        
        if decoded.startswith(b'\x89PNG'):
            return 'image/png'
        elif decoded.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        elif decoded.startswith(b'RIFF') and b'WEBP' in decoded[:20]:
            return 'image/webp'
        elif decoded.startswith(b'GIF8'):
            return 'image/gif'
        else:
            return 'image/jpeg'  # Default fallback
    except Exception:
        return 'image/jpeg'  # Default fallback


def _compress_base64_image(image_b64: str, max_dimension: int = 1024, quality: int = 80) -> str:
    """
    Compress base64 encoded image to reduce Gemini token usage.
    
    Optimization: Reduces image size by resizing and reducing quality.
    This significantly reduces token consumption in Gemini API calls.
    
    Args:
        image_b64: Base64 encoded image string
        max_dimension: Max pixel dimension (default 1024)
        quality: JPEG quality 1-100 (default 80)
    
    Returns:
        Compressed base64 image string
    """
    try:
        import base64 as b64_module
        from PIL import Image
        
        # Decode base64 to bytes
        image_bytes = b64_module.b64decode(image_b64)
        original_size_kb = len(image_bytes) / 1024
        
        # Open image
        img = Image.open(io.BytesIO(image_bytes))
        
        # Resize if too large
        if img.size[0] > max_dimension or img.size[1] > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Convert RGBA to RGB for compression
        if img.mode == 'RGBA':
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3])
            img = rgb_img
        
        # Compress
        compressed_bytes = io.BytesIO()
        img.save(compressed_bytes, format='JPEG', quality=quality, optimize=True)
        compressed_bytes.seek(0)
        compressed_data = compressed_bytes.getvalue()
        
        # Re-encode as base64
        compressed_b64 = b64_module.b64encode(compressed_data).decode('utf-8')
        compressed_size_kb = len(compressed_data) / 1024
        
        reduction = 100 * (1 - compressed_size_kb / original_size_kb)
        logger.debug(f"[COMPRESS] Image: {original_size_kb:.1f}KB → {compressed_size_kb:.1f}KB ({reduction:.0f}% reduction)")
        
        return compressed_b64
    except Exception as e:
        logger.warning(f"[COMPRESS] Failed to compress image: {e} - using original")
        return image_b64


def separate_content_types(chunk: Any) -> Dict[str, Any]:
    """
    Analyze what types of content are in a chunk.
    
    Returns dict with:
    - text: Main text content
    - tables: List of table HTML
    - images: List of (base64, mime_type) tuples
    - types: List of content types found
    
    Args:
        chunk: Unstructured chunk object
    
    Returns:
        Dict with separated content
    """
    content_data = {
        'text': chunk.text,
        'tables': [],
        'images': [],  # Now stores tuples of (base64, mime_type)
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
                        
                        # Compress image to reduce token usage with Gemini
                        compressed_b64 = _compress_base64_image(image_b64)
                        
                        # Detect MIME type from base64 magic bytes
                        mime_type = _detect_image_mime_type(compressed_b64)
                        content_data['images'].append((compressed_b64, mime_type))
                        logger.debug(f"[CONTENT] Found image in chunk ({mime_type})")
    
    except Exception as e:
        logger.warning(f"[CONTENT-ERROR] Error analyzing chunk content: {e}")
    
    content_data['types'] = list(content_data['types'])
    return content_data


def create_ai_enhanced_summary(
    text: str,
    tables: List[str],
    images: List[Tuple[str, str]],
) -> str:
    """
    Create AI-enhanced summary for chunks with images/tables using Gemini Vision.
    
    COST OPTIMIZATION: Only called for chunks with tables/images.
    Plain text chunks skip this entirely.
    
    Args:
        text: Text content
        tables: List of table HTML
        images: List of (base64_image, mime_type) tuples
    
    Returns:
        Enhanced summary optimized for search and retrieval
    """
    # Check if AI summaries are disabled (set DISABLE_GEMINI_SUMMARIES=true to save costs)
    if os.getenv("DISABLE_GEMINI_SUMMARIES", "false").lower() == "true":
        logger.info("[SUMMARY] ⚠️ AI summaries disabled (DISABLE_GEMINI_SUMMARIES=true) - using original text")
        summary = text
        if tables:
            summary += f"\n\n[Contains {len(tables)} table(s)]"
        if images:
            summary += f"\n[Contains {len(images)} image(s)]"
        return summary
    
    try:
        model = _get_gemini_model()
        if not model:
            logger.debug("[SUMMARY] No Gemini model - skipping AI summary")
            raise RuntimeError("Gemini unavailable")

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

        # Build parts for Gemini (text + optional images)
        parts: List[Union[str, Dict[str, Any]]] = [prompt_text]
        for img_b64, mime_type in images:
            try:
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": img_b64,
                    }
                })
            except Exception:
                continue

        response = model.generate_content(
            parts,
            generation_config={"max_output_tokens": 800},
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        )
        summary = response.text
        logger.info(f"[SUMMARY] AI summary created with Gemini: {len(summary)} chars")
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
        
        # Check if Gemini summaries are disabled
        if os.getenv("DISABLE_GEMINI_SUMMARIES", "false").lower() == "true":
            logger.info("[LANGCHAIN] ⚠️ Gemini summaries disabled - using generic image description")
            enhanced_content = f"[Image file: {source_file}]\nThis is an image document. Enable DISABLE_GEMINI_SUMMARIES=false to generate AI descriptions."
        else:
            try:
                logger.info("[LANGCHAIN] Summarizing image with Gemini...")
                model = _get_gemini_model()
                if not model:
                    raise RuntimeError("Gemini model not available")

                response = model.generate_content(
                    [
                        "Provide a comprehensive, detailed description of this image that would be useful for search and retrieval. Include: main subjects, visible text, layout, colors, any diagrams or charts, and key details.",
                        {
                            "inline_data": {
                                "mime_type": f"image/{image_format}",
                                "data": base64_image,
                            }
                        },
                    ],
                    generation_config={"max_output_tokens": 1000},
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    ],
                )

                enhanced_content = response.text
                logger.info(f"[LANGCHAIN] Gemini generated {len(enhanced_content)} char summary for image")
            except Exception as e:
                logger.warning(f"[LANGCHAIN] Failed to get Gemini summary: {e}")
                enhanced_content = f"[Image: {source_file}] (AI summary unavailable)"
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
    
    COST OPTIMIZATION:
    - Plain text chunks: NO API calls (free)
    - Chunks with tables/images: Gemini summary (can be disabled)
    - Standalone images: Gemini analysis (can be disabled)
    
    Set DISABLE_GEMINI_SUMMARIES=true to save costs (skip AI summaries)
    
    Args:
        filename: Original filename
        file_bytes: File contents
    
    Returns:
        Tuple of (documents, metadata)
    """
    logger.info(f"[PIPELINE] Starting multimodal processing for {filename}")
    
    # Log cost configuration
    disable_gemini = os.getenv("DISABLE_GEMINI_SUMMARIES", "false").lower() == "true"
    if disable_gemini:
        logger.warning(f"[PIPELINE] 💰 Cost optimization: Gemini AI summaries DISABLED (DISABLE_GEMINI_SUMMARIES=true)")
        logger.warning(f"[PIPELINE]    Text content: Used as-is (no API calls)")
        logger.warning(f"[PIPELINE]    Tables/Images: Not analyzed by AI")
    else:
        logger.info(f"[PIPELINE] ✓ Gemini AI summaries enabled for chunks with tables/images")
    
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
