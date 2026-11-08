from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import PurePath

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Document, DocumentChunk
from app.services.extraction import chunk_sections, extract_document
from app.services.gemini_gateway import GeminiError
from app.services.indexing import embed_document_chunks
from app.services.storage import StorageError, get_document_storage

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_failure_message(error: Exception) -> str:
    if isinstance(error, GeminiError):
        return error.public_message
    if isinstance(error, (StorageError, ValueError)) and str(error):
        return str(error)
    return "The file could not be indexed. Please check that it is a valid document."


def process_document(document_id: str) -> None:
    """Process one uploaded document in a fresh session for FastAPI BackgroundTasks."""
    db = SessionLocal()
    try:
        document = db.scalar(select(Document).where(Document.id == document_id))
        if document is None:
            return

        document.status = "PROCESSING"
        document.processing_started_at = _now()
        document.processing_completed_at = None
        document.failure_reason = None
        document.error_message = None
        db.commit()

        settings = get_settings()
        storage = get_document_storage(settings)
        key = document.storage_key
        if not key:
            raise StorageError("The stored document is unavailable.")
        content = storage.read_bytes(key)
        extension = PurePath(document.original_name).suffix.lower()
        extraction = extract_document(
            content,
            extension,
            max_pages=settings.document_max_pages,
            max_extracted_chars=settings.document_max_extracted_chars,
        )
        extracted_chunks = chunk_sections(
            extraction.sections,
            chunk_size=settings.document_chunk_size,
            overlap=settings.document_chunk_overlap,
        )

        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        document.chunks = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                page_number=chunk.page_number,
                content=chunk.text,
                token_count=len(chunk.text.split()),
            )
            for index, chunk in enumerate(extracted_chunks)
        ]
        document.page_count = extraction.page_count
        document.char_count = extraction.text_length
        document.page_number_policy = extraction.page_number_policy
        document.chunk_count = len(extracted_chunks)
        db.flush()

        # This is the existing Gemini 2 embedding service; no local fallback is permitted.
        embed_document_chunks(document)
        document.status = "READY"
        document.failure_reason = None
        document.error_message = None
        document.processing_completed_at = _now()
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Document processing failed for %s (%s)", document_id, type(exc).__name__)
        failed = db.scalar(select(Document).where(Document.id == document_id))
        if failed is not None:
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            message = _safe_failure_message(exc)
            failed.status = "FAILED"
            failed.failure_reason = message
            failed.error_message = message
            failed.chunk_count = 0
            failed.processing_completed_at = _now()
            db.commit()
    finally:
        db.close()
