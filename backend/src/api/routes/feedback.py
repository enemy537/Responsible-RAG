"""
routes/feedback.py — Feedback endpoints
=========================================
Endpoints:
    POST /api/v1/feedback/message  — Rate a specific message (thumbs up/down)
    POST /api/v1/feedback          — Submit general feedback
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from src.api.db.database import get_database
from src.api.schemas.feedback import (
    FeedbackResponse,
    FeedbackSubmitRequest,
    MessageFeedbackRequest,
)
from src.api.security import get_current_user

router = APIRouter()


@router.post("/message", response_model=FeedbackResponse)
async def submit_message_feedback(
    body: MessageFeedbackRequest,
    current_user: dict | None = Depends(get_current_user),
):
    """
    Record thumbs up / thumbs down feedback on a specific chat message.

    Works for both authenticated and anonymous users.
    """
    db = get_database()
    if db is None:
        raise HTTPException(503, "Database not available")

    doc = {
        "user_id": current_user.get("sub") if current_user else None,
        "conversation_id": body.conversation_id,
        "message_id": body.message_id,
        "rating": body.rating,
        "comment": body.comment,
        "feedback_type": f"thumbs_{body.rating}",
        "created_at": datetime.now(UTC).isoformat(),
    }
    result = db["feedback"].insert_one(doc)
    return FeedbackResponse(id=str(result.inserted_id), status="recorded")


@router.post("", response_model=FeedbackResponse)
async def submit_general_feedback(
    body: FeedbackSubmitRequest,
    current_user: dict | None = Depends(get_current_user),
):
    """
    Submit general feedback from the feedback page.

    Not tied to any specific conversation or message.
    """
    db = get_database()
    if db is None:
        raise HTTPException(503, "Database not available")

    doc = {
        "user_id": current_user.get("sub") if current_user else None,
        "feedback_type": body.feedback_type,
        "subject": body.subject,
        "message": body.message,
        "include_anonymous_data": body.include_anonymous_data,
        "created_at": datetime.now(UTC).isoformat(),
    }
    result = db["feedback"].insert_one(doc)
    return FeedbackResponse(id=str(result.inserted_id), status="recorded")
