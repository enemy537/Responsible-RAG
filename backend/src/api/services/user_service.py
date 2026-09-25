"""Admin-facing user queries and mutations."""

from src.api.db.repositories import (
    ConsentRepository,
    ConversationRepository,
    MessageRepository,
    ProfileRepository,
    UserRepository,
)
from src.api.errors import ForbiddenError, ValidationError
from src.api.services.auth_service import hash_password, serialize_user

_ROLE_CHOICES = ("user", "admin")


class UserService:
    """Aggregates user data across collections for the admin UI."""

    def __init__(
        self,
        *,
        users: UserRepository,
        profiles: ProfileRepository,
        consent: ConsentRepository,
        conversations: ConversationRepository,
        messages: MessageRepository,
    ) -> None:
        self._users = users
        self._profiles = profiles
        self._consent = consent
        self._conversations = conversations
        self._messages = messages

    # ── List / detail ─────────────────────────────────────────────────────────

    def list_users(self, search: str | None = None) -> list[dict]:
        return [self._enrich(serialize_user(doc)) for doc in self._users.search(search)]

    def get_user(self, user_id: str) -> dict:
        return self._enrich(serialize_user(self._users.require_by_id(user_id)))

    def get_profile(self, user_id: str) -> dict:
        """Return the user's profile, redacted unless research consent is granted."""
        user = self._users.require_by_id(user_id)
        email = user.get("email")
        profile = self._profiles.get(email) if email else None
        if profile is None:
            return {
                "user_id": email or user_id,
                "has_profile": False,
                "profile_mode": "general",
                "data": None,
            }

        can_show = (
            self._consent.has_research_consent(email) or profile.get("profile_mode") == "general"
        )
        return {
            "user_id": email or user_id,
            "has_profile": True,
            "profile_mode": profile.get("profile_mode", "general"),
            "research_data_consent": self._consent.has_research_consent(email),
            "data": {
                "preferred_name": profile.get("preferred_name"),
                **{
                    field: (profile.get(field) if can_show else None)
                    for field in (
                        "age_range",
                        "gender_identity",
                        "pronouns",
                        "primary_language",
                        "disability",
                        "immigration_status",
                        "indigenous_identity",
                        "education_level",
                        "literacy_comfort_ai",
                    )
                },
            },
            "redacted": not can_show,
        }

    def get_consent(self, user_id: str) -> dict:
        user = self._users.require_by_id(user_id)
        email = user.get("email")
        consent = self._consent.get(email) if email else None
        if consent is None:
            return {"user_id": user_id, "has_consented": False}
        return {
            "user_id": user_id,
            "has_consented": consent.get("has_consented", False),
            "profile_mode": consent.get("profile_mode", "general"),
            "research_data_consent": consent.get("research_data_consent", False),
            "consented_at": consent.get("consented_at"),
            "updated_at": consent.get("updated_at"),
        }

    def list_conversations(self, user_id: str, page: int = 1, limit: int = 20) -> dict:
        """List a user's conversations; requires research-data consent."""
        user = self._users.require_by_id(user_id)
        email = user.get("email")
        if not (email and self._consent.has_research_consent(email)):
            raise ForbiddenError(
                "User has not granted research data consent — conversations are private."
            )

        items = [
            {
                "id": str(conversation["_id"]),
                "title": conversation.get("title", "Untitled"),
                "profile_key": conversation.get("profile_key"),
                "message_count": self._messages.count_for_conversation(str(conversation["_id"])),
                "created_at": conversation.get("created_at"),
                "updated_at": conversation.get("updated_at"),
            }
            for conversation in self._conversations.list_for_user(email, page, limit)
        ]
        return {
            "conversations": items,
            "total": self._conversations.count_for_user(email),
            "page": page,
            "limit": limit,
        }

    def get_activity(self, user_id: str) -> dict:
        user = self._users.require_by_id(user_id)
        email = user.get("email")
        if not email:
            return {
                "conversation_count": 0,
                "message_count": 0,
                "last_conversation_at": None,
                "last_message_at": None,
            }

        last_conversation = self._conversations.last_for_user(email)
        last_message = (
            self._messages.last_for_conversation(str(last_conversation["_id"]))
            if last_conversation
            else None
        )
        return {
            "conversation_count": self._conversations.count_for_user(email),
            "message_count": self._conversations.sum_message_count_for_user(email),
            "last_conversation_at": (last_conversation or {}).get("updated_at"),
            "last_message_at": (last_message or {}).get("created_at"),
        }

    # ── Statistics ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Aggregate platform-wide user statistics."""
        return {
            "total_users": self._users.count(),
            "admin_users": self._users.count({"role": "admin"}),
            "verified_users": self._users.count({"verified": True}),
            "onboarding_completed": self._users.count({"onboarding_completed": True}),
            "users_with_profiles": self._profiles.count(),
            "full_privacy_mode": self._profiles.count({"profile_mode": "full"}),
            "consent_granted": self._consent.count({"has_consented": True}),
            "research_data_consent": self._consent.count({"research_data_consent": True}),
            "total_conversations": self._conversations.count_all(),
            "total_messages": self._messages.count_all(),
        }

    # ── Mutations ─────────────────────────────────────────────────────────────

    def update_user(self, user_id: str, changes: dict) -> dict:
        """Apply an admin edit to a user and return the enriched result."""
        self._users.require_by_id(user_id)

        fields: dict = {}
        if changes.get("name") is not None:
            fields["name"] = changes["name"]
        if changes.get("password") is not None:
            fields["hashed_password"] = hash_password(changes["password"])
        if changes.get("role") is not None:
            if changes["role"] not in _ROLE_CHOICES:
                raise ValidationError("role must be 'user' or 'admin'")
            fields["role"] = changes["role"]
        if changes.get("verified") is not None:
            fields["verified"] = changes["verified"]
        if not fields:
            raise ValidationError("Nothing to update")

        self._users.update_by_id(user_id, fields)
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> None:
        """Delete a user and every record owned by them."""
        user = self._users.require_by_id(user_id)
        email = user.get("email")
        self._users.delete_by_id(user_id)
        if not email:
            return

        self._profiles.delete(email)
        self._consent.delete(email)
        conversation_ids = self._conversations.ids_for_user(email)
        if conversation_ids:
            self._messages.delete_for_conversations(conversation_ids)
        self._conversations.delete_for_user(email)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _enrich(self, user: dict) -> dict:
        """Attach profile, consent and activity aggregates to a serialised user."""
        email = user.get("email")
        if not email:
            return user

        profile = self._profiles.get(email)
        consent = self._consent.get(email)
        return {
            **user,
            "has_profile": profile is not None,
            "profile_mode": (profile or {}).get("profile_mode", "general"),
            "has_consent": consent is not None,
            "research_data_consent": (consent or {}).get("research_data_consent", False),
            "conversation_count": self._conversations.count_for_user(email),
            "message_count": self._conversations.sum_message_count_for_user(email),
        }
