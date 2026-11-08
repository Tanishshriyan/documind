from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_backend_env = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    app_name: str = "DocuMind AI API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://documind:documind@localhost:5432/documind"
    storage_dir: str = "./storage"
    document_storage_backend: Literal["local", "s3"] = "local"
    document_storage_path: str = "storage/documents"
    document_max_upload_size_mb: int | None = None
    document_max_pages: int = 500
    document_max_extracted_chars: int = 5_000_000
    document_chunk_size: int = 1400
    document_chunk_overlap: int = 180
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_size_mb: int = 25
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimension: int = 768
    gemini_embedding_batch_size: int = 32
    gemini_max_retries: int = 3
    gemini_timeout_seconds: float = 45.0
    retrieval_min_similarity: float = 0.25
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "documind-api"
    access_token_expire_minutes: int = 60
    auth_cookie_name: str = "documind_access"
    csrf_cookie_name: str = "documind_csrf"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    model_config = SettingsConfigDict(
        env_file=(str(_backend_env), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("gemini_embedding_dimension")
    @classmethod
    def validate_embedding_dimension(cls, value: int) -> int:
        if value != 768:
            raise ValueError("DocuMind AI requires GEMINI_EMBEDDING_DIMENSION=768 for the pgvector schema.")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: str | None) -> str | None:
        if value is not None and value and len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters.")
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("Only HS256 is enabled for the MVP JWT configuration.")
        return value

    @field_validator("document_max_upload_size_mb", "document_max_pages", "document_max_extracted_chars")
    @classmethod
    def validate_positive_limits(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Document processing limits must be positive.")
        return value

    @field_validator("document_chunk_size")
    @classmethod
    def validate_chunk_size(cls, value: int) -> int:
        if value < 100:
            raise ValueError("DOCUMENT_CHUNK_SIZE must be at least 100 characters.")
        return value

    @field_validator("document_chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("DOCUMENT_CHUNK_OVERLAP cannot be negative.")
        return value

    @model_validator(mode="after")
    def validate_production_auth(self) -> "Settings":
        if self.environment.lower() == "production":
            if not self.jwt_secret_key:
                raise ValueError("JWT_SECRET_KEY is required in production.")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production.")
            if self.document_storage_backend != "s3":
                raise ValueError("DOCUMENT_STORAGE_BACKEND=s3 is required in production.")
        return self

    @property
    def effective_max_upload_size_mb(self) -> int:
        return self.document_max_upload_size_mb or self.max_upload_size_mb

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

