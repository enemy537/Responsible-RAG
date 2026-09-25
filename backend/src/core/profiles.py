"""
profiles.py — Audience-specific RAG system prompts
====================================================
:class:`RAGPopulation` is a :class:`StrEnum` where each member **is** the
system prompt injected into the LLM chain before the retrieved context.
Selecting a profile shapes the assistant's vocabulary, tone, safety
behaviours, and prioritisation of information categories.

Adding a new profile
--------------------
1. Add a new member whose value is the full system-prompt string.
2. Register its academic citation in :meth:`research_citation_note`.
3. The UI and API will automatically pick it up via :meth:`get_valid_keys`.

Source validation date: June 2026
"""

import logging

from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Dynamic profile prompt template
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIC_PROFILE_TEMPLATE = """You are a knowledgeable, respectful Canadian educational assistant. Your purpose is to provide clear, accurate, and culturally responsive information to diverse users across Canada. You adapt your communication style to meet each user's needs while maintaining factual accuracy and inclusive language.

=== USER DEMOGRAPHIC PROFILE ===
Sex at birth: {sex_at_birth}
Gender: {gender}
Age group: {age_group}
Primary language: {primary_language}
Education level: {education_level}
Citizen status: {citizen_status}
Indigenous status: {indigenous_status}
Disability: {disability_status}

=== COMMUNICATION ADAPTATION RULES ===

[AGE GROUP: {age_group}]
{age_group_rules}

[LANGUAGE: {primary_language}]
{language_rules}

[EDUCATION: {education_level}]
{education_rules}

[INDIGENOUS STATUS: {indigenous_status}]
{indigenous_rules}

[DISABILITY: {disability_status}]
{disability_rules}

[GENDER: {gender}]
{gender_rules}

[CITIZEN STATUS: {citizen_status}]
{citizen_rules}

=== RETRIEVED CONTEXT ===
{retrieved_documents}

=== TASK ===
{user_query}

Respond following the communication adaptation rules above. Base your response on the retrieved context. Use Canadian English spelling. If the topic involves Indigenous peoples, prioritize Indigenous voices and acknowledge the diversity of First Nations, Inuit, and Metis perspectives."""

# ── Standard defaults when a field is not provided ────────────────────────────
STANDARD_PROFILE: dict[str, str] = {
    "sex_at_birth": "Prefer not to say",
    "gender": "Not specified — use gender-neutral language throughout",
    "age_group": "Adult (18–64 years)",
    "primary_language": "English",
    "education_level": "Some post-secondary education",
    "citizen_status": "Canadian citizen / Permanent resident",
    "indigenous_status": "Non-Indigenous",
    "disability_status": "No disclosed disability",
}

# ── Default adaptation rules for standard profile ────────────────────────────
_STANDARD_RULES: dict[str, str] = {
    "age_group_rules": (
        "Use clear, direct language suitable for a general adult audience. "
        "Avoid patronising or overly complex explanations."
    ),
    "language_rules": (
        "Use plain English. Define any technical terms on first use. "
        "Avoid idioms or culturally specific references without explanation."
    ),
    "education_rules": (
        "Assume general literacy. Explain specialised terms but avoid "
        "oversimplifying core concepts."
    ),
    "indigenous_rules": (
        "No specific Indigenous considerations indicated. If the topic "
        "relates to Indigenous peoples, include a note that diverse "
        "First Nations, Inuit, and Métis perspectives exist."
    ),
    "disability_rules": (
        "No specific disability considerations indicated. Use clear, "
        "accessible formatting. Offer alternative formats on request."
    ),
    "gender_rules": (
        "Use gender-neutral language unless the user's gender is known. "
        "Use 'they/them' as the default pronoun."
    ),
    "citizen_rules": (
        "No specific immigration or citizenship considerations indicated. "
        "Provide general Canadian context."
    ),
}

# ── RAG queries to retrieve relevant evidence for each demographic field ─────
_FIELD_QUERIES: dict[str, str] = {
    "sex_at_birth": "sex at birth biological differences health communication",
    "gender": "gender identity diversity inclusion two-spirit LGBTQ communication",
    "age_group": "age developmental stages older adults youth communication",
    "primary_language": "language barriers English proficiency newcomers immigrants healthcare access",
    "education_level": "health literacy education level plain language communication",
    "citizen_status": "immigrant refugee newcomer migrant settlement Canada healthcare navigation",
    "indigenous_status": "First Nations Inuit Metis Indigenous data sovereignty OCAP TRC",
    "disability_status": "disability accessibility inclusive communication accommodations",
}


# ═══════════════════════════════════════════════════════════════════════════════
# ProfileAugmenter — RAG-powered demographic prompt builder
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileAugmenter:
    """
    Builds a personalised system prompt by querying the profiles Qdrant
    collection for evidence about each demographic field.

    Usage
    -----
        augmenter = ProfileAugmenter(embedding_function)
        prompt = augmenter.build_prompt(
            user_profile={"gender": "non_binary", "age_group": "teen"},
            user_query="What are my rights at school?",
        )
        # prompt is a fully rendered DYNAMIC_PROFILE_TEMPLATE string
    """

    def __init__(self, embedding_function) -> None:
        self._embedding_function = embedding_function
        self._retriever: any | None = None
        # Track source titles used in the last build_prompt() call
        self._last_source_titles: set[str] = set()

    @property
    def last_source_titles(self) -> list[str]:
        """Return sorted source titles used in the most recent build_prompt()."""
        return sorted(self._last_source_titles)

    # ── Lazy retriever ────────────────────────────────────────────────────────

    def _get_retriever(self, k: int = 5):
        """Lazy-load the profiles Qdrant collection and return a retriever."""
        if self._retriever is not None:
            return self._retriever

        from src.core.config import get_settings

        settings = get_settings()

        client = QdrantClient(
            url=f"http://{settings.qdrant_host}:{settings.qdrant_port}",
            timeout=120,
        )
        collection_name = settings.qdrant_profiles_collection_name

        # Check collection exists — if not, warn and return None so the
        # application falls back to default profiles.
        collections = client.get_collections().collections
        existing = {c.name for c in collections}

        if collection_name not in existing:
            logger.warning(
                "Profiles Qdrant collection '%s' not found — "
                "using standard defaults only. "
                "Run 'python scripts/build_profiles_kb.py' first.",
                collection_name,
            )
            self._retriever = None
            return None

        logger.info("Using Qdrant collection '%s' for profiles", collection_name)
        from langchain_qdrant import (
            FastEmbedSparse,
            QdrantVectorStore,
            RetrievalMode,
        )

        # Connect with HYBRID (dense + sparse) retrieval.  The sparse
        # embedding model must match the one used in build_profiles_kb.py.
        vector_store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=self._embedding_function,
            sparse_embedding=FastEmbedSparse(
                model_name="Qdrant/bm42-all-minilm-l6-v2-attentions",
            ),
            retrieval_mode=RetrievalMode.HYBRID,
        )
        self._retriever = vector_store.as_retriever(search_kwargs={"k": k})
        return self._retriever

    # ── Evidence retrieval ────────────────────────────────────────────────────

    def _retrieve_for_field(self, field: str, query: str) -> str:
        """
        Query the profiles vector store for *field* and return a
        condensed evidence snippet, or an empty string if the store
        is unavailable or the query returns nothing useful.

        Populates ``_last_source_titles`` with unique source titles found.
        """
        retriever = self._get_retriever(k=3)
        if retriever is None:
            return ""

        try:
            docs = retriever.invoke(query)
            if not docs:
                return ""
            # Deduplicate by source and concatenate excerpts
            seen: set[str] = set()
            excerpts: list[str] = []
            for doc in docs:
                src = doc.metadata.get("source_id", doc.metadata.get("title", ""))
                if src in seen:
                    continue
                seen.add(src)
                source_label = doc.metadata.get("title", src)
                self._last_source_titles.add(source_label)
                content = doc.page_content[:500].strip()
                if content:
                    excerpts.append(f"[From: {source_label}]\n{content}")
            return "\n\n".join(excerpts[:3])
        except Exception as exc:
            logger.warning(
                "Evidence retrieval for field '%s' failed (query=%r): %s",
                field, query, exc,
            )
            return ""

    # ── Prompt builder ────────────────────────────────────────────────────────

    def build_prompt(
        self,
        user_profile: dict[str, str] | None = None,
        user_query: str = "",
        retrieved_documents: str = "",
    ) -> str:
        """
        Build a fully rendered ``DYNAMIC_PROFILE_TEMPLATE``.

        Parameters
        ----------
        user_profile:
            Demographic data from the user's onboarding (keys match
            ``STANDARD_PROFILE``).  Missing keys fall back to defaults.
        user_query:
            The user's question.
        retrieved_documents:
            Pre-formatted context from the main RAG retriever.

        Returns
        -------
        str
            Completed prompt ready to inject into the LLM chain.
        """
        # Reset source tracking for this call
        self._last_source_titles.clear()

        profile = dict(STANDARD_PROFILE)
        if user_profile:
            # Merge — user values override defaults
            for k in profile:
                v = user_profile.get(k)
                if v and str(v).strip():
                    profile[k] = str(v).strip()

        # ── Collect evidence from the profiles knowledge base ─────────────
        rules: dict[str, str] = dict(_STANDARD_RULES)
        field_to_rule = {
            "age_group": "age_group_rules",
            "primary_language": "language_rules",
            "education_level": "education_rules",
            "indigenous_status": "indigenous_rules",
            "disability_status": "disability_rules",
            "gender": "gender_rules",
            "citizen_status": "citizen_rules",
        }

        for field_key, rule_key in field_to_rule.items():
            field_value = profile[field_key]
            query = _FIELD_QUERIES.get(field_key, field_key)

            # Retrieve evidence about this population segment
            evidence = self._retrieve_for_field(field_key, query)

            # If we have evidence and the value is not the generic default,
            # enrich the rule with evidence; otherwise keep the standard rule
            if evidence and field_value != STANDARD_PROFILE.get(field_key, ""):
                rules[rule_key] = (
                    f"{_STANDARD_RULES[rule_key]}\n\n"
                    f"Research-backed guidance for '{field_value}':\n{evidence}"
                )

        # ── Render the template ──────────────────────────────────────────
        return DYNAMIC_PROFILE_TEMPLATE.format(
            sex_at_birth=profile["sex_at_birth"],
            gender=profile["gender"],
            age_group=profile["age_group"],
            primary_language=profile["primary_language"],
            education_level=profile["education_level"],
            citizen_status=profile["citizen_status"],
            indigenous_status=profile["indigenous_status"],
            disability_status=profile["disability_status"],
            age_group_rules=rules["age_group_rules"],
            language_rules=rules["language_rules"],
            education_rules=rules["education_rules"],
            indigenous_rules=rules["indigenous_rules"],
            disability_rules=rules["disability_rules"],
            gender_rules=rules["gender_rules"],
            citizen_rules=rules["citizen_rules"],
            retrieved_documents=retrieved_documents,
            user_query=user_query,
        )

