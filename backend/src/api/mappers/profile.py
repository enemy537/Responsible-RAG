"""Mapping between Mongo documents and profile/consent API payloads."""

from src.core.profiles import STANDARD_PROFILE

# Stored field -> value returned when the field is absent.
_PROFILE_FIELD_DEFAULTS: dict[str, object] = {
    "preferred_name": "",
    "age_range": None,
    "gender_identity": [],
    "pronouns": None,
    "primary_language": None,
    "disability": [],
    "immigration_status": None,
    "indigenous_identity": None,
    "education_level": None,
    "literacy_comfort_ai": None,
}

# Personalisation dimensions exposed to the onboarding review UI.
ADAPTATION_LABELS: dict[str, str] = {
    "sex_at_birth": "Sex at Birth",
    "gender": "Gender Identity",
    "age_group": "Age Group",
    "primary_language": "Primary Language",
    "education_level": "Education Level",
    "citizen_status": "Citizen Status",
    "indigenous_status": "Indigenous Status",
    "disability_status": "Disability Status",
}


def _default_for(value: object) -> object:
    return list(value) if isinstance(value, list) else value


def profile_to_response(doc: dict) -> dict:
    """Serialise a stored profile document."""
    response: dict = {
        "id": str(doc["_id"]),
        "user_id": doc["user_id"],
        "profile_mode": doc.get("profile_mode", "general"),
        "created_at": doc.get("created_at", ""),
        "updated_at": doc.get("updated_at", ""),
    }
    for field, default in _PROFILE_FIELD_DEFAULTS.items():
        response[field] = doc.get(field, _default_for(default))
    return response


def consent_to_response(doc: dict) -> dict:
    """Serialise a stored consent document."""
    return {
        "id": str(doc["_id"]),
        "user_id": doc["user_id"],
        "profile_mode": doc.get("profile_mode", "general"),
        "research_data_consent": doc.get("research_data_consent", False),
        # Absent on records created before the flag existed -> storage allowed.
        "chat_history_consent": doc.get("chat_history_consent", True),
        "has_consented": doc.get("has_consented", False),
        "consented_at": doc.get("consented_at"),
        "updated_at": doc.get("updated_at"),
    }


def _has_custom_value(field_key: str, value: object) -> bool:
    return bool(str(value).strip()) and value != STANDARD_PROFILE.get(field_key, "")


def count_provided_fields(user_profile: dict[str, str] | None) -> int:
    """Count fields whose value departs from the standard default."""
    return sum(1 for key, value in (user_profile or {}).items() if _has_custom_value(key, value))


def adaptation_fields(user_profile: dict[str, str] | None) -> list[dict]:
    """Describe each personalisation dimension for the review UI."""
    profile = user_profile or {}
    fields: list[dict] = []
    for field_key, label in ADAPTATION_LABELS.items():
        value = profile.get(field_key, "")
        fields.append(
            {
                "field": field_key,
                "label": label,
                "value": (str(value).strip() if value else STANDARD_PROFILE.get(field_key, "")),
                "evidence_found": _has_custom_value(field_key, value),
            }
        )
    return fields
