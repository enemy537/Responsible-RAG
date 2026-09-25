"""
schemas/chat.py — Chat & conversation models
==============================================
Mirrors the frontend's ``types/chat.ts`` interfaces.
"""


from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════════
# Embedded objects
# ═══════════════════════════════════════════════════════════════════════════════

class CitationSchema(BaseModel):
    """A source citation attached to an assistant message."""

    id: str = Field(..., description="Citation ID.")
    source_id: str = Field(..., description="Source document ID.")
    source_title: str = Field("", description="Document title.")
    source_type: str = Field("pdf", description="Type of source (pdf, text, webpage, etc.).")
    authors: list[str] = Field(default_factory=list, description="Author names.")
    publication_date: str | None = Field(None, description="Publication date (ISO-8601).")
    publisher: str | None = Field(None, description="Publisher name.")
    url: str = Field("", description="Source URL.")
    doi: str = Field("", description="Digital Object Identifier.")
    language: str | None = Field(None, description="Language code (e.g. 'en', 'fr').")
    description: str | None = Field(None, description="Document summary.")
    tags: list[str] = Field(default_factory=list, description="Tags / keywords.")
    content_sensitivity: str = Field("low", description="'low', 'medium', or 'high'.")
    excerpt: str = Field(..., description="Relevant excerpt from the source.")
    number: int = Field(..., description="Citation number (rendered as [1], [2], etc.).")


# ═══════════════════════════════════════════════════════════════════════════════
# Chat (RAG)
# ═══════════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    """Single-turn Q&A with the RAG pipeline."""

    question: str = Field(
        ..., min_length=1, max_length=4096,
        description="The user's question.",
        example="What are my rights under the Canadian Charter?",
    )
    conversation_id: str | None = Field(
        None, description="Existing conversation ID for multi-turn context.",
    )
    profile_key: str | None = Field(
        None, description="Audience profile key (e.g. 'senior', 'lgbt_teen').",
    )


class ChatResponse(BaseModel):
    """Response from the single-turn chat endpoint."""

    answer: str = Field(..., description="Generated answer text.")
    sources: list[CitationSchema] = Field(
        default_factory=list, description="Source citations.",
    )
    conversation_id: str = Field(
        ..., description="Conversation ID (new or existing).",
    )
    message_id: str = Field(
        ..., description="The assistant message ID.",
    )
    profile_key: str | None = Field(None)


class ChatStreamRequest(BaseModel):
    """Request body for the streaming chat endpoint (SSE)."""

    question: str = Field(
        ..., min_length=1, max_length=4096,
        description="The user's question.",
    )
    conversation_id: str | None = Field(
        None, description="Existing conversation ID.",
    )
    profile_key: str | None = Field(
        None, description="Optional audience profile key.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Conversations
# ═══════════════════════════════════════════════════════════════════════════════

class CreateConversationRequest(BaseModel):
    """Start a new conversation."""

    title: str | None = Field(
        None, max_length=200,
        description="Optional title (auto-generated from first message if omitted).",
    )
    profile_key: str | None = Field(
        None, description="Audience profile for this conversation.",
    )


class RenameConversationRequest(BaseModel):
    """Rename an existing conversation."""

    title: str = Field(
        ..., min_length=1, max_length=200,
        description="New conversation title.",
    )


class ConversationListItem(BaseModel):
    """Summary of a conversation for the sidebar list."""

    id: str = Field(..., description="Conversation ID.")
    title: str = Field(..., description="Conversation title.")
    last_message: str | None = Field(None, description="Preview of last message.")
    last_message_at: str | None = Field(None, description="ISO-8601 timestamp.")
    created_at: str = Field(..., description="ISO-8601 timestamp.")
    message_count: int = Field(0)


class ConversationListResponse(BaseModel):
    """Paginated list of conversations for a user."""

    conversations: list[ConversationListItem] = Field(
        default_factory=list,
    )
    total: int = Field(0)
    page: int = Field(1)
    limit: int = Field(20)


class ConversationResponse(BaseModel):
    """Full conversation with messages."""

    id: str = Field(...)
    title: str = Field(...)
    profile_key: str | None = Field(None)
    messages: list["MessageResponse"] = Field(default_factory=list)
    message_count: int = Field(0)
    created_at: str = Field(...)
    updated_at: str = Field(...)


class MessageResponse(BaseModel):
    """A single message within a conversation."""

    id: str = Field(...)
    conversation_id: str = Field(...)
    role: str = Field(..., description="'user' or 'assistant'.")
    content: str = Field(..., description="Message text.")
    citations: list[CitationSchema] = Field(default_factory=list)
    is_streaming: bool = Field(False)
    created_at: str = Field(...)
