"""
Per-character versioned bounded reflection journal.

This store is SYSTEM-WRITTEN ONLY. It is NOT a tool, is NOT registered in the
tool registry (modules/tools/init_tools.py), and is NOT exposed to Discord. The
autonomous loop (mainAgent) and the outcome interpreter
(modules/soul/experience/outcome_interpreter.py, itself reachable only from the
ToolOrchestrator) append entries; no model tool can read or write it, so the
journal is a trusted record of the runtime's own deterministic action-outcome
reasoning rather than something an LLM (or a Discord caller) can influence.

Each character's journal lives under
~/.sarah/state/{character_id}/reflection_log.json, honoring SARAH_STATE_DIR via
modules.memory.json_file_store.state_dir (the same path rule as goals /
action_proposals). It is versioned so a later phase can migrate without
misreading old files, and bounded to the most recent REFLECTION_LOG_CAP entries
(older entries are dropped, newest kept - FIFO). Unknown versions fail closed
(loaded as empty) rather than guessing at a shape the code doesn't understand.

Journal layout (a sibling of goals.json / action_proposals.json):

  {
    "version": 1,
    "entries": [                       # ordered oldest -> newest (list() returns newest first)
      {
        "id": "reflection-...",        # stable, per-character store (ids needn't be global)
        "recorded_at": str,            # ISO-8601
        "kind": autonomous | outcome,  # what produced the entry
        "content": str,                # bounded deterministic text (see below)
        "goal_id": str|None,           # linked goal, when this turn concerned one
        "proposal_id": str|None,       # linked action proposal, for outcome entries
        "outcome": success|failure|None,  # for outcome entries; else None
        "source": str,                 # provenance: "autonomous_loop" | "outcome_interpreter"
      }
    ]
  }

Every field is written by the runtime from deterministic data - never raw tool
args, never unmodified LLM output, never content that encodes anything the
model could use to launder privileged information. `content` for an autonomous
entry is the character's own (scheduler-deduped) reflection output; for an
outcome entry it is the interpreter's bounded reason built only from the
executor success flag + goal state (see outcome_interpreter.py).
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime

from modules.memory.json_file_store import state_dir
from modules.soul.identity_state.identity_state import active_character_id

logger = logging.getLogger("ReflectionLog")

# Schema version for a reflection_log file. Bump + add a migration (don't
# silently rewrite) if the on-disk shape ever changes.
REFLECTION_LOG_VERSION = 1

# Hard bound on how many journal entries a character retains. When the journal
# exceeds this, the OLDEST entries are dropped (newest kept).
REFLECTION_LOG_CAP = 200

# Journal entry kinds.
ENTRY_AUTONOMOUS = "autonomous"
ENTRY_OUTCOME = "outcome"
ENTRY_KINDS = (ENTRY_AUTONOMOUS, ENTRY_OUTCOME)

# Provenance markers for the entry `source` field.
SOURCE_AUTONOMOUS_LOOP = "autonomous_loop"
SOURCE_OUTCOME_INTERPRETER = "outcome_interpreter"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _new_entry_id() -> str:
    return f"reflection-{uuid.uuid4().hex[:8]}"


class ReflectionLogStore:
    """Per-character versioned, bounded reflection journal.

    Layout:
      { "version": 1, "entries": [ {entry...}, ... ] }
    """

    def __init__(self, character_id: str = "sarah", storage_path: str = None):
        self.character_id = character_id
        self.storage_path = storage_path or os.path.join(
            state_dir(character_id), "reflection_log.json"
        )
        self.storage_path = os.path.expanduser(self.storage_path)
        self._lock = threading.Lock()
        self._entries: list = []
        self._version = REFLECTION_LOG_VERSION
        self._load()

    # ── persistence ───────────────────────────────────────────────────
    def _load(self):
        """Load the journal, failing closed (to empty) on any shape we don't
        understand - including an unknown/newer schema version, exactly like
        goals / action_proposals."""
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load reflection log from %s: %s", self.storage_path, e)
            return
        version = saved.get("version")
        if version != REFLECTION_LOG_VERSION:
            logger.warning(
                "Reflection log at %s has unsupported version %r (expected %d); "
                "loading as empty. A migration would be needed - not guessed.",
                self.storage_path, version, REFLECTION_LOG_VERSION,
            )
            return
        entries = saved.get("entries") or []
        if not isinstance(entries, list):
            logger.warning("Reflection log at %s has no entries list; loading as empty.", self.storage_path)
            return
        self._entries = entries
        self._version = version
        # Defensively enforce the cap on load too (a hand-edited/oversized file
        # shouldn't blow past the bound).
        self._trim_locked()

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as e:
            logger.warning("Could not save reflection log to %s: %s", self.storage_path, e)

    def _trim_locked(self):
        """Drop the oldest entries beyond the cap (newest kept)."""
        excess = len(self._entries) - REFLECTION_LOG_CAP
        if excess > 0:
            del self._entries[:excess]

    # ── append ───────────────────────────────────────────────────────
    def append(self, *, kind: str, content: str, goal_id: str = None,
               proposal_id: str = None, outcome: str = None,
               source: str = None) -> int:
        """Append one journal entry (system-written only). Returns the new
        total entry count, or -1 on invalid input/storage failure.

        Never stores raw action args or unmodified model content beyond the
        bounded `content` the caller (autonomous loop / outcome interpreter)
        explicitly hands in. `outcome` must be 'success'/'failure' or None.
        """
        if kind not in ENTRY_KINDS:
            logger.warning("Reflection log refuses unknown kind %r.", kind)
            return -1
        if content is None:
            content = ""
        content = str(content)[:4000]
        outcome = outcome if outcome in ("success", "failure") else None
        source = source or (SOURCE_AUTONOMOUS_LOOP if kind == ENTRY_AUTONOMOUS
                            else SOURCE_OUTCOME_INTERPRETER)
        entry = {
            "id": _new_entry_id(),
            "recorded_at": _now_iso(),
            "kind": kind,
            "content": content,
            "goal_id": goal_id or None,
            "proposal_id": proposal_id or None,
            "outcome": outcome,
            "source": source,
        }
        with self._lock:
            self._entries.append(entry)
            self._trim_locked()
            self._save()
            return len(self._entries)

    # ── read / query ────────────────────────────────────────────────
    def list(self, *, limit: int = None) -> list:
        """Return journal entries, newest first (bounded)."""
        if limit is not None:
            limit = max(1, min(int(limit), REFLECTION_LOG_CAP))
        with self._lock:
            newest_first = list(reversed(self._entries))
            if limit is not None:
                newest_first = newest_first[:limit]
            return [dict(e) for e in newest_first]

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # ── serialization ───────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"version": self._version, "entries": self._entries}


# ── per-character registry + contextvar resolution (same as goals/proposals) ──
_reflection_stores: dict[str, "ReflectionLogStore"] = {}


def get_reflection_log_store(character_id: str = "sarah") -> "ReflectionLogStore":
    """Look up (or lazily create) the reflection journal store for a character."""
    if character_id not in _reflection_stores:
        _reflection_stores[character_id] = ReflectionLogStore(character_id=character_id)
    return _reflection_stores[character_id]


def _active_store() -> "ReflectionLogStore":
    """Resolve the store for whichever character's runtime is writing journal
    entries (matches the active_character_id used by goals / action_proposals)."""
    return get_reflection_log_store(active_character_id.get())


def _clear_reflection_log_store_cache():
    """Drop cached store instances (tests only)."""
    _reflection_stores.clear()
