"""Mapping of stored user profiles to audience-aware prompt input."""

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, polite AI assistant. Answer the user's question "
    "concisely and clearly. Be respectful and direct."
)

AGE_MAP: dict[str, str] = {
    "under_18": "Youth (under 18)",
    "18_30": "Young adult (18–30 years)",
    "31_50": "Adult (31–50 years)",
    "51_65": "Middle-aged adult (51–65 years)",
    "65_plus": "Senior (65+ years)",
    "prefer_not_to_say": "Adult",
}

EDUCATION_MAP: dict[str, str] = {
    "no_formal": "No formal education",
    "high_school": "High school diploma",
    "some_college": "Some post-secondary education",
    "bachelors": "Bachelor's degree",
    "masters": "Master's degree",
    "doctoral": "Doctoral degree",
}

IMMIGRATION_MAP: dict[str, str] = {
    "citizen": "Canadian citizen",
    "permanent_resident": "Permanent resident",
    "temporary_resident": "Temporary resident / Visa holder",
    "refugee": "Refugee / Protected person",
    "undocumented": "Undocumented / No legal status",
}

INDIGENOUS_MAP: dict[str, str] = {
    "first_nations": "First Nations",
    "metis": "Métis",
    "inuit": "Inuit",
    "non_indigenous": "Non-Indigenous",
}


def _humanise(values: list[str]) -> str:
    """Render snake_case identifiers as a comma-separated human-readable list."""
    return ", ".join(value.replace("_", " ").title() for value in values if value)


def map_profile_to_generation(profile_doc: dict) -> dict[str, str]:
    """Translate stored profile fields into ProfileAugmenter inputs."""
    mapped: dict[str, str] = {}

    age = profile_doc.get("age_range")
    if age in AGE_MAP:
        mapped["age_group"] = AGE_MAP[age]

    genders = profile_doc.get("gender_identity") or []
    if genders:
        mapped["gender"] = _humanise(genders)

    if profile_doc.get("primary_language"):
        mapped["primary_language"] = profile_doc["primary_language"]

    education = profile_doc.get("education_level")
    if education in EDUCATION_MAP:
        mapped["education_level"] = EDUCATION_MAP[education]

    immigration = profile_doc.get("immigration_status")
    if immigration in IMMIGRATION_MAP:
        mapped["citizen_status"] = IMMIGRATION_MAP[immigration]

    indigenous = profile_doc.get("indigenous_identity")
    if indigenous in INDIGENOUS_MAP:
        mapped["indigenous_status"] = INDIGENOUS_MAP[indigenous]

    disabilities = profile_doc.get("disability") or []
    if disabilities:
        mapped["disability_status"] = (
            _humanise(disabilities) if "none" not in disabilities else "No disclosed disability"
        )

    return mapped


def build_profile_prompt(profile_doc: dict | None, generator, query: str) -> str:
    """Build the audience-aware system prompt, falling back to the default."""
    if not profile_doc or profile_doc.get("profile_mode") == "general":
        return DEFAULT_SYSTEM_PROMPT

    mapped = map_profile_to_generation(profile_doc)
    if not mapped:
        return DEFAULT_SYSTEM_PROMPT

    return generator.generate_prompt(user_profile=mapped, user_query=query)
