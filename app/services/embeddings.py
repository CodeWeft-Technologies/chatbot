from sentence_transformers import SentenceTransformer
from app.core.config import settings

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float]:
    model = get_model()
    vec = model.encode([text], normalize_embeddings=True)[0]
    return vec.tolist()


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i : i + chunk_size]
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks
