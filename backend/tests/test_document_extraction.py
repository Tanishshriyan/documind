from __future__ import annotations

import io

import pytest

from app.services.extraction import (
    CorruptedDocumentError,
    EmptyDocumentError,
    ExtractedSection,
    chunk_sections,
    extract_document,
    validate_file_content,
)


def test_txt_extraction_has_explicit_logical_page_policy():
    result = extract_document(b"A private research note.", ".txt")

    assert result.sections[0].text == "A private research note."
    assert result.sections[0].page_number is None
    assert result.page_number_policy == "logical_document"
    assert result.page_count == 0


def test_docx_extraction_reads_paragraphs_and_tables():
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Project decision")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Owner"
    table.cell(0, 1).text = "Research"
    buffer = io.BytesIO()
    document.save(buffer)

    result = extract_document(buffer.getvalue(), ".docx")

    assert "Project decision" in result.sections[0].text
    assert "Owner | Research" in result.sections[0].text
    assert result.page_number_policy == "logical_document"


def test_pdf_extraction_preserves_one_based_page_numbers():
    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "first page evidence")
    page = document.new_page()
    page.insert_text((72, 72), "second page evidence")
    data = document.tobytes()
    document.close()

    result = extract_document(data, ".pdf")

    assert result.page_count == 2
    assert [section.page_number for section in result.sections] == [1, 2]
    assert result.page_number_policy == "physical"


def test_invalid_and_empty_documents_are_rejected():
    with pytest.raises(CorruptedDocumentError):
        validate_file_content(b"not a pdf", ".pdf")
    with pytest.raises(EmptyDocumentError):
        extract_document(b"", ".txt")
    with pytest.raises(CorruptedDocumentError):
        validate_file_content(b"%PDF-1.7", ".txt")


def test_chunking_keeps_page_metadata_and_overlap():
    text = " ".join(f"word{index}" for index in range(80))
    chunks = chunk_sections([ExtractedSection(text, page_number=7)], chunk_size=80, overlap=20)

    assert len(chunks) > 1
    assert all(chunk.page_number == 7 for chunk in chunks)
    assert any(set(first.text.split()) & set(second.text.split()) for first, second in zip(chunks, chunks[1:]))
