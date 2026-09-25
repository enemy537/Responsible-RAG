"""Conversation memory: a token-bounded window plus a rolling summary.

The window is measured in **tokens** using LangChain's :func:`trim_messages`.
Whenever messages fall out of the window they are folded into a running summary
and their user statements merged into the long-term fact list, so the model
keeps earlier context without the prompt growing without bound.

Stored memory document (unchanged keys, plus ``window_tokens``)::

    {
      "enabled": True,
      "summary": "...",
      "facts": ["Preference: plain language"],
      "recent_turns": [{"role": "...", "content": "..."}],
      "last_refreshed_at": "<iso>",
      "last_refreshed_turn_count": 12,
      "window_tokens": 812,
    }
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.core.config import get_settings

DEFAULT_WINDOW_TOKENS = 2000
MAX_FACTS = 10

_SUMMARY_PROMPT = ChatPromptTemplate.from_template(
    "You are a memory assistant that updates a concise session summary based "
    "on the user's conversation history. The summary should capture the user's "
    "goals, preferences, topics, and any stated health or disability details."
    "\n\nExisting summary:\n{existing_summary}\n\n"
    "Recent conversation:\n{recent_turns}\n\n"
    "Produce a short summary in 2-3 sentences. If the existing summary already "
    "captures the context, preserve it and only add new, relevant details."
)

_FACTS_PROMPT = ChatPromptTemplate.from_template(
    "You are a memory assistant that extracts explicit user facts from the "
    "conversation history. Only include user statements; do not include assistant text. "
    "Return a JSON array of strings only, with each string in one of these canonical forms: "
    '"Health condition: ..." , "Disability: ..." , "Location: ..." , "Preference: ..." , "Goal: ..." , "Topic: ..." .\n\n'
    "Conversation:\n{recent_turns}\n\n"
    "If there are no extractable facts, return an empty array: []."
)


class MemoryAgent:
    """Produces the rolling summary and the long-term fact list."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm = None
        self._summary_chain = None
        self._facts_chain = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = init_chat_model(
                model=self._settings.llm_model,
                temperature=self._settings.llm_temperature,
            )
        return self._llm

    def _get_summary_chain(self):
        if self._summary_chain is None:
            self._summary_chain = (
                {
                    "existing_summary": lambda payload: payload["existing_summary"],
                    "recent_turns": lambda payload: payload["recent_turns"],
                }
                | _SUMMARY_PROMPT
                | self._get_llm()
                | StrOutputParser()
            )
        return self._summary_chain

    def _get_facts_chain(self):
        if self._facts_chain is None:
            self._facts_chain = (
                {"recent_turns": lambda payload: payload["recent_turns"]}
                | _FACTS_PROMPT
                | self._get_llm()
                | StrOutputParser()
            )
        return self._facts_chain

    def summarise(self, existing_summary: str, transcript: str) -> str:
        """Fold *transcript* into the running summary."""
        if not transcript.strip():
            return existing_summary.strip()
        summary = self._get_summary_chain().invoke(
            {"existing_summary": existing_summary or "", "recent_turns": transcript}
        )
        return summary.strip()

    def extract_facts(self, transcript: str) -> list[str]:
        """Extract explicit user facts from *transcript*."""
        if not transcript.strip():
            return []
        raw = self._get_facts_chain().invoke({"recent_turns": transcript})
        return format_facts(parse_json_array(raw))


# ── Window management ─────────────────────────────────────────────────────────

def _to_messages(turns: list[dict[str, Any]]) -> list[BaseMessage]:
    return [
        AIMessage(content=turn.get("content", ""))
        if turn.get("role") == "assistant"
        else HumanMessage(content=turn.get("content", ""))
        for turn in turns
    ]


def _to_turns(messages: list[BaseMessage]) -> list[dict[str, str]]:
    return [
        {
            "role": "assistant" if isinstance(message, AIMessage) else "user",
            "content": message.content if isinstance(message.content, str) else str(message.content),
        }
        for message in messages
    ]


def roll_window(
    turns: list[dict[str, Any]], max_tokens: int = DEFAULT_WINDOW_TOKENS
) -> tuple[list[dict[str, str]], list[dict[str, str]], int]:
    """Trim *turns* to the newest messages that fit within *max_tokens*.

    Returns ``(kept, dropped, kept_tokens)``. ``dropped`` holds everything that
    fell out of the window, oldest first, ready to be summarised.
    """
    messages = _to_messages(turns)
    if not messages:
        return [], [], 0

    trimmed = trim_messages(
        messages,
        max_tokens=max_tokens,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
        include_system=False,
        allow_partial=False,
    )

    if not trimmed:
        # A single oversized message cannot be trimmed. Keep it so the current
        # question is never dropped, even though it exceeds the budget.
        trimmed = messages[-1:]

    dropped_count = len(messages) - len(trimmed)
    return (
        _to_turns(trimmed),
        _to_turns(messages[:dropped_count]),
        count_tokens_approximately(trimmed),
    )


def format_recent_turns(turns: list[dict[str, str]]) -> str:
    """Render turns as a transcript, one line per turn."""
    return "\n".join(f"{turn['role'].title()}: {turn['content']}" for turn in turns)


def build_memory_context(memory: dict[str, Any], window: list[dict[str, str]]) -> str:
    """Render the summary, facts and windowed turns for the prompt."""
    if not memory or not memory.get("enabled", True):
        return ""

    pieces: list[str] = []

    summary = (memory.get("summary") or "").strip()
    if summary:
        pieces.append(f"Summary:\n{summary}")

    facts = [fact.strip() for fact in memory.get("facts", []) if fact and fact.strip()]
    if facts:
        pieces.append("Facts:\n" + "\n".join(f"- {fact}" for fact in facts))

    transcript = format_recent_turns(window)
    if transcript:
        pieces.append("Recent conversation:\n" + transcript)

    return "\n\n".join(pieces)


# ── Memory document ───────────────────────────────────────────────────────────

def init_memory(now: str) -> dict[str, Any]:
    """Initialise a memory document. Keys match records already in the database."""
    return {
        "enabled": True,
        "summary": "",
        "facts": [],
        "recent_turns": [],
        "last_refreshed_at": now,
        "last_refreshed_turn_count": 0,
        "window_tokens": 0,
    }


def fold_overflow(
    memory: dict[str, Any],
    dropped: list[dict[str, str]],
    *,
    agent: MemoryAgent,
    now: str,
    total_turn_count: int,
) -> dict[str, Any]:
    """Fold messages that left the window into the summary and fact list."""
    transcript = format_recent_turns(dropped)
    return {
        **memory,
        "summary": agent.summarise(memory.get("summary", ""), transcript),
        "facts": update_facts(memory.get("facts", []), agent.extract_facts(transcript)),
        "last_refreshed_at": now,
        "last_refreshed_turn_count": total_turn_count,
    }


def update_memory_window(
    turns: list[dict[str, Any]],
    memory: dict[str, Any],
    *,
    agent: MemoryAgent,
    now: str,
    total_turn_count: int,
    max_tokens: int = DEFAULT_WINDOW_TOKENS,
) -> tuple[dict[str, Any], str]:
    """Roll the token window and return ``(memory, prompt_context)``.

    The summary is only recomputed when messages actually leave the window, so
    steady-state turns cost no extra LLM calls.
    """
    window, dropped, window_tokens = roll_window(turns, max_tokens)
    updated = {**memory, "recent_turns": window, "window_tokens": window_tokens}
    if dropped:
        updated = fold_overflow(
            updated,
            dropped,
            agent=agent,
            now=now,
            total_turn_count=total_turn_count,
        )
    return updated, build_memory_context(updated, window)


def update_facts(existing: list[str], new_facts: list[str]) -> list[str]:
    """Merge *new_facts* into *existing*, de-duplicated and capped."""
    existing_clean = [fact.strip() for fact in existing if fact and fact.strip()]
    merged = list(
        dict.fromkeys(existing_clean + [fact for fact in new_facts if fact and fact.strip()])
    )
    return merged[-MAX_FACTS:]


def format_facts(facts: list[Any]) -> list[str]:
    """Clean and de-duplicate raw facts coming back from the LLM."""
    normalised: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        if not isinstance(fact, str):
            continue
        text = fact.strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        normalised.append(text)
        if len(normalised) >= MAX_FACTS:
            break
    return normalised


def parse_json_array(raw: str) -> list[str]:
    """Extract a JSON array of facts from LLM output, tolerating code fences."""
    candidate = raw.strip()
    candidate = re.sub(r"^```(?:json)?\n", "", candidate, flags=re.I)
    candidate = re.sub(r"\n```$", "", candidate)

    json_start = candidate.find("[")
    json_end = candidate.rfind("]")
    if json_start != -1 and json_end != -1 and json_end > json_start:
        candidate = candidate[json_start : json_end + 1]

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    return []
