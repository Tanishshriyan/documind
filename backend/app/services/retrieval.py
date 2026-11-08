from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import Document, DocumentChunk, Message
from app.schemas import Citation
from app.services.gemini_embeddings import GeminiEmbeddingService
from app.services.gemini_generation import GeneratedAnswer, GeminiAnswerService


@dataclass
class RankedChunk:
    chunk: DocumentChunk
    score: float


NO_ANSWER = "I couldn't find enough relevant information in the selected documents to answer that reliably."


def retrieve(
    db: Session,
    owner_id: str,
    question: str,
    document_ids: list[str] | None = None,
    limit: int = 5,
    embedding_service: GeminiEmbeddingService | None = None,
) -> list[RankedChunk]:
    if document_ids == []:
        return []
    service = embedding_service or GeminiEmbeddingService()
    settings = get_settings()
    query_embedding = service.embed_query(question)
    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    query = (
        select(DocumentChunk, distance)
        .join(DocumentChunk.document)
        .options(joinedload(DocumentChunk.document))
        .where(
            Document.owner_id == owner_id,
            Document.status == "READY",
            DocumentChunk.embedding.is_not(None),
            DocumentChunk.embedding_model == settings.gemini_embedding_model,
            DocumentChunk.embedding_dimension == settings.gemini_embedding_dimension,
        )
        .order_by(distance, DocumentChunk.id.asc())
        .limit(limit)
    )
    if document_ids:
        query = query.where(DocumentChunk.document_id.in_(document_ids))

    ranked: list[RankedChunk] = []
    for chunk, raw_distance in db.execute(query).all():
        similarity = max(0.0, min(1.0, 1.0 - float(raw_distance)))
        if similarity >= settings.retrieval_min_similarity:
            ranked.append(RankedChunk(chunk=chunk, score=similarity))
    return ranked


def answer_question(
    db: Session,
    owner_id: str,
    question: str,
    document_ids: list[str] | None = None,
    recent_messages: list[Message] | None = None,
    embedding_service: GeminiEmbeddingService | None = None,
    answer_service: GeminiAnswerService | None = None,
) -> tuple[str, list[Citation]]:
    matches = retrieve(db, owner_id, question, document_ids, embedding_service=embedding_service)
    if db is not None:
        # Retrieval is read-only. Close its database transaction before the
        # potentially lengthy generation request; the chat route opens a new
        # transaction only after an answer has been produced.
        db.commit() if matches else db.rollback()
    if not matches:
        return NO_ANSWER, []

    citations = [
        Citation(
            chunk_id=match.chunk.id,
            source_label=f"[S{index}]",
            document_id=match.chunk.document_id,
            document_name=match.chunk.document.name,
            page_number=match.chunk.page_number,
            excerpt=match.chunk.content[:360].strip(),
            relevance=round(match.score, 2),
        )
        for index, match in enumerate(matches, start=1)
    ]
    generator = answer_service or GeminiAnswerService()
    answer: GeneratedAnswer = generator.generate(question, matches, recent_messages)
    return answer.content, citations

