from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Citation(BaseModel):
    # Optional for compatibility with citation JSON written before chunk-level
    # citation metadata was introduced.
    chunk_id: int | None = None
    source_label: str | None = None
    document_id: str
    document_name: str
    page_number: int | None = None
    excerpt: str
    relevance: float = Field(ge=0, le=1)


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Display name cannot be empty.")
        return normalized


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    is_active: bool
    created_at: datetime


class CsrfResponse(BaseModel):
    status: str = "ok"


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    original_name: str
    content_type: str
    size_bytes: int
    page_count: int
    char_count: int
    status: str
    error_message: str | None
    failure_reason: str | None = None
    uploaded_at: datetime | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    chunk_count: int = 0


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: str
    document_name: str
    chunk_index: int
    page_number: int | None
    content: str


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Conversation title cannot be empty.")
        return normalized


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Conversation title cannot be empty.")
        return normalized


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    citations: list[Citation] = Field(default_factory=list)
    # NULL means all sources, [] means no sources, and a non-empty list is an
    # explicit document scope for this user message.
    document_ids: list[str] | None = None
    created_at: datetime


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    document_ids: list[str] | None = None

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message content cannot be empty.")
        return normalized


class InitialConversationRequest(ChatRequest):
    title: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Conversation title cannot be empty.")
        return normalized


class ChatResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


class ConversationWithMessagesResponse(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]

