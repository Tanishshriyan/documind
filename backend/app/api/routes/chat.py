from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db
from app.models import Conversation, Document, Message
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    ConversationWithMessagesResponse,
    InitialConversationRequest,
    MessageResponse,
)
from app.services.gemini_gateway import GeminiError
from app.services.retrieval import answer_question

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MESSAGE_HISTORY_LIMIT = 6


def serialize_conversation(conversation: Conversation, message_count: int | None = None) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages) if message_count is None else message_count,
    )


def _stored_document_scope(message: Message) -> list[str] | None:
    if message.selected_document_ids_json is None:
        return None
    try:
        scope = json.loads(message.selected_document_ids_json)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Ignoring malformed document scope for message %s", message.id)
        return None
    if not isinstance(scope, list) or not all(isinstance(item, str) for item in scope):
        logger.warning("Ignoring invalid document scope for message %s", message.id)
        return None
    return scope


def serialize_message(message: Message) -> MessageResponse:
    try:
        raw_citations = json.loads(message.citations_json or "[]")
    except (TypeError, json.JSONDecodeError):
        raw_citations = []
    if not isinstance(raw_citations, list):
        raw_citations = []
    citations = []
    for item in raw_citations:
        try:
            citations.append(Citation.model_validate(item))
        except ValueError:
            logger.warning("Ignoring malformed citations for message %s", message.id)
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=citations,
        document_ids=_stored_document_scope(message),
        created_at=message.created_at,
    )


def _get_owned_conversation(db: Session, conversation_id: str, owner_id: str) -> Conversation:
    try:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.owner_id == owner_id,
            )
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database read failed while loading a conversation")
        raise HTTPException(status_code=500, detail="The conversation could not be loaded safely.") from exc
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


def _validate_document_selection(db: Session, owner_id: str, document_ids: list[str] | None) -> None:
    if not document_ids:
        return
    owned_ids = set(
        db.scalars(
            select(Document.id).where(
                Document.owner_id == owner_id,
                Document.id.in_(document_ids),
            )
        ).all()
    )
    if owned_ids != set(document_ids):
        # Do not distinguish a missing document from another user's document.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected document not found.")


def _recent_messages(db: Session, conversation_id: str) -> list[Message]:
    try:
        messages = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(MESSAGE_HISTORY_LIMIT)
        ).all()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database read failed while loading conversation history")
        raise HTTPException(status_code=500, detail="The conversation history could not be loaded safely.") from exc
    messages.reverse()
    # Rollback below expires ORM instances. Copy the history into transient
    # model values so prompt rendering does not reopen a read transaction.
    return [
        Message(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            citations_json=message.citations_json,
            created_at=message.created_at,
        )
        for message in messages
    ]


def _generate_answer(
    db: Session,
    owner_id: str,
    payload: ChatRequest,
    recent_messages: list[Message] | None = None,
) -> tuple[str, list[Citation]]:
    try:
        _validate_document_selection(db, owner_id, payload.document_ids)
        # The validation/history reads are complete. End their read-only transaction
        # before invoking retrieval and Gemini; persistence starts only after
        # generation succeeds.
        db.rollback()
        return answer_question(
            db,
            owner_id,
            payload.content,
            payload.document_ids,
            recent_messages,
        )
    except HTTPException:
        raise
    except GeminiError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database read failed while answering a conversation message")
        raise HTTPException(status_code=500, detail="The message could not be processed safely.") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected assistant failure while answering a conversation message")
        raise HTTPException(status_code=502, detail="The assistant could not answer right now.") from exc


def _persist_exchange(
    db: Session,
    owner_id: str,
    content: str,
    answer: str,
    citations: list[Citation],
    document_ids: list[str] | None,
    conversation_id: str | None = None,
    initial_title: str | None = None,
) -> tuple[Conversation, Message, Message]:
    if conversation_id is None:
        conversation = Conversation(
            title=initial_title or content[:80],
            owner_id=owner_id,
        )
        db.add(conversation)
    else:
        conversation = _get_owned_conversation(db, conversation_id, owner_id)
        if conversation.title == "New conversation":
            conversation.title = content[:80]

    # Message inserts do not trigger SQLAlchemy's onupdate hook on Conversation.
    conversation.updated_at = datetime.now(timezone.utc)
    user_message = Message(
        conversation=conversation,
        role="user",
        content=content,
        citations_json="[]",
        selected_document_ids_json=json.dumps(document_ids) if document_ids is not None else None,
    )
    assistant_message = Message(
        conversation=conversation,
        role="assistant",
        content=answer,
        citations_json=json.dumps([citation.model_dump() for citation in citations]),
    )
    db.add_all([user_message, assistant_message])
    try:
        db.commit()
        db.refresh(conversation)
        db.refresh(user_message)
        db.refresh(assistant_message)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database transaction failed while persisting a conversation exchange")
        raise HTTPException(status_code=500, detail="The conversation could not be saved safely.") from exc
    return conversation, user_message, assistant_message


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    current_user: CurrentUser,
    response: Response,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> list[ConversationResponse]:
    owner_filter = Conversation.owner_id == current_user.id
    total = db.scalar(select(func.count()).select_from(Conversation).where(owner_filter)) or 0
    message_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Conversation, message_count.label("message_count"))
        .where(owner_filter)
        .order_by(
            Conversation.updated_at.desc(),
            Conversation.created_at.desc(),
            Conversation.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    return [serialize_conversation(conversation, int(count)) for conversation, count in rows]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    conversation = Conversation(title=payload.title, owner_id=current_user.id)
    db.add(conversation)
    try:
        db.commit()
        db.refresh(conversation)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database transaction failed while creating a conversation")
        raise HTTPException(status_code=500, detail="The conversation could not be created safely.") from exc
    return serialize_conversation(conversation, 0)


@router.post("/with-message", response_model=ConversationWithMessagesResponse, status_code=status.HTTP_201_CREATED)
def create_conversation_with_message(
    payload: InitialConversationRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationWithMessagesResponse:
    answer, citations = _generate_answer(db, current_user.id, payload, recent_messages=[])
    conversation, user_message, assistant_message = _persist_exchange(
        db,
        current_user.id,
        payload.content,
        answer,
        citations,
        payload.document_ids,
        initial_title=payload.title or payload.content[:80],
    )
    return ConversationWithMessagesResponse(
        conversation=serialize_conversation(conversation, 2),
        messages=[serialize_message(user_message), serialize_message(assistant_message)],
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str, current_user: CurrentUser, db: Session = Depends(get_db)) -> ConversationResponse:
    conversation = _get_owned_conversation(db, conversation_id, current_user.id)
    message_count = db.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    ) or 0
    return serialize_conversation(conversation, int(message_count))


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    conversation = _get_owned_conversation(db, conversation_id, current_user.id)
    conversation.title = payload.title
    conversation.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(conversation)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database transaction failed while renaming a conversation")
        raise HTTPException(status_code=500, detail="The conversation could not be renamed safely.") from exc
    message_count = db.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    ) or 0
    return serialize_conversation(conversation, int(message_count))


@router.delete(
    "/{conversation_id}",
    response_model=None,
    response_class=Response,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(conversation_id: str, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    _get_owned_conversation(db, conversation_id, current_user.id)
    try:
        # Explicitly delete children as well as the owned parent. This is safe on
        # PostgreSQL and does not depend on SQLite foreign-key pragma settings.
        db.execute(delete(Message).where(Message.conversation_id == conversation_id))
        db.execute(
            delete(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.owner_id == current_user.id,
            )
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database transaction failed while deleting a conversation")
        raise HTTPException(status_code=500, detail="The conversation could not be deleted safely.") from exc
    return None


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation_id: str,
    current_user: CurrentUser,
    response: Response,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
) -> list[MessageResponse]:
    _get_owned_conversation(db, conversation_id, current_user.id)
    total = db.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    ) or 0
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    return [serialize_message(message) for message in messages]


@router.post("/{conversation_id}/messages", response_model=ChatResponse)
def send_message(
    conversation_id: str,
    payload: ChatRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ChatResponse:
    _get_owned_conversation(db, conversation_id, current_user.id)
    recent_messages = _recent_messages(db, conversation_id)
    answer, citations = _generate_answer(db, current_user.id, payload, recent_messages)
    _, user_message, assistant_message = _persist_exchange(
        db,
        current_user.id,
        payload.content,
        answer,
        citations,
        payload.document_ids,
        conversation_id=conversation_id,
    )
    return ChatResponse(
        user_message=serialize_message(user_message),
        assistant_message=serialize_message(assistant_message),
    )
