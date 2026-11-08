from types import SimpleNamespace

from app.services.retrieval import retrieve


class FakeEmbeddingService:
    def embed_query(self, question: str) -> list[float]:
        return [0.0] * 768


class FakeResult:
    def all(self):
        return []


class FakeSession:
    def __init__(self):
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return FakeResult()


def test_retrieval_query_contains_owner_scope():
    session = FakeSession()
    retrieve(session, "alice", "private question", embedding_service=FakeEmbeddingService())

    compiled = str(session.statement)
    assert "documents.owner_id" in compiled


def test_empty_document_selection_does_not_search_all_sources():
    class ShouldNotEmbed:
        def embed_query(self, question: str) -> list[float]:
            raise AssertionError("an empty selection must not invoke retrieval")

    assert retrieve(FakeSession(), "alice", "private question", document_ids=[], embedding_service=ShouldNotEmbed()) == []

