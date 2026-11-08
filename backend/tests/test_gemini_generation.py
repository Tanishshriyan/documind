from types import SimpleNamespace

from app.services.gemini_generation import GeminiAnswerService


class FakeGateway:
    def __init__(self):
        self.prompt = ""
        self.system_instruction = ""

    def generate_answer(self, prompt: str, system_instruction: str):
        self.prompt = prompt
        self.system_instruction = system_instruction
        return SimpleNamespace(output_text="The answer is grounded in the excerpt.")


def test_generation_receives_grounding_context_and_recent_history():
    document = SimpleNamespace(name="brief.txt")
    chunk = SimpleNamespace(id=19, document_id="doc-1", page_number=2, content="The launch date is 10 October.", document=document)
    gateway = FakeGateway()
    service = GeminiAnswerService(gateway=gateway, settings=SimpleNamespace(gemini_model="gemini-3.8-flash"))

    answer = service.generate(
        "When is the launch?",
        [SimpleNamespace(chunk=chunk, score=0.88)],
        [SimpleNamespace(role="user", content="Tell me about the launch.")],
    )

    assert answer.content == "The answer is grounded in the excerpt."
    assert "brief.txt" in gateway.prompt
    assert "[S1]" in gateway.prompt
    assert "Chunk ID: 19" in gateway.prompt
    assert "Page: 2" in gateway.prompt
    assert "Tell me about the launch." in gateway.prompt
    assert "only the supplied document excerpts" in gateway.system_instruction


def test_generation_removes_unknown_source_references():
    document = SimpleNamespace(name="brief.txt")
    chunk = SimpleNamespace(id=19, document_id="doc-1", page_number=2, content="The launch date is 10 October.", document=document)

    class UnknownReferenceGateway:
        def generate_answer(self, prompt: str, system_instruction: str):
            return SimpleNamespace(output_text="The date is supported by [S1] and [S99].")

    service = GeminiAnswerService(gateway=UnknownReferenceGateway(), settings=SimpleNamespace(gemini_model="gemini-3.8-flash"))
    answer = service.generate("When is the launch?", [SimpleNamespace(chunk=chunk, score=0.88)])

    assert answer.content == "The date is supported by [S1] and the supplied evidence."
    assert "[S99]" not in answer.content

