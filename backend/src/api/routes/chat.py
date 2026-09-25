"""Chat routes: conversations, messages, and RAG."""

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_chat_service, get_profile_generator, get_rag_chain
from src.api.mappers.chat import build_citations
from src.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    RenameConversationRequest,
)
from src.api.security import get_current_user
from src.api.services.chat_service import ChatService
from src.core.profile_prompt import build_profile_prompt

router = APIRouter()


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
):
    """List the current user's conversations, newest first."""
    return service.list_conversations(current_user["sub"], page, limit)


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
):
    """Create an empty conversation."""
    return service.create_conversation(current_user["sub"], body.title, body.profile_key)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
):
    """Return a conversation with all of its messages."""
    return service.get_conversation(current_user["sub"], conversation_id)


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: str,
    body: RenameConversationRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
):
    """Rename a conversation."""
    return service.rename_conversation(current_user["sub"], conversation_id, body.title)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
):
    """Delete a conversation and its messages."""
    service.delete_conversation(current_user["sub"], conversation_id)
    return {"status": "ok"}


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
):
    """Return a page of messages for a conversation."""
    return service.list_messages(current_user["sub"], conversation_id, page, limit)


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    chain=Depends(get_rag_chain),
    generator=Depends(get_profile_generator),
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
):
    """Answer a question through the RAG chain and persist the exchange."""
    user_id = current_user["sub"]
    group_prompt = build_profile_prompt(service.profile_doc(user_id), generator, body.question)

    turn = service.begin_turn(
        user_id,
        question=body.question,
        profile_key=body.profile_key,
        conversation_id=body.conversation_id,
    )

    result = chain.invoke(body.question, group_prompt, turn.memory_context)
    citations = build_citations(result.sources)
    message_id = service.finish_turn(
        turn,
        question=body.question,
        answer=result.answer,
        citations=[citation.model_dump() for citation in citations],
    )

    return ChatResponse(
        answer=result.answer,
        sources=citations,
        conversation_id=turn.conversation_id,
        message_id=message_id,
        profile_key=body.profile_key,
    )
