from __future__ import annotations

from pathlib import Path

from app.models import Document, User


def csrf_headers(client):
    client.get("/api/v1/auth/csrf")
    return {"X-CSRF-Token": client.cookies.get("documind_csrf")}


def register(client, email="owner@example.com"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple", "display_name": "Owner"},
        headers=csrf_headers(client),
    )


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_file(self, source: Path, key: str, content_type: str) -> None:
        del content_type
        self.objects[key] = source.read_bytes()

    def read_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def delete_legacy_path(self, path: str) -> None:
        del path


def test_valid_txt_upload_is_owned_and_deduplicated(auth_harness, monkeypatch):
    make_client, _ = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    storage = FakeStorage()
    monkeypatch.setattr("app.api.routes.documents.get_document_storage", lambda *_: storage)
    monkeypatch.setattr("app.api.routes.documents.process_document", lambda *_: None)

    first = client.post(
        "/api/v1/documents/upload",
        files={"file": ("research.txt", b"private research", "application/octet-stream")},
        headers=csrf_headers(client),
    )
    second = client.post(
        "/api/v1/documents/upload",
        files={"file": ("renamed.txt", b"private research", "text/plain")},
        headers=csrf_headers(client),
    )

    assert first.status_code == 201
    assert first.json()["status"] == "PENDING"
    assert second.status_code == 200
    assert second.headers["X-Documind-Duplicate"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert len(storage.objects) == 1


def test_upload_rejects_content_that_does_not_match_extension(auth_harness):
    client = auth_harness[0]()
    assert register(client).status_code == 201

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("fake.pdf", b"plain text", "application/pdf")},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422


def test_delete_document_returns_no_content(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    storage = FakeStorage()
    storage.objects["document.txt"] = b"private research"
    monkeypatch.setattr("app.api.routes.documents.get_document_storage", lambda *_: storage)

    with session_factory() as db:
        user = db.query(User).filter_by(email="owner@example.com").one()
        document = Document(
            name="research.txt",
            original_name="research.txt",
            content_type="text/plain",
            size_bytes=len(storage.objects["document.txt"]),
            storage_key="document.txt",
            owner_id=user.id,
        )
        db.add(document)
        db.commit()
        document_id = document.id

    response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=csrf_headers(client),
    )

    assert response.status_code == 204
    assert response.content == b""
    assert storage.objects == {}
    with session_factory() as db:
        assert db.get(Document, document_id) is None
