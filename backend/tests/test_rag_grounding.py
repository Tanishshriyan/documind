from types import SimpleNamespace

from app.models import Document, DocumentChunk
from app.services.retrieval import RankedChunk, answer_question


class FakeAnswerService:
    def generate(self, question, matches, recent_messages):
        assert question == "What is the refund policy?"
        assert matches[0].chunk.document.name == "policy.txt"
        return SimpleNamespace(content="The refund window is 30 days.")


def test_citations_keep_retrieved_chunk_metadata(monkeypatch):
    document = Document(id="doc-1", name="policy.txt", original_name="policy.txt", content_type="text/plain", size_bytes=10, storage_path="policy.txt", owner_id="alice")
    chunk = DocumentChunk(id=7, document_id="doc-1", chunk_index=0, page_number=4, content="Refunds are available within 30 days.", token_count=6, embedding=[0.1])
    chunk.document = document
    monkeypatch.setattr(
        "app.services.retrieval.retrieve",
        lambda *args, **kwargs: [RankedChunk(chunk=chunk, score=0.91)],
    )

    answer, citations = answer_question(None, "alice", "What is the refund policy?", answer_service=FakeAnswerService())

    assert answer == "The refund window is 30 days."
    assert citations[0].document_id == "doc-1"
    assert citations[0].chunk_id == 7
    assert citations[0].source_label == "[S1]"
    assert citations[0].document_name == "policy.txt"
    assert citations[0].page_number == 4
    assert citations[0].excerpt == "Refunds are available within 30 days."


def test_all_retrieved_chunks_have_exact_source_mapping(monkeypatch):
    first_document = Document(id="doc-1", name="policy.txt", original_name="policy.txt", content_type="text/plain", size_bytes=10, storage_path="policy.txt", owner_id="alice")
    second_document = Document(id="doc-2", name="faq.txt", original_name="faq.txt", content_type="text/plain", size_bytes=10, storage_path="faq.txt", owner_id="alice")
    first = DocumentChunk(id=11, document_id="doc-1", chunk_index=0, content="First source text.", token_count=3, embedding=[0.1])
    second = DocumentChunk(id=22, document_id="doc-2", chunk_index=2, content="Second source text.", token_count=3, embedding=[0.2])
    first.document = first_document
    second.document = second_document

    class CaptureAnswerService:
        def generate(self, question, matches, recent_messages):
            assert [match.chunk.id for match in matches] == [11, 22]
            return SimpleNamespace(content="Answer grounded in both sources.")

    monkeypatch.setattr(
        "app.services.retrieval.retrieve",
        lambda *args, **kwargs: [RankedChunk(chunk=first, score=0.91), RankedChunk(chunk=second, score=0.82)],
    )
    answer, citations = answer_question(None, "alice", "Compare the sources.", answer_service=CaptureAnswerService())

    assert answer == "Answer grounded in both sources."
    assert [(citation.source_label, citation.chunk_id, citation.document_id, citation.excerpt) for citation in citations] == [
        ("[S1]", 11, "doc-1", "First source text."),
        ("[S2]", 22, "doc-2", "Second source text."),
    ]


def test_no_answer_does_not_call_generation(monkeypatch):
    called = False

    class ShouldNotRun:
        def generate(self, *args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("generation must not run without evidence")

    monkeypatch.setattr("app.services.retrieval.retrieve", lambda *args, **kwargs: [])

    answer, citations = answer_question(None, "alice", "Unknown question", answer_service=ShouldNotRun())

    assert "couldn't find" in answer
    assert citations == []
    assert called is False

