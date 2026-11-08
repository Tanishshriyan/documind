from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Conversation, Document, DocumentChunk, Message, User


def csrf_headers(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies.get("documind_csrf")}


def register(client, email="alice@example.com", password="correct horse battery staple", name="Alice"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": name},
        headers=csrf_headers(client),
    )


def login(client, email, password):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )


def test_successful_registration_hashes_password(auth_harness):
    make_client, session_factory = auth_harness
    client = make_client()

    response = register(client)

    assert response.status_code == 201
    assert response.json()["email"] == "alice@example.com"
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "alice@example.com"))
        assert user is not None
        assert user.password_hash.startswith("$argon2")
        assert "correct horse battery staple" not in user.password_hash


def test_duplicate_registration_is_rejected(auth_harness):
    client = auth_harness[0]()
    assert register(client).status_code == 201

    response = register(client)

    assert response.status_code == 409


def test_invalid_registration_data_is_rejected(auth_harness):
    client = auth_harness[0]()

    response = register(client, password="short")

    assert response.status_code == 422


def test_successful_login_and_profile(auth_harness):
    client = auth_harness[0]()
    assert register(client).status_code == 201
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    response = login(client, "alice@example.com", "correct horse battery staple")

    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").json()["email"] == "alice@example.com"


def test_logout_clears_the_session(auth_harness):
    client = auth_harness[0]()
    assert register(client).status_code == 201

    response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_incorrect_password_is_generic_and_rejected(auth_harness):
    client = auth_harness[0]()
    assert register(client).status_code == 201
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    response = login(client, "alice@example.com", "wrong password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_missing_invalid_and_expired_tokens_are_rejected(auth_harness):
    client = auth_harness[0]()
    assert client.get("/api/v1/documents").status_code == 401

    client.cookies.set("documind_access", "not-a-jwt")
    assert client.get("/api/v1/documents").status_code == 401

    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": "missing-user",
            "iss": settings.jwt_issuer,
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "jti": "expired-test",
            "type": "access",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    client.cookies.set("documind_access", expired)
    assert client.get("/api/v1/documents").status_code == 401


def test_two_users_cannot_cross_access_documents_chunks_or_conversations(auth_harness):
    make_client, session_factory = auth_harness
    with session_factory() as db:
        alice = User(email="alice@example.com", display_name="Alice", password_hash=hash_password("alice password"))
        bob = User(email="bob@example.com", display_name="Bob", password_hash=hash_password("bob password"))
        db.add_all([alice, bob])
        db.flush()
        alice_doc = Document(name="alice.txt", original_name="alice.txt", content_type="text/plain", size_bytes=10, storage_path="alice.txt", owner_id=alice.id)
        bob_doc = Document(name="bob.txt", original_name="bob.txt", content_type="text/plain", size_bytes=10, storage_path="bob.txt", owner_id=bob.id)
        alice_conversation = Conversation(title="Alice thread", owner_id=alice.id)
        bob_conversation = Conversation(title="Bob thread", owner_id=bob.id)
        db.add_all([alice_doc, bob_doc, alice_conversation, bob_conversation])
        db.flush()
        db.add_all([
            DocumentChunk(document_id=alice_doc.id, chunk_index=0, content="Alice secret", token_count=2),
            DocumentChunk(document_id=bob_doc.id, chunk_index=0, content="Bob secret", token_count=2),
            Message(conversation_id=bob_conversation.id, role="assistant", content="Bob citation", citations_json="[]"),
        ])
        db.commit()
        alice_doc_id, bob_doc_id = alice_doc.id, bob_doc.id
        bob_conversation_id = bob_conversation.id

    alice_client = make_client()
    bob_client = make_client()
    assert login(alice_client, "alice@example.com", "alice password").status_code == 200
    assert login(bob_client, "bob@example.com", "bob password").status_code == 200

    alice_documents = alice_client.get("/api/v1/documents").json()
    assert [item["id"] for item in alice_documents] == [alice_doc_id]
    assert alice_client.get(f"/api/v1/documents/{bob_doc_id}").status_code == 404
    assert alice_client.get(f"/api/v1/documents/{bob_doc_id}/chunks").status_code == 404
    assert alice_client.get(f"/api/v1/conversations/{bob_conversation_id}/messages").status_code == 404

    # A forged legacy identity header cannot change the verified JWT owner.
    assert alice_client.get("/api/v1/documents", headers={"X-User-ID": "bob"}).json() == alice_documents

