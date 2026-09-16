"""
Per-character episodic memory: an append-only, durable event record.

Backed by stdlib `sqlite3` only (no ORM, no third-party DB). One database per
character at ~/.sarah/state/{character_id}/episodes.sqlite, honoring
SARAH_STATE_DIR via modules.memory.json_file_store.state_dir.

Schema (small and explicit):
    id            INTEGER PRIMARY KEY AUTOINCREMENT
    recorded_at   TEXT     -- ISO-8601, lexicographically sortable
    character_id  TEXT     -- which character owns this episode
    person_id     TEXT     -- nullable; the stable id of the caller/person involved
    kind          TEXT     -- e.g. "conversation", "task", "observation"
    content       TEXT     -- free-text description of what happened
    source        TEXT     -- provenance: "cli", "voice", "discord", "manual", ...
    confidence    REAL 0-1 -- how sure we are this is accurate
    salience      REAL 0-1 -- how important/durable the memory is (ranking)
    goal_id       TEXT     -- nullable; link to an active goal this relates to
    metadata_json TEXT     -- free-form JSON metadata

Every query is fully parameterized (user-provided values are bound as ?  placeholders,
never interpolated into SQL). Retrieval never crosses character or person boundaries:
each query always filters by character_id, and a person scope restricts to that
episode's person (plus character-general episodes with NULL person_id), so a caller
never sees another person's private memories.

Capture is *explicit* in this phase: nothing auto-writes episodes; callers record
events deliberately. In particular the Discord bot does not auto-store every message.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

from modules.memory.json_file_store import state_dir
from modules.soul.identity_state.identity_state import (
    active_character_id,
    active_person_id,
)

logger = logging.getLogger("EpisodicMemory")

# Default bound for context/model-visible memory recall.
RELEVANT_MEMORY_LIMIT = 6

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at   TEXT    NOT NULL,
    character_id  TEXT    NOT NULL,
    person_id     TEXT,
    kind          TEXT    NOT NULL,
    content       TEXT    NOT NULL,
    source        TEXT    NOT NULL,
    confidence    REAL    NOT NULL DEFAULT 0.5,
    salience      REAL    NOT NULL DEFAULT 0.5,
    goal_id       TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes_char ON episodes (character_id);
CREATE INDEX IF NOT EXISTS idx_episodes_char_salience ON episodes (character_id, salience);
CREATE INDEX IF NOT EXISTS idx_episodes_char_time ON episodes (character_id, recorded_at);
"""

_INSERT = """
INSERT INTO episodes
    (recorded_at, character_id, person_id, kind, content, source,
     confidence, salience, goal_id, metadata_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_COLS = (
    "id, recorded_at, character_id, person_id, kind, content, source, "
    "confidence, salience, goal_id, metadata_json"
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _clamp(value, lo=0.0, hi=1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(lo, min(hi, v))


def _to_kinds(kinds) -> list:
    """Normalize the kinds filter to a list of strings (empty when absent)."""
    if kinds is None:
        return []
    if isinstance(kinds, str):
        return [kinds]
    return [str(k) for k in kinds]


class EpisodicMemoryStore:
    """Append-only episodic memory for a single character.

    The store is bound to one `character_id` (its database file lives under that
    character's state dir), so writes and reads are inherently character-scoped;
    the schema additionally carries the character_id so the column is explicit and
    queries filter on it as defence in depth.
    """

    def __init__(self, character_id: str = "sarah", storage_path: str = None):
        self.character_id = character_id
        self.storage_path = storage_path or os.path.join(
            state_dir(character_id), "episodes.sqlite"
        )
        self.storage_path = os.path.expanduser(self.storage_path)

    # ── low-level connection ──────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        conn = sqlite3.connect(self.storage_path)
        conn.row_factory = sqlite3.Row
        # _SCHEMA is multiple statements (CREATE TABLE + indexes), which
        # conn.execute() rejects; executescript runs them together.
        with conn:
            conn.executescript(_SCHEMA)
        return conn

    def _query(self, sql: str, params: list):
        conn = None
        try:
            conn = self._connect()
            with conn:
                cur = conn.execute(sql, params)
                rows = cur.fetchall()
            return list(rows)
        except sqlite3.Error as e:
            # Never let a storage error break a reasoning cycle; log and treat
            # as "no results" rather than raising.
            logger.warning("episodic read failed for %s: %s", self.storage_path, e)
            return []
        finally:
            if conn is not None:
                conn.close()

    # ── write ─────────────────────────────────────────────────────────
    def record(self, kind: str, content: str, source: str = "local",
               *, person_id: str = None, confidence: float = 0.5,
               salience: float = 0.5, goal_id: str = None,
               metadata: dict = None, recorded_at: str = None) -> int:
        """Append one episode and return its new row id (or None on failure)."""
        recorded_at = recorded_at or _now_iso()
        metadata_json = json.dumps(metadata) if metadata is not None else None
        params = (
            recorded_at,
            self.character_id,
            person_id if person_id else None,
            kind,
            content,
            source,
            _clamp(confidence),
            _clamp(salience),
            goal_id if goal_id else None,
            metadata_json,
        )
        try:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute(_INSERT, params)
                    row_id = cur.lastrowid
            finally:
                conn.close()
            return row_id
        except sqlite3.Error as e:
            logger.warning("episodic write failed for %s: %s", self.storage_path, e)
            return None

    # ── read ─────────────────────────────────────────────────────────
    def retrieve(self, query: str = None, *, person_id: str = None,
                 kinds=None, limit: int = 20, rank: str = "salience") -> list:
        """Return episodes for this character matching the given filters.

        Args:
            query: optional free-text matched against content/kind (case-insensitive).
            person_id: optional person scope. When given, results are restricted to
                that person's episodes PLUS character-general episodes (NULL
                person_id). A caller never sees another person's private episodes.
            kinds: optional single kind or iterable of kinds.
            limit: bounded result cap (1..200).
            rank: "salience" (default) ranks by salience then recency; "recency"
                ranks by recorded_at only.
        """
        limit = max(1, min(int(limit), 200))
        where = ["character_id = ?"]
        params: list = [self.character_id]

        kinds = _to_kinds(kinds)
        if kinds:
            placeholders = ", ".join("?" for _ in kinds)
            where.append(f"kind IN ({placeholders})")
            params.extend(kinds)

        if query:
            where.append("(content LIKE ? OR kind LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        if person_id:
            # Person-bound callers see their episodes plus general (NULL person)
            # episodes, never a different person's private ones.
            where.append("(person_id = ? OR person_id IS NULL)")
            params.append(person_id)

        order = (
            "recorded_at DESC, id DESC"
            if rank == "recency"
            else "salience DESC, recorded_at DESC, id DESC"
        )
        sql = (
            f"SELECT {_SELECT_COLS} FROM episodes "
            f"WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?"
        )
        params.append(limit)
        rows = self._query(sql, params)
        return [self._row_to_episode(r) for r in rows]

    def count(self, character_id: str = None) -> int:
        """Total episodes for a character (defaults to this store's character)."""
        cid = character_id or self.character_id
        rows = self._query(
            "SELECT COUNT(*) AS n FROM episodes WHERE character_id = ?", [cid]
        )
        return int(rows[0]["n"]) if rows else 0

    def summary(self, *, person_id: str = None, query: str = None,
                kinds=None, limit: int = RELEVANT_MEMORY_LIMIT,
                rank: str = "salience") -> str:
        """Human/LLM-readable summary of this character's most relevant
        episodes, with raw stable person ids omitted (labeled by display name
        only when a profile is available)."""
        episodes = self.retrieve(
            query=query, person_id=person_id, kinds=kinds,
            limit=limit, rank=rank,
        )
        return render_episodes(self.character_id, episodes)

    @staticmethod
    def _row_to_episode(row: sqlite3.Row) -> dict:
        ep = dict(row)
        if ep.get("metadata_json"):
            try:
                ep["metadata"] = json.loads(ep["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                ep["metadata"] = None
        else:
            ep["metadata"] = None
        ep.pop("metadata_json", None)
        return ep


# ── per-character registry + contextvar resolution (same as identity/person) ──
_episodic_stores: dict[str, "EpisodicMemoryStore"] = {}


def get_episodic_store(character_id: str = "sarah") -> "EpisodicMemoryStore":
    """Look up (or lazily create) the episodic store for a character."""
    if character_id not in _episodic_stores:
        _episodic_stores[character_id] = EpisodicMemoryStore(character_id=character_id)
    return _episodic_stores[character_id]


def _active_store() -> "EpisodicMemoryStore":
    """Resolve the store for whichever character's tool-call loop is running."""
    return get_episodic_store(active_character_id.get())


def _clear_episodic_store_cache():
    """Drop cached store instances (tests only). Each store pins a storage_path
    at construction; redirecting SARAH_STATE_DIR to a fresh temp dir requires
    invalidating the cache so a later case doesn't reuse a stale path."""
    _episodic_stores.clear()


# ── model-visible summary ──────────────────────────────────────────────
def _person_label(character_id: str, person_id: str) -> str:
    """Human/presentation label for a person, omitting raw stable person id.

    Uses the person's display name when a profile exists; otherwise we emit no
    person label at all rather than leaking the opaque stable id into model text.
    """
    try:
        from modules.soul.person_profiles import get_person_profile_store
    except Exception:  # noqa: BLE001 - profiler store is optional for rendering
        return ""
    profile = get_person_profile_store(character_id).get_profile(person_id)
    if profile is None:
        return ""
    name = profile.get("display_name") or ""
    return name


def render_episodes(character_id: str, episodes: list) -> str:
    """Concise, model-visible rendering of episodes.

    Raw stable person ids are never shown: a person is labeled by display name
    only (or not at all when unknown).
    """
    if not episodes:
        return ""
    lines = []
    for ep in episodes:
        prefix = f"[{ep['kind']}] {ep['content']}"
        parts = [prefix]
        if ep.get("person_id"):
            label = _person_label(character_id, ep["person_id"])
            if label:
                parts.append(f"about {label}")
        parts.append(f"confidence {ep['confidence']:.2f}")
        line = " - ".join(parts)
        if ep.get("goal_id"):
            line += f" [goal: {ep['goal_id']}]"
        lines.append("- " + line)
    return "\n".join(lines)


def episodic_memory_summary(character_id: str = None, *, person_id: str = None,
                            limit: int = RELEVANT_MEMORY_LIMIT, query: str = None,
                            kinds=None, rank: str = "salience") -> str:
    """A concise memory summary the model can read each turn.

    Scope is derived the same way context assembly does: character from
    character_id (or active_character_id), person from person_id (or
    active_person_id). Results are bounded and rendered without raw person ids.
    """
    cid = character_id or active_character_id.get()
    person = person_id if person_id is not None else active_person_id.get()
    episodes = get_episodic_store(cid).retrieve(
        query=query, person_id=person, kinds=kinds, limit=limit, rank=rank
    )
    return render_episodes(cid, episodes)
