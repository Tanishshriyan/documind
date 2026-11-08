from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import io
import re
from typing import BinaryIO
import zipfile

from docx import Document as DocxDocument

try:  # The dependency is required in deployed environments, but keeps import errors explicit.
    import pymupdf
except ImportError:  # pragma: no cover - exercised only before dependencies are installed.
    pymupdf = None  # type: ignore[assignment]


class DocumentProcessingError(ValueError):
    """Safe, user-facing document processing failure."""


class UnsupportedDocumentError(DocumentProcessingError):
    pass


class CorruptedDocumentError(DocumentProcessingError):
    pass


class EmptyDocumentError(DocumentProcessingError):
    pass


class DocumentLimitError(DocumentProcessingError):
    pass


@dataclass
class ExtractedSection:
    text: str
    page_number: int | None = None


@dataclass
class ExtractionResult:
    sections: list[ExtractedSection]
    page_count: int
    page_number_policy: str
    text_length: int


def _read_source(source: Path | bytes | bytearray | BinaryIO) -> bytes:
    if isinstance(source, Path):
        return source.read_bytes()
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    return source.read()


def _decode_text(data: bytes) -> str:
    if b"\x00" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise CorruptedDocumentError("The text file contains binary data and could not be decoded safely.")
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" not in text:
            return text
    raise CorruptedDocumentError("The text file could not be decoded safely.")


def validate_file_content(data: bytes, extension: str, *, max_uncompressed_bytes: int = 100_000_000) -> None:
    """Validate the actual bytes, not the browser-provided MIME type."""
    extension = extension.lower()
    if extension == ".pdf":
        if not data[:1024].lstrip().startswith(b"%PDF-"):
            raise CorruptedDocumentError("The uploaded file is not a valid PDF.")
        return
    if extension == ".docx":
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise CorruptedDocumentError("The uploaded file is not a valid DOCX document.")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise CorruptedDocumentError("The uploaded file is not a valid DOCX document.")
                if sum(info.file_size for info in archive.infolist()) > max_uncompressed_bytes:
                    raise DocumentLimitError("The DOCX archive is larger than this workspace allows.")
        except (OSError, zipfile.BadZipFile) as exc:
            raise CorruptedDocumentError("The uploaded file is not a valid DOCX document.") from exc
        return
    if extension == ".txt":
        if data[:1024].lstrip().startswith(b"%PDF-") or zipfile.is_zipfile(io.BytesIO(data)):
            raise CorruptedDocumentError("The file content does not match the TXT extension.")
        _decode_text(data)
        return
    raise UnsupportedDocumentError("Only PDF, DOCX, and TXT files are supported.")


def _ensure_text_limit(text_length: int, max_extracted_chars: int) -> None:
    if text_length > max_extracted_chars:
        raise DocumentLimitError("The document contains more extracted text than this workspace allows.")


def extract_document(
    source: Path | bytes | bytearray | BinaryIO,
    extension: str,
    *,
    max_pages: int = 500,
    max_extracted_chars: int = 5_000_000,
) -> ExtractionResult:
    extension = extension.lower()
    if extension not in {".pdf", ".docx", ".txt"}:
        raise UnsupportedDocumentError("Only PDF, DOCX, and TXT files are supported.")
    data = _read_source(source)
    if not data:
        raise EmptyDocumentError("The uploaded document is empty.")
    validate_file_content(data, extension, max_uncompressed_bytes=max_extracted_chars * 8)

    if extension == ".pdf":
        if pymupdf is None:
            raise CorruptedDocumentError("PDF processing is not available on this server.")
        try:
            with pymupdf.open(stream=data, filetype="pdf") as document:
                page_count = document.page_count
                if page_count > max_pages:
                    raise DocumentLimitError(f"Documents are limited to {max_pages} pages.")
                sections: list[ExtractedSection] = []
                text_length = 0
                for page_index in range(page_count):
                    text = document[page_index].get_text("text").strip()
                    text_length += len(text)
                    _ensure_text_limit(text_length, max_extracted_chars)
                    sections.append(ExtractedSection(text=text, page_number=page_index + 1))
        except DocumentProcessingError:
            raise
        except Exception as exc:
            raise CorruptedDocumentError("The PDF could not be read safely.") from exc
        if not text_length:
            raise EmptyDocumentError("The document does not contain extractable text.")
        return ExtractionResult(sections, page_count, "physical", text_length)

    if extension == ".docx":
        try:
            document = DocxDocument(io.BytesIO(data))
            parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
            for table in document.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            text = "\n".join(parts).strip()
        except Exception as exc:
            raise CorruptedDocumentError("The DOCX document could not be read safely.") from exc
        _ensure_text_limit(len(text), max_extracted_chars)
        if not text:
            raise EmptyDocumentError("The document does not contain extractable text.")
        # DOCX has no reliable physical page information without a rendering engine.
        return ExtractionResult([ExtractedSection(text=text)], 0, "logical_document", len(text))

    text = _decode_text(data).strip()
    _ensure_text_limit(len(text), max_extracted_chars)
    if not text:
        raise EmptyDocumentError("The document does not contain text.")
    # TXT has no physical page structure; citations intentionally omit page numbers.
    return ExtractionResult([ExtractedSection(text=text)], 0, "logical_document", len(text))


def chunk_sections(
    sections: list[ExtractedSection],
    chunk_size: int = 1400,
    overlap: int = 180,
) -> list[ExtractedSection]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk size must be positive and overlap must be smaller than chunk size.")

    chunks: list[ExtractedSection] = []
    for section in sections:
        text = re.sub(r"\s+", " ", section.text).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + chunk_size // 2, end)
                if boundary > start:
                    end = boundary
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(ExtractedSection(text=chunk, page_number=section.page_number))
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    if not chunks:
        raise EmptyDocumentError("The document did not produce any searchable text.")
    return chunks
