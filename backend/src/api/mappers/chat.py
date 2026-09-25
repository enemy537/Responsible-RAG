"""Mapping between Mongo documents and chat API payloads."""

from src.api.schemas.chat import CitationSchema

DEFAULT_CONVERSATION_TITLE = "New conversation"


def conversation_to_response(doc: dict, messages: list[dict] | None = None) -> dict:
    """Serialise a conversation document (optionally with its messages)."""
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", DEFAULT_CONVERSATION_TITLE),
        "profile_key": doc.get("profile_key"),
        "messages": [message_to_response(message) for message in (messages or [])],
        "message_count": doc.get("message_count", 0),
        "created_at": doc.get("created_at", ""),
        "updated_at": doc.get("updated_at", ""),
    }


def conversation_to_list_item(doc: dict) -> dict:
    """Serialise a conversation document for the sidebar list."""
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", DEFAULT_CONVERSATION_TITLE),
        "last_message": doc.get("last_message"),
        "last_message_at": doc.get("last_message_at"),
        "created_at": doc.get("created_at", ""),
        "message_count": doc.get("message_count", 0),
    }


def message_to_response(doc: dict) -> dict:
    """Serialise a message document."""
    return {
        "id": str(doc["_id"]),
        "conversation_id": doc.get("conversation_id", ""),
        "role": doc.get("role", "user"),
        "content": doc.get("content", ""),
        "citations": doc.get("citations", []),
        "is_streaming": doc.get("is_streaming", False),
        "created_at": doc.get("created_at", ""),
    }


def build_citations(sources: list[dict]) -> list[CitationSchema]:
    """Convert RAG source metadata into numbered citation schemas."""
    return [
        CitationSchema(
            id=f"cit-{index}",
            source_id=source.get("source_id", ""),
            source_title=source.get("source_title", "Unknown source"),
            source_type=source.get("source_type", "pdf"),
            authors=source.get("authors") or [],
            publication_date=source.get("publication_date") or None,
            publisher=source.get("publisher") or None,
            url=source.get("url") or "",
            doi=source.get("doi") or "",
            language=source.get("language") or None,
            description=source.get("description") or None,
            tags=source.get("tags") or [],
            content_sensitivity=source.get("content_sensitivity") or "low",
            excerpt=source.get("excerpt", ""),
            number=index + 1,
        )
        for index, source in enumerate(sources)
    ]
