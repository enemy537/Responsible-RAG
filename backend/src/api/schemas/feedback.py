"""
schemas/feedback.py — User feedback models
============================================
Covers per-message feedback (thumbs up/down) and general feedback forms.
"""


from pydantic import BaseModel, Field


class MessageFeedbackRequest(BaseModel):
    """
    Feedback on a specific message from the chat.

    Mirrors the frontend's ``PostChatFeedback`` component.
    """

    conversation_id: str = Field(
        ..., description="Conversation the message belongs to.",
    )
    message_id: str = Field(
        ..., description="The specific message being rated.",
    )
    rating: str = Field(
        ..., description="'up' for thumbs up, 'down' for thumbs down.",
        pattern="^(up|down)$",
    )
    comment: str | None = Field(
        None, max_length=2000,
        description="Optional free-text explanation.",
    )


class FeedbackSubmitRequest(BaseModel):
    """
    General feedback not tied to a specific message.

    Matches the frontend's Feedback page form.
    """

    feedback_type: str = Field(
        ..., description="Type of feedback.",
        example="general",
    )
    subject: str | None = Field(
        None, max_length=200,
        description="Short subject line.",
    )
    message: str = Field(
        ..., min_length=1, max_length=5000,
        description="Feedback text body.",
    )
    include_anonymous_data: bool = Field(
        False,
        description="Whether to include anonymised conversation context.",
    )


class FeedbackResponse(BaseModel):
    """Confirmation that feedback was recorded."""

    id: str = Field(..., description="Feedback record ID.")
    status: str = Field("recorded", description="'recorded' or 'submitted'.")
    message: str = Field(
        "Thank you for your feedback!",
        description="User-facing confirmation message.",
    )
