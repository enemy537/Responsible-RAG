"""Re-export of every API schema for convenient importing."""

from src.api.schemas.admin_alert import AdminAlertListResponse, AdminAlertResponse
from src.api.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from src.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatStreamRequest,
    CitationSchema,
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    RenameConversationRequest,
)
from src.api.schemas.common import (
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
    StatsResponse,
)
from src.api.schemas.feedback import (
    FeedbackResponse,
    FeedbackSubmitRequest,
    MessageFeedbackRequest,
)
from src.api.schemas.profile import (
    AdaptationField,
    ConsentResponse,
    ConsentUpdateRequest,
    GenerateProfileRequest,
    GenerateProfileResponse,
    ProfileMode,
    ProfileResponse,
    ProfileUpdateRequest,
)
from src.api.schemas.source import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
    SourceType,
    SourceUpdateRequest,
    UploadResponse,
    URLUploadRequest,
    YouTubeUploadRequest,
)

__all__ = [
    "AdaptationField",
    "AdminAlertListResponse",
    "AdminAlertResponse",
    "ChatRequest",
    "ChatResponse",
    "ChatStreamRequest",
    "CitationSchema",
    "ConsentResponse",
    "ConsentUpdateRequest",
    "ConversationListItem",
    "ConversationListResponse",
    "ConversationResponse",
    "CreateConversationRequest",
    "ErrorResponse",
    "FeedbackResponse",
    "FeedbackSubmitRequest",
    "ForgotPasswordRequest",
    "GenerateProfileRequest",
    "GenerateProfileResponse",
    "LoginRequest",
    "MessageFeedbackRequest",
    "MessageResponse",
    "PaginatedResponse",
    "PaginationParams",
    "ProfileMode",
    "ProfileResponse",
    "ProfileUpdateRequest",
    "RegisterRequest",
    "RenameConversationRequest",
    "SourceCreateRequest",
    "SourceListResponse",
    "SourceResponse",
    "SourceType",
    "SourceUpdateRequest",
    "StatsResponse",
    "TokenResponse",
    "UploadResponse",
    "URLUploadRequest",
    "YouTubeUploadRequest",
]
