from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Conversation, Document, Message, User
from app.services.gemini_gateway import GeminiProviderError


def csrf_headers(client):
    client.get("/api/v1/auth/csrf")
    return {"X-CSRF-Token": client.cookies.get("documind_csrf")}


def register(client, email="owner@example.com"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": email.split("@")[0].title(),
        },
        headers=csrf_headers(client),
    )


def fake_answer(*_args, **_kwargs):
    return "A grounded answer.", []


def parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def conversation_for(session_factory, email: str, conversation_id: str) -> Conversation:
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.owner_id == user.id,
            )
        )
        assert conversation is not None
        return conversation


def test_atomic_first_message_persists_conversation_and_pair(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    monkeypatch.setattr("app.api.routes.chat.answer_question", fake_answer)

    response = client.post(
        "/api/v1/conversations/with-message",
        json={"content": "What does the policy say?"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["conversation"]["message_count"] == 2
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert payload["messages"][1]["content"] == "A grounded answer."
    with session_factory() as db:
        conversation = db.get(Conversation, payload["conversation"]["id"])
        assert conversation is not None
        assert db.scalars(select(Message).where(Message.conversation_id == conversation.id)).all().__len__() == 2


def test_gemini_failure_does_not_leave_empty_initial_conversation(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201

    def fail_answer(*_args, **_kwargs):
        raise GeminiProviderError()

    monkeypatch.setattr("app.api.routes.chat.answer_question", fail_answer)
    response = client.post(
        "/api/v1/conversations/with-message",
        json={"content": "This must be atomic."},
        headers=csrf_headers(client),
    )

    assert response.status_code == 502
    with session_factory() as db:
        assert db.scalars(select(Conversation)).all() == []
        assert db.scalars(select(Message)).all() == []


def test_message_source_scope_round_trips_all_none_empty_and_explicit_ids(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    monkeypatch.setattr("app.api.routes.chat.answer_question", fake_answer)
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "owner@example.com"))
        document = Document(
            name="scope.txt",
            original_name="scope.txt",
            content_type="text/plain",
            size_bytes=5,
            owner_id=user.id,
        )
        db.add(document)
        db.commit()
        document_id = document.id

    all_sources = client.post(
        "/api/v1/conversations/with-message",
        json={"content": "Use every source."},
        headers=csrf_headers(client),
    )
    assert all_sources.status_code == 201
    all_messages = all_sources.json()["messages"]
    assert all_messages[0]["document_ids"] is None

    none_sources_conversation = client.post(
        "/api/v1/conversations",
        json={"title": "No sources"},
        headers=csrf_headers(client),
    ).json()["id"]
    none_sources = client.post(
        f"/api/v1/conversations/{none_sources_conversation}/messages",
        json={"content": "Use no source.", "document_ids": []},
        headers=csrf_headers(client),
    )
    assert none_sources.status_code == 200
    assert none_sources.json()["user_message"]["document_ids"] == []

    explicit_sources = client.post(
        "/api/v1/conversations/with-message",
        json={"content": "Use one source.", "document_ids": [document_id]},
        headers=csrf_headers(client),
    )
    assert explicit_sources.status_code == 201
    assert explicit_sources.json()["messages"][0]["document_ids"] == [document_id]

    reopened = client.get(f"/api/v1/conversations/{none_sources_conversation}/messages")
    assert reopened.status_code == 200
    assert reopened.json()[0]["document_ids"] == []
    with session_factory() as db:
        message = db.scalar(
            select(Message).where(
                Message.conversation_id == none_sources_conversation,
                Message.role == "user",
            )
        )
        assert message.selected_document_ids_json == "[]"


def test_legacy_citation_json_remains_readable(auth_harness):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "owner@example.com"))
        conversation = Conversation(title="Legacy citations", owner_id=user.id)
        db.add(conversation)
        db.flush()
        db.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="A historical answer.",
                citations_json=json.dumps([{
                    "document_id": "legacy-document",
                    "document_name": "legacy.txt",
                    "page_number": 3,
                    "excerpt": "Historical excerpt.",
                    "relevance": 0.75,
                }]),
            )
        )
        db.commit()
        conversation_id = conversation.id

    response = client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert response.status_code == 200
    citation = response.json()[0]["citations"][0]
    assert citation["document_id"] == "legacy-document"
    assert citation["chunk_id"] is None
    assert citation["source_label"] is None


def test_existing_exchange_persists_both_messages_and_updates_activity(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    monkeypatch.setattr("app.api.routes.chat.answer_question", fake_answer)
    created = client.post(
        "/api/v1/conversations",
        json={"title": "Research"},
        headers=csrf_headers(client),
    )
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Summarize the evidence."},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["user_message"]["content"] == "Summarize the evidence."
    assert response.json()["assistant_message"]["content"] == "A grounded answer."
    with session_factory() as db:
        messages = db.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        ).all()
        assert [message.role for message in messages] == ["user", "assistant"]
        assert db.get(Conversation, conversation_id).updated_at > db.get(Conversation, conversation_id).created_at


def test_rename_and_delete_conversation_cascade_messages(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    monkeypatch.setattr("app.api.routes.chat.answer_question", fake_answer)
    created = client.post("/api/v1/conversations", json={}, headers=csrf_headers(client))
    conversation_id = created.json()["id"]
    assert client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Keep this thread."},
        headers=csrf_headers(client),
    ).status_code == 200

    renamed = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Renamed thread"},
        headers=csrf_headers(client),
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed thread"
    assert client.get(f"/api/v1/conversations/{conversation_id}").json()["title"] == "Renamed thread"

    deleted = client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=csrf_headers(client),
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    with session_factory() as db:
        assert db.get(Conversation, conversation_id) is None
        assert db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all() == []


def test_failed_exchange_does_not_update_timestamp_or_create_messages(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    created = client.post("/api/v1/conversations", json={}, headers=csrf_headers(client))
    conversation_id = created.json()["id"]
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    with session_factory() as db:
        conversation = db.get(Conversation, conversation_id)
        conversation.updated_at = old_time
        db.commit()
    before = client.get(f"/api/v1/conversations/{conversation_id}").json()["updated_at"]

    def fail_answer(*_args, **_kwargs):
        raise GeminiProviderError()

    monkeypatch.setattr("app.api.routes.chat.answer_question", fail_answer)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "This will fail."},
        headers=csrf_headers(client),
    )

    assert response.status_code == 502
    after = client.get(f"/api/v1/conversations/{conversation_id}").json()["updated_at"]
    assert parse_instant(after) == parse_instant(before)
    with session_factory() as db:
        assert db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all() == []


def test_conversation_and_message_access_is_isolated_between_users(auth_harness):
    make_client, _ = auth_harness
    alice = make_client()
    bob = make_client()
    assert register(alice, "alice@example.com").status_code == 201
    assert register(bob, "bob@example.com").status_code == 201
    conversation = alice.post(
        "/api/v1/conversations",
        json={"title": "Alice private thread"},
        headers=csrf_headers(alice),
    ).json()
    conversation_id = conversation["id"]

    assert bob.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    assert bob.get(f"/api/v1/conversations/{conversation_id}/messages").status_code == 404
    assert bob.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Stolen"},
        headers=csrf_headers(bob),
    ).status_code == 404
    assert bob.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=csrf_headers(bob),
    ).status_code == 404


def test_conversation_and_message_pagination_have_stable_order(auth_harness):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    created_ids = []
    for index in range(5):
        response = client.post(
            "/api/v1/conversations",
            json={"title": f"Thread {index}"},
            headers=csrf_headers(client),
        )
        created_ids.append(response.json()["id"])
    page = client.get("/api/v1/conversations?page=2&page_size=2")
    assert page.status_code == 200
    assert len(page.json()) == 2
    assert page.headers["X-Total-Count"] == "5"
    assert page.headers["X-Page"] == "2"
    assert page.headers["X-Page-Size"] == "2"

    conversation_id = created_ids[0]
    with session_factory() as db:
        timestamp = datetime.now(timezone.utc)
        db.add_all([
            Message(
                conversation_id=conversation_id,
                role="user",
                content=f"message {index}",
                citations_json="[]",
                created_at=timestamp,
            )
            for index in range(5)
        ])
        db.commit()
    messages = client.get(f"/api/v1/conversations/{conversation_id}/messages?page=2&page_size=2")
    assert messages.status_code == 200
    assert [item["content"] for item in messages.json()] == ["message 2", "message 3"]
    assert messages.headers["X-Total-Count"] == "5"


def test_invalid_pagination_and_message_content_are_rejected(auth_harness):
    make_client, _ = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    assert client.get("/api/v1/conversations?page=0").status_code == 422
    assert client.get("/api/v1/conversations?page_size=101").status_code == 422
    assert client.post(
        "/api/v1/conversations/with-message",
        json={"content": "   "},
        headers=csrf_headers(client),
    ).status_code == 422


def test_selected_document_must_belong_to_authenticated_user(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    alice = make_client()
    bob = make_client()
    assert register(alice, "alice@example.com").status_code == 201
    assert register(bob, "bob@example.com").status_code == 201
    with session_factory() as db:
        alice_user = db.scalar(select(User).where(User.email == "alice@example.com"))
        document = Document(
            name="alice.txt",
            original_name="alice.txt",
            content_type="text/plain",
            size_bytes=5,
            owner_id=alice_user.id,
        )
        db.add(document)
        db.commit()
        document_id = document.id
    monkeypatch.setattr("app.api.routes.chat.answer_question", fake_answer)

    response = bob.post(
        "/api/v1/conversations/with-message",
        json={"content": "Read Alice's file.", "document_ids": [document_id]},
        headers=csrf_headers(bob),
    )

    assert response.status_code == 404
    with session_factory() as db:
        bob_user = db.scalar(select(User).where(User.email == "bob@example.com"))
        assert db.scalars(select(Conversation).where(Conversation.owner_id == bob_user.id)).all() == []


def test_exchange_commit_rolls_back_both_messages_and_timestamp(auth_harness, monkeypatch):
    make_client, session_factory = auth_harness
    client = make_client()
    assert register(client).status_code == 201
    monkeypatch.setattr("app.api.routes.chat.answer_question", fake_answer)
    conversation_id = client.post(
        "/api/v1/conversations",
        json={},
        headers=csrf_headers(client),
    ).json()["id"]
    before = client.get(f"/api/v1/conversations/{conversation_id}").json()["updated_at"]
    original_commit = Session.commit

    def fail_message_commit(session):
        if any(isinstance(item, Message) for item in session.new):
            raise SQLAlchemyError("forced transaction failure")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_message_commit)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Do not partially save this."},
        headers=csrf_headers(client),
    )

    assert response.status_code == 500
    after = client.get(f"/api/v1/conversations/{conversation_id}").json()["updated_at"]
    assert parse_instant(after) == parse_instant(before)
    with session_factory() as db:
        assert db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all() == []
