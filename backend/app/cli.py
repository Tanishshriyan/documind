from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Document
from app.services.gemini_gateway import GeminiError
from app.services.gemini_embeddings import GeminiEmbeddingService
from app.services.indexing import embed_document_chunks


def reindex_embeddings() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    db = SessionLocal()
    indexed = 0
    try:
        documents = db.scalars(select(Document).order_by(Document.created_at)).unique().all()
        service = GeminiEmbeddingService()
        for document in documents:
            if not document.chunks:
                document.status = "FAILED"
                document.failure_reason = "Document has no searchable chunks."
                db.commit()
                continue
            document.status = "PROCESSING"
            db.flush()
            embed_document_chunks(document, service)
            document.status = "READY"
            document.failure_reason = None
            document.error_message = None
            document.chunk_count = len(document.chunks)
            db.commit()
            indexed += 1
            logging.info("Re-indexed document %s", document.id)
        return indexed
    except GeminiError:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="DocuMind maintenance commands")
    parser.add_argument("command", choices=["reindex-embeddings"])
    args = parser.parse_args()
    if args.command == "reindex-embeddings":
        print(f"Re-indexed {reindex_embeddings()} document(s).")


if __name__ == "__main__":
    main()

