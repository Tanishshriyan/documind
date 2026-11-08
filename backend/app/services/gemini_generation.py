from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from app.services.gemini_gateway import GeminiGateway, GeminiProviderError

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.models import Message
    from app.services.retrieval import RankedChunk


GROUNDING_INSTRUCTION = """
You are DocuMind, a document question-answering assistant.
Answer the user's question using only the supplied document excerpts and recent conversation context.
Do not use general knowledge to fill gaps. Do not invent facts, sources, page numbers, or quotations.
If the supplied excerpts do not contain enough information, clearly say that the answer could not be found in the uploaded documents.
Be concise and direct. Do not create or modify citation metadata; the application attaches citations from retrieved chunks.
The supplied evidence sources use exact labels such as [S1] and [S2]. If you refer to a source in the answer, use only a supplied label; never invent a source label or cite a source that was not supplied.
""".strip()
SOURCE_REFERENCE_PATTERN = re.compile(r"\[S\d+\]")


@dataclass(frozen=True)
class GeneratedAnswer:
    content: str


class GeminiAnswerService:
    def __init__(self, gateway: GeminiGateway | None = None, settings: Settings | None = None) -> None:
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        self.settings = settings
        self.gateway = gateway or GeminiGateway(settings=self.settings)

    def generate(
        self,
        question: str,
        matches: list[RankedChunk],
        recent_messages: list[Message] | None = None,
    ) -> GeneratedAnswer:
        prompt = self._build_prompt(question, matches, recent_messages or [])
        interaction = self.gateway.generate_answer(prompt, GROUNDING_INSTRUCTION)
        answer = self._sanitize_source_references(str(getattr(interaction, "output_text", "") or ""), len(matches))
        if not answer:
            raise GeminiProviderError()
        return GeneratedAnswer(content=answer)

    @staticmethod
    def _sanitize_source_references(answer: str, source_count: int) -> str:
        valid_labels = {f"[S{index}]" for index in range(1, source_count + 1)}

        def replace_reference(match: re.Match[str]) -> str:
            label = match.group(0)
            return label if label in valid_labels else "the supplied evidence"

        return SOURCE_REFERENCE_PATTERN.sub(replace_reference, answer).strip()

    @staticmethod
    def _build_prompt(question: str, matches: list[RankedChunk], recent_messages: list[Message]) -> str:
        conversation = "\n".join(
            f"{message.role.upper()}: {message.content[:1200]}"
            for message in recent_messages[-6:]
        ) or "(No prior conversation.)"
        sources = "\n\n".join(
            "{label}\nChunk ID: {chunk_id}\nDocument ID: {document_id}\nDocument: {name}\nPage: {page}\nExcerpt:\n{excerpt}".format(
                label=f"[S{index}]",
                chunk_id=getattr(match.chunk, "id", "unknown"),
                document_id=match.chunk.document_id,
                index=index,
                name=match.chunk.document.name,
                page=match.chunk.page_number or "not available",
                excerpt=match.chunk.content[:3000],
            )
            for index, match in enumerate(matches, start=1)
        )
        return (
            f"RECENT CONVERSATION:\n{conversation}\n\n"
            f"RETRIEVED DOCUMENT EVIDENCE:\n{sources}\n\n"
            f"USER QUESTION:\n{question.strip()}"
        )

