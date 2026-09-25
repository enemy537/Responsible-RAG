"""Integration tests against a live dataset.

These exercise the refactored data paths against **real payloads**, which is the
guard for the existing production data: field names, document shapes, and
enumerations must keep working without any migration.

Skipped automatically when the backing services are unreachable, so the normal
`pytest` run stays self-contained.

Safety rules:
  * Qdrant is only **read** from (one test rewrites a field with its own value).
  * MongoDB writes go to a dedicated throwaway database that is dropped in
    teardown; no pre-existing database is modified.

Environment overrides:
  TEST_QDRANT_URL   default http://127.0.0.1:6333
  TEST_MONGO_URI    default mongodb://127.0.0.1:27017/responsible_rag_refactor_test
"""

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

pymongo = pytest.importorskip("pymongo")
httpx = pytest.importorskip("httpx")
ObjectId = pytest.importorskip("bson").ObjectId
pytest.importorskip("langchain_core")

from langchain_core.embeddings import Embeddings  # noqa: E402

QDRANT_URL = os.environ.get("TEST_QDRANT_URL", "http://127.0.0.1:6333")
MONGO_URI = os.environ.get(
    "TEST_MONGO_URI", "mongodb://127.0.0.1:27017/responsible_rag_refactor_test"
)

EMBEDDING_DIM = 1024
EMAIL = "legacy.user@example.com"
LEGACY_CONVERSATION_ID = "64f0c0ffee1234567890abcd"


def _qdrant_up() -> bool:
    try:
        return httpx.get(f"{QDRANT_URL}/collections", timeout=3.0).status_code == 200
    except Exception:
        return False


def _mongo_up() -> bool:
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return True
    except Exception:
        return False


requires_qdrant = pytest.mark.skipif(not _qdrant_up(), reason="Qdrant not reachable")
requires_mongo = pytest.mark.skipif(not _mongo_up(), reason="MongoDB not reachable")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# Qdrant — real knowledge base (read-only)
# ═══════════════════════════════════════════════════════════════════════════════

class _StubEmbeddings(Embeddings):
    """Offline embeddings: enough to open the store, never used for search."""

    def embed_documents(self, texts):
        return [[0.001] * EMBEDDING_DIM for _ in texts]

    def embed_query(self, text):
        return [0.001] * EMBEDDING_DIM


@pytest.fixture(scope="module")
def qdrant_settings():
    from src.core.config import Settings

    host = QDRANT_URL.split("//", 1)[-1]
    hostname, _, port = host.partition(":")
    return Settings(qdrant_host=hostname or "127.0.0.1", qdrant_port=int(port or 6333))


@pytest.fixture(scope="module")
def knowledge_base(qdrant_settings):
    from src.core.vector_store import KnowledgeBase

    return KnowledgeBase(qdrant_settings, _StubEmbeddings())


@requires_qdrant
class TestQdrantDataset:
    def test_collection_matches_expected_shape(self, knowledge_base):
        """The KB collection must look exactly like what the code expects."""
        collection = knowledge_base._client.get_collection(
            knowledge_base._collection_name
        )
        assert collection.config.params.vectors.size == EMBEDDING_DIM
        assert "langchain-sparse" in (collection.config.params.sparse_vectors or {})

    def test_list_sources_returns_real_sources(self, knowledge_base):
        sources = knowledge_base.list_sources()

        assert sources, "expected at least one source in the knowledge base"
        assert all(source.get("source_id") for source in sources)

    def test_get_source_round_trips_metadata(self, knowledge_base):
        source = knowledge_base.list_sources()[0]
        source_id = source["source_id"]

        fetched = knowledge_base.get_source(source_id)

        assert fetched is not None
        assert fetched["source_id"] == source_id
        assert knowledge_base.chunk_count(source_id) > 0

    def test_metadata_updates_stay_under_metadata_key(self, knowledge_base):
        """Regression guard: payload must keep the nested `metadata` layout."""
        source = knowledge_base.list_sources()[0]
        source_id = source["source_id"]
        title = source.get("title", "")

        assert knowledge_base.update_source_metadata(source_id, {"title": title}) is True
        assert knowledge_base.get_source(source_id)["title"] == title

    def test_source_service_reads_real_sources(self, knowledge_base):
        from src.api.services.source_service import SourceService

        service = SourceService(knowledge_base=knowledge_base)
        sources = service.list_sources()

        assert sources
        assert all(source.get("status") for source in sources)
        stats = service.get_stats()
        assert stats["total_sources"] >= 1
        assert stats["indexed_sources"] == stats["total_sources"]


@requires_qdrant
class TestCitationMappingOnRealPayload:
    def test_real_chunks_map_to_citations(self):
        """Feed real Qdrant payloads through the new citation mapper."""
        from langchain_core.documents import Document

        from src.api.mappers.chat import build_citations
        from src.core.rag_chain import _extract_source_metadata

        resp = httpx.post(
            f"{QDRANT_URL}/collections/rag_kb_collection/points/scroll",
            json={"limit": 5, "with_payload": True},
            timeout=15.0,
        )
        points = resp.json()["result"]["points"]
        assert points, "expected points in the knowledge base collection"

        documents = [
            Document(
                page_content=(point.get("payload") or {}).get("page_content", ""),
                metadata=(point.get("payload") or {}).get("metadata", {}),
            )
            for point in points
        ]

        citations = build_citations(_extract_source_metadata(documents))

        assert citations, "real chunks must produce citations"
        assert [c.number for c in citations] == list(range(1, len(citations) + 1))
        assert citations[0].source_id
        assert citations[0].source_title
        assert citations[0].excerpt == documents[0].page_content[:300]


def test_upload_policy():
    from src.api.services.source_service import SourceService

    service = SourceService()

    assert service.is_supported_file("paper.pdf") is True
    assert service.is_supported_file("talk.MP3") is True
    assert service.is_supported_file("notes.markdown") is True
    assert service.is_supported_file("archive.zip") is False
    assert service.source_type_for("paper.pdf") == "pdf"
    assert service.source_type_for("talk.mp3") == "audio"
    assert service.source_type_for("notes.txt") == "text"
    assert service.size_limit_for("pdf") == 100 * 1024 * 1024
    assert service.size_limit_for("webpage") == 50 * 1024 * 1024


# ═══════════════════════════════════════════════════════════════════════════════
# MongoDB — legacy document shapes round-trip through the new repositories
# ═══════════════════════════════════════════════════════════════════════════════

CONVERSATION_KEYS = {
    "user_id",
    "title",
    "profile_key",
    "message_count",
    "last_message",
    "last_message_at",
    "created_at",
    "updated_at",
    "memory",
}

MESSAGE_KEYS = {
    "conversation_id",
    "role",
    "content",
    "citations",
    "is_streaming",
    "created_at",
}


class _StubMemoryAgent:
    """Avoids LLM calls while keeping the memory-update contract."""

    def summarise(self, existing_summary: str, transcript: str) -> str:
        return "updated summary"

    def extract_facts(self, transcript: str) -> list[str]:
        return ["Goal: verify data compatibility"]


def _chat_service(db, **kwargs):
    from src.api.db.repositories import (
        ConversationRepository,
        MessageRepository,
        ProfileRepository,
    )
    from src.api.services.chat_service import ChatService

    return ChatService(
        conversations=ConversationRepository(db),
        messages=MessageRepository(db),
        profiles=ProfileRepository(db),
        memory_agent=_StubMemoryAgent(),
        **kwargs,
    )


def _user_service(db):
    from src.api.db.repositories import (
        ConsentRepository,
        ConversationRepository,
        MessageRepository,
        ProfileRepository,
        UserRepository,
    )
    from src.api.services.user_service import UserService

    return UserService(
        users=UserRepository(db),
        profiles=ProfileRepository(db),
        consent=ConsentRepository(db),
        conversations=ConversationRepository(db),
        messages=MessageRepository(db),
    )


@pytest.fixture(scope="module")
def mongo_db():
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client.get_default_database()
    assert db.name.endswith("_test"), (
        "refusing to run: the integration database name must end in '_test'"
    )
    client.drop_database(db.name)
    try:
        yield db
    finally:
        client.drop_database(db.name)
        client.close()


def _seed_legacy_documents(db):
    """Insert documents using the shapes already stored in production."""
    timestamp = now_iso()
    user_id = db["users"].insert_one(
        {
            "email": EMAIL,
            "name": "Legacy User",
            "provider": "email",
            "role": "user",
            "hashed_password": "x",
            "verified": True,
            "onboarding_completed": True,
            "created_at": timestamp,
            "google_id": None,
        }
    ).inserted_id

    db["profiles"].insert_one(
        {
            "user_id": EMAIL,
            "preferred_name": "Legacy",
            "age_range": "65_plus",
            "gender_identity": ["woman"],
            "pronouns": "she/her",
            "primary_language": "English",
            "disability": ["none"],
            "immigration_status": "citizen",
            "indigenous_identity": "non_indigenous",
            "education_level": "high_school",
            "literacy_comfort_ai": 2,
            "profile_mode": "full",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )

    db["consent"].insert_one(
        {
            "user_id": EMAIL,
            "profile_mode": "full",
            "research_data_consent": True,
            "has_consented": True,
            "consented_at": timestamp,
            "updated_at": timestamp,
        }
    )

    db["conversations"].insert_one(
        {
            "_id": ObjectId(LEGACY_CONVERSATION_ID),
            "user_id": EMAIL,
            "title": "Legacy conversation",
            "profile_key": "senior",
            "message_count": 2,
            "last_message": "an older answer",
            "last_message_at": timestamp,
            "created_at": timestamp,
            "updated_at": timestamp,
            "memory": {
                "enabled": True,
                "summary": "Existing summary",
                "facts": ["Preference: plain language"],
                "recent_turns": [],
                "last_refreshed_at": timestamp,
                "last_refreshed_turn_count": 2,
            },
        }
    )

    db["messages"].insert_many(
        [
            {
                "conversation_id": LEGACY_CONVERSATION_ID,
                "role": "user",
                "content": "What is predictive policing?",
                "citations": [],
                "is_streaming": False,
                "created_at": timestamp,
            },
            {
                "conversation_id": LEGACY_CONVERSATION_ID,
                "role": "assistant",
                "content": "It is ...",
                "citations": [
                    {
                        "id": "cit-0",
                        "source_id": "src-1",
                        "source_title": "A paper",
                        "source_type": "pdf",
                        "authors": ["A. Author"],
                        "publication_date": None,
                        "publisher": None,
                        "url": "",
                        "doi": "",
                        "language": None,
                        "description": None,
                        "tags": [],
                        "content_sensitivity": "low",
                        "excerpt": "excerpt",
                        "number": 1,
                    }
                ],
                "is_streaming": False,
                "created_at": _later(timestamp),
            },
        ]
    )
    return user_id


def _later(timestamp: str) -> str:
    """Return an ISO timestamp one second after *timestamp*."""
    return (datetime.fromisoformat(timestamp) + timedelta(seconds=1)).isoformat()


@requires_mongo
class TestMongoLegacyData:
    def test_repositories_read_legacy_documents(self, mongo_db):
        from src.api.db.repositories import (
            ConsentRepository,
            ConversationRepository,
            MessageRepository,
            ProfileRepository,
            UserRepository,
        )

        _seed_legacy_documents(mongo_db)

        users = UserRepository(mongo_db)
        assert users.get_by_email(EMAIL, provider="email") is not None
        assert len(users.search("legacy")) == 1

        assert ProfileRepository(mongo_db).get(EMAIL)["age_range"] == "65_plus"
        assert ConsentRepository(mongo_db).has_research_consent(EMAIL) is True

        conversations = ConversationRepository(mongo_db)
        assert conversations.count_for_user(EMAIL) == 1
        assert conversations.sum_message_count_for_user(EMAIL) == 2
        assert conversations.ids_for_user(EMAIL) == [LEGACY_CONVERSATION_ID]

        messages = MessageRepository(mongo_db)
        assert messages.count_for_conversation(LEGACY_CONVERSATION_ID) == 2
        assert messages.last_for_conversation(LEGACY_CONVERSATION_ID)["role"] == "assistant"

    def test_chat_service_renders_legacy_conversation(self, mongo_db):
        service = _chat_service(mongo_db)

        listing = service.list_conversations(EMAIL)
        assert listing["total"] == 1
        assert listing["conversations"][0]["id"] == LEGACY_CONVERSATION_ID
        assert listing["conversations"][0]["message_count"] == 2

        conversation = service.get_conversation(EMAIL, LEGACY_CONVERSATION_ID)
        assert conversation["title"] == "Legacy conversation"
        assert len(conversation["messages"]) == 2
        assert conversation["messages"][1]["citations"][0]["source_id"] == "src-1"

        messages = service.list_messages(EMAIL, LEGACY_CONVERSATION_ID)
        assert [message["role"] for message in messages] == ["user", "assistant"]

    def test_turn_writes_preserve_document_shape(self, mongo_db):
        service = _chat_service(mongo_db)

        turn = service.begin_turn(
            EMAIL,
            question="A follow-up question",
            profile_key="senior",
            conversation_id=LEGACY_CONVERSATION_ID,
        )
        assert turn.prior_message_count == 2

        service.finish_turn(
            turn,
            question="A follow-up question",
            answer="A follow-up answer",
            citations=[],
        )

        conversation = mongo_db["conversations"].find_one(
            {"_id": ObjectId(LEGACY_CONVERSATION_ID)}
        )
        assert set(conversation) >= CONVERSATION_KEYS
        assert conversation["message_count"] == 4
        assert conversation["last_message"] == "A follow-up answer"
        # The 2000-token window was not exceeded, so the summary is untouched.
        assert conversation["memory"]["summary"] == "Existing summary"
        assert conversation["memory"]["window_tokens"] > 0
        assert len(conversation["memory"]["recent_turns"]) == 4

        stored = list(mongo_db["messages"].find({"conversation_id": LEGACY_CONVERSATION_ID}))
        assert len(stored) == 4
        assert all(set(message) >= MESSAGE_KEYS for message in stored)

    def test_window_overflow_summarises_and_rolls(self, mongo_db):
        """A tiny window forces the overflow path against real MongoDB."""
        service = _chat_service(mongo_db, memory_window_tokens=1, history_limit=20)

        turn = service.begin_turn(
            EMAIL,
            question="A question that overflows the window",
            profile_key=None,
            conversation_id=LEGACY_CONVERSATION_ID,
        )
        service.finish_turn(
            turn,
            question="A question that overflows the window",
            answer="A rolling answer",
            citations=[],
        )

        conversation = mongo_db["conversations"].find_one(
            {"_id": ObjectId(LEGACY_CONVERSATION_ID)}
        )
        memory = conversation["memory"]
        assert memory["summary"] == "updated summary"
        assert memory["facts"]
        assert memory["last_refreshed_turn_count"] == 6
        assert len(memory["recent_turns"]) < 6

    def test_begin_turn_creates_legacy_shaped_conversation(self, mongo_db):
        service = _chat_service(mongo_db)

        turn = service.begin_turn(
            EMAIL,
            question="Brand new question",
            profile_key="general",
            conversation_id=None,
        )
        service.finish_turn(
            turn, question="Brand new question", answer="Answer", citations=[]
        )

        created = mongo_db["conversations"].find_one(
            {"_id": ObjectId(turn.conversation_id)}
        )
        assert set(created) >= CONVERSATION_KEYS
        assert created["memory"]["enabled"] is True
        assert created["message_count"] == 2

    def test_user_service_enriches_legacy_user(self, mongo_db):
        user_id = str(mongo_db["users"].find_one({"email": EMAIL})["_id"])
        users = _user_service(mongo_db)

        listed = users.list_users()
        assert len(listed) == 1
        assert listed[0]["has_profile"] is True
        assert listed[0]["has_consent"] is True
        assert listed[0]["conversation_count"] >= 1
        assert "hashed_password" not in listed[0]

        assert users.get_user(user_id)["email"] == EMAIL

        profile = users.get_profile(user_id)
        assert profile["redacted"] is False
        assert profile["data"]["education_level"] == "high_school"

        assert users.get_activity(user_id)["conversation_count"] >= 1

        stats = users.stats()
        assert stats["total_users"] == 1
        assert stats["users_with_profiles"] == 1

        updated = users.update_user(user_id, {"name": "Renamed User"})
        assert updated["name"] == "Renamed User"

    def test_profile_prompt_mapping_uses_real_profile(self, mongo_db):
        from src.api.mappers.profile import adaptation_fields, count_provided_fields
        from src.core.profile_prompt import build_profile_prompt, map_profile_to_generation

        profile = mongo_db["profiles"].find_one({"user_id": EMAIL})
        mapped = map_profile_to_generation(profile)

        assert mapped["age_group"] == "Senior (65+ years)"
        assert mapped["education_level"] == "High school diploma"
        assert mapped["citizen_status"] == "Canadian citizen"
        assert mapped["disability_status"] == "No disclosed disability"

        assert build_profile_prompt(None, None, "q") == build_profile_prompt(
            {"profile_mode": "general"}, None, "q"
        )

        fields = adaptation_fields({"age_group": "teen"})
        age_field = next(field for field in fields if field["field"] == "age_group")
        assert age_field["value"] == "teen"
        assert age_field["evidence_found"] is True
        assert count_provided_fields({"age_group": "teen"}) == 1

    def test_delete_user_removes_all_related_data(self, mongo_db):
        extra_email = "delete.me@example.com"
        extra_id = mongo_db["users"].insert_one(
            {
                "email": extra_email,
                "name": "Delete Me",
                "provider": "email",
                "role": "user",
                "hashed_password": "x",
                "verified": True,
                "onboarding_completed": True,
                "created_at": now_iso(),
                "google_id": None,
            }
        ).inserted_id
        mongo_db["profiles"].insert_one({"user_id": extra_email})
        mongo_db["consent"].insert_one({"user_id": extra_email})
        conversation_id = mongo_db["conversations"].insert_one(
            {"user_id": extra_email, "title": "temp", "message_count": 1}
        ).inserted_id
        mongo_db["messages"].insert_one(
            {"conversation_id": str(conversation_id), "role": "user"}
        )

        _user_service(mongo_db).delete_user(str(extra_id))

        assert mongo_db["users"].find_one({"_id": extra_id}) is None
        assert mongo_db["profiles"].find_one({"user_id": extra_email}) is None
        assert mongo_db["consent"].find_one({"user_id": extra_email}) is None
        assert mongo_db["conversations"].find_one({"user_id": extra_email}) is None
        assert mongo_db["messages"].find_one({"conversation_id": str(conversation_id)}) is None
