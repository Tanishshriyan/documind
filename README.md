# DocuMind AI

DocuMind AI is a production-oriented document assistant with authenticated, grounded question answering. The repository is intentionally small and modular so the core document workflow remains easy to maintain.

## Repository layout

```text
backend/    FastAPI API, SQLAlchemy models, extraction and retrieval services
frontend/   React + TypeScript + Vite client
storage/    Local development document storage (created at runtime, ignored by git)
```

## Local development

### One-command startup

With Docker Desktop running, start the full product from the repository root:

```powershell
.\start.ps1
```

You can also simply double-click `start.bat`. The launcher automatically starts PostgreSQL, applies all Alembic migrations, starts the FastAPI backend (on port 8000), starts the Vite frontend (on port 5173), verifies server readiness, and opens your default browser directly to the DocuMind AI interface (`http://127.0.0.1:5173/`).

To cleanly shut down the application:

```powershell
.\stop.bat
```

Use `-SkipInstall` when dependencies are already installed, or `-SkipMigrations` only when the database schema is already current:

```powershell
.\start.ps1 -SkipInstall
```

### Backend

```powershell
docker compose up -d postgres

cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
# Edit .env and set GEMINI_API_KEY before indexing or chatting.
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Docker Compose provides the local PostgreSQL database on `localhost:5432`, including the pgvector extension and a persistent `documind_postgres` volume. The API is available at `http://localhost:8000`. Interactive documentation is available at `/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The client is available at `http://localhost:5173` and proxies `/api` requests to the backend.

Copy `.env.example` to `.env` when you need to override the development defaults. PostgreSQL is the default database. SQLite remains supported by setting `DATABASE_URL=sqlite:///./documind.db` explicitly.

### PostgreSQL with Docker Compose

```powershell
docker compose up -d postgres
```

This is the recommended local database workflow. The bundled pgvector-enabled PostgreSQL 16 service listens on port `5432`; stop it with `docker compose down` when finished. The migrations enable the `vector` extension, create a 768-dimensional embedding column for each indexed chunk, and add an HNSW cosine index.

The current migrations replace the old 384-dimensional placeholder column with `vector(768)`, record embedding provenance, and add the document ingestion lifecycle. Existing documents that were indexed under the old pipeline are marked `FAILED` with a reindex reason; regenerate them with Gemini after applying migrations:

```powershell
cd backend
python -m app.cli reindex-embeddings
```

To run the entire API stack in containers instead, use:

```powershell
Copy-Item .env.example .env
# Edit .env and set GEMINI_API_KEY before starting the API container.
docker compose up --build
```

## Document ingestion

- Supported uploads are PDF, DOCX, and TXT. PDFs are extracted with PyMuPDF; DOCX files use `python-docx`; TXT files use safe BOM-aware decoding. File signatures are checked before processing, so the browser MIME type is not trusted.
- Uploads are bounded by `DOCUMENT_MAX_UPLOAD_SIZE_MB`, `DOCUMENT_MAX_PAGES`, and `DOCUMENT_MAX_EXTRACTED_CHARS`. Empty, corrupted, unsupported, and over-limit documents are rejected without indexing.
- A successful upload is stored with a SHA-256 checksum and enters `PENDING`, then `PROCESSING`, and only becomes `READY` after all chunks and 768-dimensional Gemini embeddings are committed. Failed processing is marked `FAILED` with a safe failure reason.
- PDF citations use one-based physical page numbers. DOCX and TXT use the explicit `logical_document` policy and therefore omit physical page numbers.
- Chunks retain document ID, filename, page metadata, ordering, and source text. Raw vectors and internal storage keys are never returned by the API.
- Assistant citations include the stable database chunk ID, document ID/name, source labels (`[S1]`, `[S2]`, ...), page number when available, relevance, and an excerpt taken from the retrieved chunk. Citation labels and metadata are application-generated from the retrieved evidence; Gemini does not invent citation records.
- Same-user duplicate uploads are detected by `(owner_id, checksum_sha256)`; another user’s documents are never considered.

Document endpoints:

```text
POST   /api/v1/documents/upload
GET    /api/v1/documents?page=1&page_size=20
GET    /api/v1/documents/{document_id}
GET    /api/v1/documents/{document_id}/chunks
DELETE /api/v1/documents/{document_id}
```

Listing supports `page` and `page_size` query parameters and returns pagination headers (`X-Total-Count`, `X-Page`, and `X-Page-Size`). Every endpoint is authenticated and owner-scoped at the database query.

Conversation endpoints:

```text
POST   /api/v1/conversations
POST   /api/v1/conversations/with-message
GET    /api/v1/conversations?page=1&page_size=20
GET    /api/v1/conversations/{conversation_id}
PATCH  /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}
GET    /api/v1/conversations/{conversation_id}/messages?page=1&page_size=100
POST   /api/v1/conversations/{conversation_id}/messages
```

`POST /conversations/with-message` validates the selected documents, generates the answer, and then commits the new conversation plus its user and assistant messages in one database transaction. A Gemini failure therefore does not leave an empty conversation or a partial message pair. Existing conversation creation and message endpoints remain supported. Conversation and message listings are owner-scoped, paginated, and return the same pagination headers shown above.

Chat document scope is persisted on each user message. An omitted or `null` `document_ids` value searches all accessible `READY` documents, an empty array searches no documents, and a non-empty array searches only those owned document IDs. Reopening a conversation restores the latest user message's scope in the frontend.

After establishing the authenticated HttpOnly session and CSRF header, an upload is a standard multipart request:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/documents/upload `
  -H "X-CSRF-Token: <csrf-cookie-value>" `
  -b "documind_access=<session-cookie>; documind_csrf=<csrf-cookie-value>" `
  -F "file=@C:\path\to\research.pdf"
```

## Document storage

Local storage is intended for development only:

```env
DOCUMENT_STORAGE_BACKEND=local
DOCUMENT_STORAGE_PATH=storage/documents
DOCUMENT_MAX_UPLOAD_SIZE_MB=25
DOCUMENT_MAX_PAGES=500
DOCUMENT_MAX_EXTRACTED_CHARS=5000000
```

Production must use the S3-compatible adapter and a durable bucket. Configure `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, and `S3_REGION`; do not use the container filesystem as production document storage. The backend stores opaque object keys and never sends credentials or internal paths to the frontend.

The upload request stores the validated object and database metadata, then schedules processing with FastAPI background tasks. This MVP deliberately does not require Redis, Celery, Kafka, or another queue. Deletion verifies ownership, removes the stored object, and cascades chunks through the database foreign key.

Questions and the relevant extracted excerpts are sent to Google’s Gemini API for embedding and answer generation. Uploaded files and unrelated document excerpts are not sent to Gemini. Application conversation history remains in PostgreSQL.

## Phase 1 behavior

- Stores conversations and message history.
- Generates 768-dimensional semantic embeddings with Gemini Embedding 2 and retrieves chunks with pgvector cosine similarity.
- Generates grounded answers with Gemini Interactions API using only retrieved excerpts and recent application-owned conversation context.
- Keeps the Gemini API key exclusively on the backend. Questions and retrieved excerpts are sent to Google Gemini for processing; application conversation history remains in PostgreSQL.
- Stores conversations and message history.
- Generates 768-dimensional semantic embeddings with Gemini Embedding 2 and retrieves chunks with pgvector cosine similarity.
- Generates grounded answers with Gemini Interactions API using only retrieved excerpts and recent application-owned conversation context.
- Keeps the Gemini API key exclusively on the backend. Questions and retrieved excerpts are sent to Google Gemini for processing; application conversation history remains in PostgreSQL.

## Gemini configuration

Set `GEMINI_API_KEY` in `backend/.env` or the root `.env` used by Docker Compose. Model names, embedding dimension, batch size, retry count, and timeout are configurable through the `GEMINI_*` variables in `.env.example`. The MVP uses Gemini only; there is no local model or provider fallback.

Gemini requests use `store=false`, so DocuMind does not depend on Google's stored conversation state. Citations are created from the retrieved database chunks and are never generated by the model.

Document and conversation queries are scoped by the verified JWT subject and the corresponding database user. User IDs are never accepted from request headers, bodies, or query parameters.

## Authentication

The API provides:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

Passwords are hashed with Argon2 through `pwdlib`. Access JWTs are stored in an HttpOnly cookie and verified against the database user on every protected request. Mutating requests also require the CSRF token from the readable CSRF cookie in the `X-CSRF-Token` header. The React client uses `credentials: include`, never stores tokens in localStorage, and clears authenticated state on logout or session expiry.

The `0006_users` migration preserves pre-auth workspace owner IDs as disabled legacy identities. Existing legacy documents are not automatically assigned to a new account. The `0007_document_ingestion` migration adds checksum, storage key, lifecycle timestamps, chunk counts, and provenance fields. The `0008_message_document_scope` migration adds nullable per-user-message document scope storage; existing messages remain compatible and represent all-source scope.

## Verification

```powershell
cd backend
python -m compileall app
alembic check
python -m pytest -q

cd ..\frontend
npm run typecheck
npm run build
```

