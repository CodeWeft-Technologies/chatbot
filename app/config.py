from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import typing
from dotenv import load_dotenv, dotenv_values
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[2]
ENV_CANDIDATES = [
    ROOT / ".env",
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parent / ".env",
]
ENV_PATH = next((p for p in ENV_CANDIDATES if p.exists()), ENV_CANDIDATES[0])

class Settings(BaseSettings):
    SUPABASE_URL: str = Field(...)
    SUPABASE_ANON_KEY: str = Field(...)
    SUPABASE_SERVICE_ROLE_KEY: str = Field(...)
    SUPABASE_DB_DSN: str = Field(...)
    GROQ_API_KEY: str = Field(...)
    JWT_SECRET: str = Field("dev-secret")
    PASSWORD_PEPPER: str = Field(default="")

    EMBEDDING_MODEL_NAME: str = Field("BAAI/bge-large-en-v1.5")
    MAX_CONTEXT_CHUNKS: int = Field(6)
    MIN_SIMILARITY: float = Field(0.25)

    CORS_ALLOWED_ORIGINS: str = Field("http://localhost:3000,http://127.0.0.1:8001,http://localhost:8001")
    ENV: str = Field("development")

    PUBLIC_API_BASE_URL: str = Field(default="http://localhost:8000")
    WIDGET_THEME: str = Field(default="light")
    GOOGLE_CLIENT_ID: typing.Optional[str] = Field(default=None)
    GOOGLE_CLIENT_SECRET: typing.Optional[str] = Field(default=None)
    GOOGLE_SERVICE_ACCOUNT_JSON: typing.Optional[str] = Field(default=None)

    @property
    def cors_origins(self) -> List[str]:
        v = self.CORS_ALLOWED_ORIGINS
        vs = v.strip()
        if vs.startswith("["):
            import json
            try:
                arr = json.loads(vs)
                return [str(s).strip() for s in arr]
            except Exception:
                pass
        return [o.strip() for o in vs.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=str(ENV_PATH), env_file_encoding="utf-8", case_sensitive=False)


# Load .env and force-populate os.environ so pydantic sees values even in reloader subprocess
vals = dotenv_values(str(ENV_PATH))
for k, v in vals.items():
    if v is not None:
        os.environ.setdefault(k, v)
load_dotenv(str(ENV_PATH))
settings = Settings()
