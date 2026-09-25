"""Tests for the token-bounded conversation window and its rolling summary."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from src.core.memory import (
    build_memory_context,
    init_memory,
    roll_window,
    update_memory_window,
)


class StubAgent:
    """Records what it was asked to summarise, without calling an LLM."""

    def __init__(self) -> None:
        self.summarised: list[str] = []
        self.fact_calls: list[str] = []

    def summarise(self, existing_summary: str, transcript: str) -> str:
        self.summarised.append(transcript)
        return f"{existing_summary}|folded"

    def extract_facts(self, transcript: str) -> list[str]:
        self.fact_calls.append(transcript)
        return ["Goal: from overflow"]


def turns(count: int, words: int = 20) -> list[dict]:
    """Build *count* alternating turns of roughly *words* tokens each."""
    body = " ".join(["word"] * words)
    return [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"{body} #{index}"}
        for index in range(count)
    ]


class TestRollWindow:
    def test_short_history_is_kept_entirely(self):
        kept, dropped, tokens = roll_window(turns(2), max_tokens=2000)

        assert len(kept) == 2
        assert dropped == []
        assert tokens > 0

    def test_long_history_keeps_a_suffix_and_drops_the_front(self):
        kept, dropped, tokens = roll_window(turns(200), max_tokens=500)

        assert kept, "the window must never be empty"
        assert dropped, "overflow must be reported for summarisation"
        assert len(kept) + len(dropped) == 200
        assert tokens <= 500 + 30, "window should respect the token budget"
        # Window is the newest messages, overflow is the oldest.
        assert dropped[0]["content"].endswith("#0")
        assert kept[-1]["content"].endswith("#199")

    def test_single_oversized_message_is_never_lost(self):
        huge = [{"role": "user", "content": " ".join(["token"] * 5000)}]

        kept, dropped, _ = roll_window(huge, max_tokens=100)

        assert kept == huge
        assert dropped == []

    def test_empty_history(self):
        assert roll_window([], max_tokens=100) == ([], [], 0)


class TestUpdateMemoryWindow:
    def test_no_overflow_does_not_call_the_summariser(self):
        agent = StubAgent()
        memory = init_memory("2026-01-01T00:00:00+00:00")

        updated, context = update_memory_window(
            turns(2), memory, agent=agent, now="2026-01-01T00:01:00+00:00",
            total_turn_count=2, max_tokens=2000,
        )

        assert agent.summarised == []
        assert updated["summary"] == ""
        assert updated["window_tokens"] > 0
        assert len(updated["recent_turns"]) == 2
        assert "Recent conversation" in context

    def test_overflow_folds_into_summary_and_facts(self):
        agent = StubAgent()
        memory = init_memory("2026-01-01T00:00:00+00:00")

        updated, _ = update_memory_window(
            turns(200), memory, agent=agent, now="2026-01-01T00:05:00+00:00",
            total_turn_count=200, max_tokens=500,
        )

        assert len(agent.summarised) == 1
        assert agent.summarised[0].startswith("User:")
        assert updated["summary"] == "|folded"
        assert "Goal: from overflow" in updated["facts"]
        assert updated["last_refreshed_turn_count"] == 200
        assert updated["last_refreshed_at"] == "2026-01-01T00:05:00+00:00"
        assert len(updated["recent_turns"]) < 200

    def test_context_includes_summary_facts_and_window(self):
        memory = {
            **init_memory("now"),
            "summary": "User is researching policing.",
            "facts": ["Preference: plain language"],
        }

        context = build_memory_context(memory, [{"role": "user", "content": "Hi"}])

        assert "Summary:" in context
        assert "Preference: plain language" in context
        assert "User: Hi" in context

    def test_disabled_memory_produces_no_context(self):
        memory = {**init_memory("now"), "enabled": False}

        assert build_memory_context(memory, [{"role": "user", "content": "Hi"}]) == ""

    def test_legacy_memory_document_still_works(self):
        """Records written before the token window existed must keep working."""
        legacy = {
            "enabled": True,
            "summary": "old summary",
            "facts": ["Goal: legacy"],
            "recent_turns": [{"role": "user", "content": "old question"}],
            "last_refreshed_at": "2026-01-01T00:00:00+00:00",
            "last_refreshed_turn_count": 4,
        }

        updated, context = update_memory_window(
            turns(2), legacy, agent=StubAgent(), now="2026-02-01T00:00:00+00:00",
            total_turn_count=6, max_tokens=2000,
        )

        assert updated["window_tokens"] > 0
        assert updated["summary"] == "old summary"
        assert "old summary" in context
        assert "Goal: legacy" in context
