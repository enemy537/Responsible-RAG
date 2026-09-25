"""Profile, consent, and personalised-prompt endpoints."""

from fastapi import APIRouter, Depends

from src.api.db.repositories import (
    ConsentRepository,
    ConversationRepository,
    MessageRepository,
    ProfileRepository,
)
from src.api.deps import (
    get_consent_repository,
    get_conversation_repository,
    get_message_repository,
    get_profile_generator,
    get_profile_repository,
)
from src.api.errors import NotFoundError, ValidationError
from src.api.mappers.profile import (
    adaptation_fields,
    consent_to_response,
    count_provided_fields,
    profile_to_response,
)
from src.api.schemas.profile import (
    ConsentUpdateRequest,
    GenerateProfileRequest,
    GenerateProfileResponse,
    ProfileUpdateRequest,
)
from src.api.security import get_current_user
from src.api.services.profile_generator_service import ProfileGeneratorService

router = APIRouter()


# ── Profile ───────────────────────────────────────────────────────────────────


@router.get("")
async def get_profile(
    repository: ProfileRepository = Depends(get_profile_repository),
    current_user: dict = Depends(get_current_user),
):
    """Return the current user's demographic profile."""
    doc = repository.get(current_user["sub"])
    if doc is None:
        raise NotFoundError("No profile found. Complete onboarding first.")
    return profile_to_response(doc)


@router.put("")
async def update_profile(
    body: ProfileUpdateRequest,
    repository: ProfileRepository = Depends(get_profile_repository),
    current_user: dict = Depends(get_current_user),
):
    """Create or update the user's demographic profile."""
    data = body.model_dump(exclude_none=True)
    if not data:
        raise ValidationError("No fields to update")
    return profile_to_response(repository.upsert(current_user["sub"], data))


# ── Prompt generation ─────────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateProfileResponse)
async def generate_profile(
    body: GenerateProfileRequest,
    generator: ProfileGeneratorService = Depends(get_profile_generator),
    current_user: dict = Depends(get_current_user),
):
    """Render a personalised system prompt from demographic data.

    Each non-default field is enriched with evidence-based communication
    rules retrieved from the profiles knowledge base.
    """
    prompt = generator.generate_prompt(
        user_profile=body.user_profile,
        user_query=body.user_query,
        retrieved_documents=body.retrieved_documents or "",
    )
    return GenerateProfileResponse(
        prompt=prompt,
        prompt_length=len(prompt),
        fields_provided=count_provided_fields(body.user_profile),
        sources_used=generator.last_source_titles,
        adaptation_fields=adaptation_fields(body.user_profile),
    )


# ── Consent ───────────────────────────────────────────────────────────────────


@router.get("/consent")
async def get_consent(
    repository: ConsentRepository = Depends(get_consent_repository),
    current_user: dict = Depends(get_current_user),
):
    """Return the user's consent and privacy preferences."""
    doc = repository.get(current_user["sub"])
    if doc is None:
        raise NotFoundError("No consent record found.")
    return consent_to_response(doc)


@router.put("/consent")
async def update_consent(
    body: ConsentUpdateRequest,
    repository: ConsentRepository = Depends(get_consent_repository),
    current_user: dict = Depends(get_current_user),
):
    """Create or update consent preferences."""
    data = body.model_dump(exclude_none=True)
    if not data:
        raise ValidationError("No fields to update")
    return consent_to_response(repository.upsert(current_user["sub"], data))


# ── Data deletion ─────────────────────────────────────────────────────────────


@router.delete("/data")
async def delete_user_data(
    profiles: ProfileRepository = Depends(get_profile_repository),
    consent: ConsentRepository = Depends(get_consent_repository),
    conversations: ConversationRepository = Depends(get_conversation_repository),
    messages: MessageRepository = Depends(get_message_repository),
    current_user: dict = Depends(get_current_user),
):
    """Delete everything owned by the current user (right to erasure)."""
    email = current_user["sub"]
    profiles.delete(email)
    consent.delete(email)
    conversation_ids = conversations.ids_for_user(email)
    if conversation_ids:
        messages.delete_for_conversations(conversation_ids)
    conversations.delete_for_user(email)
    return {"message": "All user data deleted"}
