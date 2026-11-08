from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.gemini_gateway import GeminiGateway, GeminiProviderError

if TYPE_CHECKING:
    from app.core.config import Settings


@dataclass(frozen=True)
class DocumentEmbeddingInput:
    title: str
    text: str


class GeminiEmbeddingService:
    def __init__(self, gateway: GeminiGateway | None = None, settings: Settings | None = None) -> None:
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        self.settings = settings
        self.gateway = gateway or GeminiGateway(settings=self.settings)

    def embed_documents(self, chunks: list[DocumentEmbeddingInput]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        batch_size = max(1, self.settings.gemini_embedding_batch_size)
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            contents = [self._document_input(item) for item in batch]
            response = self.gateway.embed_content(contents, self.settings.gemini_embedding_dimension)
            embeddings.extend(self._read_embeddings(response, len(batch)))
        return embeddings

    def embed_query(self, question: str) -> list[float]:
        response = self.gateway.embed_content(
            [f"task: question answering | query: {question.strip()}"],
            self.settings.gemini_embedding_dimension,
        )
        return self._read_embeddings(response, 1)[0]

    @staticmethod
    def _document_input(item: DocumentEmbeddingInput) -> str:
        title = item.title.strip() or "none"
        return f"title: {title} | text: {item.text.strip()}"

    def _read_embeddings(self, response: object, expected_count: int) -> list[list[float]]:
        raw_embeddings = getattr(response, "embeddings", None)
        if not raw_embeddings or len(raw_embeddings) != expected_count:
            raise GeminiProviderError("Gemini returned an unexpected number of embeddings.")
        values: list[list[float]] = []
        for item in raw_embeddings:
            vector = list(getattr(item, "values", []) or [])
            if len(vector) != self.settings.gemini_embedding_dimension:
                raise GeminiProviderError("Gemini returned an unexpected embedding dimension.")
            values.append(vector)
        return values

