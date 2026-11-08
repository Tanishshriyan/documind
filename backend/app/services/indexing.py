from app.models import Document
from app.services.gemini_embeddings import DocumentEmbeddingInput, GeminiEmbeddingService


def embed_document_chunks(document: Document, embedding_service: GeminiEmbeddingService | None = None) -> None:
    service = embedding_service or GeminiEmbeddingService()
    chunks = sorted(document.chunks, key=lambda chunk: chunk.chunk_index)
    inputs = [
        DocumentEmbeddingInput(title=document.name, text=chunk.content)
        for chunk in chunks
    ]
    vectors = service.embed_documents(inputs)
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector
        chunk.embedding_model = service.settings.gemini_embedding_model
        chunk.embedding_dimension = service.settings.gemini_embedding_dimension
    document.embedding_model = service.settings.gemini_embedding_model
    document.embedding_dimension = service.settings.gemini_embedding_dimension

