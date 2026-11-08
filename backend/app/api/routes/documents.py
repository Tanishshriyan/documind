from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from pathlib import Path, PurePosixPath
import tempfile
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db
from app.core.config import get_settings
from app.models import Conversation, Document, DocumentChunk, Message
from app.schemas import DocumentChunkResponse, DocumentResponse
from app.services.document_processing import process_document
from app.services.extraction import CorruptedDocumentError, DocumentLimitError, UnsupportedDocumentError, validate_file_content
from app.services.storage import StorageError, get_document_storage

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


def _safe_filename(filename: str | None) -> str:
    candidate = PurePosixPath((filename or "document").replace("\\", "/")).name
    candidate = re.sub(r"[\x00-\x1f\x7f]", "", candidate).strip(" .")
    return candidate[:255] or "document"


def serialize_document(document: Document) -> DocumentResponse:
    return DocumentResponse.model_validate({
        "id": document.id,
        "name": document.name,
        "original_name": document.original_name,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "page_count": document.page_count,
        "char_count": document.char_count,
        "status": document.status,
        "error_message": document.error_message,
        "failure_reason": document.failure_reason,
        "uploaded_at": document.uploaded_at,
        "processing_started_at": document.processing_started_at,
        "processing_completed_at": document.processing_completed_at,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "chunk_count": document.chunk_count,
    })


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    current_user: CurrentUser,
    response: Response,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[DocumentResponse]:
    owner_filter = Document.owner_id == current_user.id
    total = db.scalar(select(func.count()).select_from(Document).where(owner_filter)) or 0
    documents = db.scalars(
        select(Document)
        .where(owner_filter)
        .order_by(Document.uploaded_at.desc(), Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    return [serialize_document(document) for document in documents]


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    settings = get_settings()
    original_name = _safe_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only PDF, DOCX, and TXT files are supported.")

    max_bytes = settings.effective_max_upload_size_mb * 1024 * 1024
    temporary_path: Path | None = None
    checksum = hashlib.sha256()
    size_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(prefix="documind-upload-", suffix=extension, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            while True:
                block = file.file.read(1024 * 1024)
                if not block:
                    break
                size_bytes += len(block)
                if size_bytes > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Files must be smaller than {settings.effective_max_upload_size_mb} MB.",
                    )
                checksum.update(block)
                temporary.write(block)

        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        content = temporary_path.read_bytes()
        try:
            validate_file_content(
                content,
                extension,
                max_uncompressed_bytes=settings.document_max_extracted_chars * 8,
            )
        except UnsupportedDocumentError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        except CorruptedDocumentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DocumentLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc

        checksum_hex = checksum.hexdigest()
        duplicate = db.scalar(
            select(Document).where(
                Document.owner_id == current_user.id,
                Document.checksum_sha256 == checksum_hex,
            )
        )
        if duplicate is not None:
            response.status_code = status.HTTP_200_OK
            response.headers["X-Documind-Duplicate"] = "true"
            return serialize_document(duplicate)

        storage_key = f"{uuid4().hex}{extension}"
        try:
            storage = get_document_storage(settings)
            storage.put_file(temporary_path, storage_key, CONTENT_TYPES[extension])
        except StorageError as exc:
            raise HTTPException(status_code=503, detail="Document storage is temporarily unavailable.") from exc

        document = Document(
            name=original_name,
            original_name=original_name,
            content_type=CONTENT_TYPES[extension],
            size_bytes=size_bytes,
            status="PENDING",
            storage_key=storage_key,
            checksum_sha256=checksum_hex,
            uploaded_at=datetime.now(timezone.utc),
            owner_id=current_user.id,
            page_number_policy="physical" if extension == ".pdf" else "logical_document",
        )
        db.add(document)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            try:
                get_document_storage(settings).delete(storage_key)
            except StorageError:
                pass
            duplicate = db.scalar(
                select(Document).where(
                    Document.owner_id == current_user.id,
                    Document.checksum_sha256 == checksum_hex,
                )
            )
            if duplicate is None:
                raise HTTPException(status_code=409, detail="This document could not be created safely.")
            response.status_code = status.HTTP_200_OK
            response.headers["X-Documind-Duplicate"] = "true"
            return serialize_document(duplicate)

        db.refresh(document)
        background_tasks.add_task(process_document, document.id)
        return serialize_document(document)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, current_user: CurrentUser, db: Session = Depends(get_db)) -> DocumentResponse:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == current_user.id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return serialize_document(document)


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkResponse])
def list_document_chunks(document_id: str, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[DocumentChunkResponse]:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == current_user.id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.status != "READY":
        raise HTTPException(status_code=409, detail="Document processing is not complete.")
    chunks = db.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index)
    ).all()
    return [DocumentChunkResponse(
        id=chunk.id,
        document_id=chunk.document_id,
        document_name=document.name,
        chunk_index=chunk.chunk_index,
        page_number=chunk.page_number,
        content=chunk.content,
    ) for chunk in chunks]


@router.delete(
    "/{document_id}",
    response_model=None,
    response_class=Response,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(document_id: str, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == current_user.id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        storage = get_document_storage()
        if document.storage_key:
            storage.delete(document.storage_key)
        elif document.storage_path:
            storage.delete_legacy_path(document.storage_path)
    except StorageError as exc:
        logger.warning("Storage deletion failed for document %s", document.id)
        raise HTTPException(status_code=503, detail="The document could not be removed from storage.") from exc

    try:
        conversations = db.scalars(
            select(Conversation).where(Conversation.owner_id == current_user.id)
        ).unique().all()
        for conversation in conversations:
            for message in conversation.messages:
                try:
                    citations = json.loads(message.citations_json or "[]")
                except json.JSONDecodeError:
                    continue
                if not isinstance(citations, list):
                    continue
                filtered = [
                    citation for citation in citations
                    if not isinstance(citation, dict) or citation.get("document_id") != document.id
                ]
                if filtered != citations:
                    message.citations_json = json.dumps(filtered)
        db.delete(document)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Database deletion failed for document %s", document.id)
        raise HTTPException(status_code=500, detail="The document could not be removed safely.") from exc
