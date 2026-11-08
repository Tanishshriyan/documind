from types import SimpleNamespace

from app.services.gemini_embeddings import DocumentEmbeddingInput, GeminiEmbeddingService


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_content(self, contents: list[str], output_dimension: int):
        self.calls.append(contents)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[float(index)] * output_dimension) for index, _ in enumerate(contents, start=1)]
        )


def test_document_embeddings_are_batched_and_768_dimensional():
    gateway = FakeGateway()
    settings = SimpleNamespace(gemini_embedding_batch_size=2, gemini_embedding_dimension=768)
    service = GeminiEmbeddingService(gateway=gateway, settings=settings)

    values = service.embed_documents([
        DocumentEmbeddingInput("one.txt", "first"),
        DocumentEmbeddingInput("two.txt", "second"),
        DocumentEmbeddingInput("three.txt", "third"),
    ])

    assert len(gateway.calls) == 2
    assert len(values) == 3
    assert all(len(vector) == 768 for vector in values)
    assert gateway.calls[0][0] == "title: one.txt | text: first"


def test_question_embedding_uses_retrieval_instruction():
    gateway = FakeGateway()
    settings = SimpleNamespace(gemini_embedding_batch_size=2, gemini_embedding_dimension=768)
    service = GeminiEmbeddingService(gateway=gateway, settings=settings)

    vector = service.embed_query("What is the refund policy?")

    assert len(vector) == 768
    assert gateway.calls == [["task: question answering | query: What is the refund policy?"]]

