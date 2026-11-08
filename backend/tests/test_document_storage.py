from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.services.storage import LocalDocumentStorage


def test_local_storage_round_trip_and_safe_key(tmp_path: Path):
    settings = Settings(document_storage_path=str(tmp_path / "documents"), storage_dir=str(tmp_path))
    storage = LocalDocumentStorage(settings)
    source = tmp_path / "source.txt"
    source.write_text("private content", encoding="utf-8")

    storage.put_file(source, "documents/object.txt", "text/plain")

    assert storage.read_bytes("documents/object.txt") == b"private content"
    storage.delete("documents/object.txt")
    assert not (tmp_path / "documents" / "documents" / "object.txt").exists()


def test_local_storage_rejects_path_traversal(tmp_path: Path):
    settings = Settings(document_storage_path=str(tmp_path / "documents"), storage_dir=str(tmp_path))
    storage = LocalDocumentStorage(settings)

    try:
        storage.read_bytes("../outside.txt")
    except RuntimeError as exc:
        assert "Invalid document storage key" in str(exc)
    else:
        raise AssertionError("path traversal key was accepted")
