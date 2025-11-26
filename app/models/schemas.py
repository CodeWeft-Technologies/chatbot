from pydantic import BaseModel


class ChatRequest(BaseModel):
    org_id: str
    query: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    similarity: float
