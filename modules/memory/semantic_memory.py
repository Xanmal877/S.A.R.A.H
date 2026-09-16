"""
Per-character semantic memory: durable facts consolidated from episodes.

Backed by stdlib `sqlite3` only (no ORM, no third-party DB). One database per
character at ~/.sarah/state/{character_id}/semantic_memory.sqlite, honoring
SARAH_STATE_DIR via modules.memory.json_file_store.state_dir.

Schema (small and explicit):
    fact_id           INTEGER PRIMARY KEY AUTOINCREMENT  -- stable per-revision id
    character_id      TEXT    -- which character owns this fact
    person_id         TEXT    -- nullable; the stable id of the caller/person this fact is about
    topic             TEXT    -- key / subject of the fact
    value             TEXT    -- the asserted value
    source_episode_id INTEGER -- nullable; the episode id this fact was consolidated from
    source_note       TEXT    -- nullable; free-text provenance when not from an episode
    confidence        REAL 0-1
    salience          REAL 0-1
    status            TEXT    -- 'active' | 'superseded'
    created_at        TEXT    -- when this revision was created (ISO-8601)
    superseded_at     TEXT    -- when this revision was superseded (nullable)
    metadata_json     TEXT    -- free-form JSON metadata

Revision model: this is an *append-only* fact store. A new fact with the same
scope+topic does NOT update a row in place - it inserts a fresh revision and
marks the previously-active revision(s) for that (character, person-scope, topic)
as 'superseded'. History is never deleted, so the full provenance trail survives
and consumers always read the active revision(s) first.

Scope for supersession and retrieval:
    character_id is mandatory (the store is character-scoped anyway).
    person_id is optional. A fact with a NULL person_id is character-general; a
    fact with a person_id is person-scoped. Two revisions supersede when they
    share character_id, topic, and the same person scope (both NULL, or the
    same person_id). This keeps one person's fact from clobbering another's, and
    keeps a general fact distinct from a person-scoped one.

Retrieval never crosses character/person boundaries: every query filters by
character_id, and a person binder restricts results to that person's facts PLUS
character-general facts (NULL person_id). Model-visible summaries omit raw
person ids (labeled by display name only when a profile exists).

Capture/consolidation is *explicit* in this phase: nothing auto-consolidates
episodes and no LLM is called. `consolidate_episode` runs deliberately, records
provenance, and verifies its source episode belongs to the active character.
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

logger = logging.getLogger("SemanticMemory")

# Default bound for context/model-visible fact recall.
RELEVANT_FACT_LIMIT = 6

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id      TEXT    NOT NULL,
    person_id         TEXT,
    topic             TEXT    NOT NULL,
    value             TEXT    NOT NULL,
    source_episode_id INTEGER,
    source_note       TEXT,
    confidence        REAL    NOT NULL DEFAULT 0.5,
    salience          REAL    NOT NULL DEFAULT 0.5,
    status            TEXT    NOT NULL DEFAULT 'active',
    created_at        TEXT    NOT NULL,
    superseded_at     TEXT,
    metadata_json     TEXT
);
CREATE INDEX IF NOT EXISTS idx_facts_char ON facts (character_id);
CREATE INDEX IF NOT EXISTS idx_facts_char_topic ON facts (character_id, topic);
CREATE INDEX IF NOT EXISTS idx_facts_char_status_salience ON facts (character_id, status, salience);
CREATE INDEX IF NOT EXISTS idx_facts_char_person ON facts (character_id, person_id);
"""

_INSERT = """
INSERT INTO facts
    (character_id, person_id, topic, value, source_episode_id, source_note,
     confidence, salience, status, created_at, superseded_at, metadata_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL, ?)
"""

_SELECT_COLS = (
    "fact_id, character_id, person_id, topic, value, source_episode_id, "
    "source_note, confidence, salience, status, created_at, superseded_at, "
    "metadata_json"
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _clamp(value, lo=0.0, hi=1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(lo, min(hi, v))


class SemanticMemoryStore:
    """Append-only semantic fact store for a single character.

    The store is bound to one `character_id`, so writes and reads are inherently
    character-scoped; the schema additionally carries character_id and queries
    filter on it as defence in depth. Facts carry an optional person_id to scope
    facts about a specific person.
    """

    def __init__(self, character_id: str = "sarah", storage_path: str = None):
        self.character_id = character_id
        self.storage_path = storage_path or os.path.join(
            state_dir(character_id), "semantic_memory.sqlite"
        )
        self.storage_path = os.path.expanduser(self.storage_path)

    # ── low-level connection ──────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        conn = sqlite3.connect(self.storage_path)
        conn.row_factory = sqlite3.Row
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
            logger.warning("semantic read failed for %s: %s", self.storage_path, e)
            return []
        finally:
            if conn is not None:
                conn.close()

    # ── write / consolidation ────────────────────────────────────────
    def _supersede_scope(self, conn, person_id, topic, superseded_at: str) -> None:
        """Mark all currently-active facts for the given scope+topic as
        superseded. person_id matched exactly, including the NULL general scope
        (SQL 'IS NULL'). The previous active revision keeps its full row for
        audit - it is never deleted."""
        if person_id is None:
            conn.execute(
                "UPDATE facts SET status='superseded', superseded_at=? "
                "WHERE character_id=? AND topic=? AND person_id IS NULL "
                "AND status='active'",
                (superseded_at, self.character_id, topic),
            )
        else:
            conn.execute(
                "UPDATE facts SET status='superseded', superseded_at=? "
                "WHERE character_id=? AND person_id=? AND topic=? "
                "AND status='active'",
                (superseded_at, self.character_id, person_id, topic),
            )

    def add_fact(self, topic: str, value: str, *, person_id: str = None,
                 source_episode_id=None, source_note: str = None,
                 confidence: float = 0.5, salience: float = 0.5,
                 metadata: dict = None, created_at: str = None) -> int:
        """Append a new active fact revision, superseding any prior active
        revision in the same scope+topic. Returns the new fact_id (or None on
        failure). Does not modify history - prior revisions are marked
        'superseded', never deleted.

        A fact with the same topic but a different person scope (e.g. NULL vs a
        person_id, or a different person_id) does not supersede each other.
        """
        created_at = created_at or _now_iso()
        metadata_json = json.dumps(metadata) if metadata is not None else None
        params = (
            self.character_id,
            person_id if person_id else None,
            topic,
            value,
            int(source_episode_id) if source_episode_id is not None else None,
            source_note if source_note else None,
            _clamp(confidence),
            _clamp(salience),
            created_at,
            metadata_json,
        )
        try:
            conn = self._connect()
            try:
                with conn:
                    self._supersede_scope(conn, person_id, topic, created_at)
                    cur = conn.execute(_INSERT, params)
                    return cur.lastrowid
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.warning("semantic write failed for %s: %s", self.storage_path, e)
            return None

    # ── read ─────────────────────────────────────────────────────────
    def retrieve(self, *, person_id: str = None, topic: str = None,
                 query: str = None, active_only: bool = True,
                 limit: int = RELEVANT_FACT_LIMIT) -> list:
        """Return facts for this character matching the given filters.

        Args:
            person_id: optional person scope. When given, results are restricted
                to that person's facts PLUS character-general facts (NULL
                person_id) - a caller never sees another person's private facts.
            topic: optional exact topic filter.
            query: optional free-text matched against topic/value
                (case-insensitive).
            active_only: when True (default) return only 'active' revisions,
                which is how consumers see the current truth without history.
            limit: bounded result cap (1..50).
        """
        limit = max(1, min(int(limit), 50))
        where = ["character_id = ?"]
        params: list = [self.character_id]

        if active_only:
            where.append("status = 'active'")

        if topic:
            where.append("topic = ?")
            params.append(topic)

        if query:
            where.append("(topic LIKE ? OR value LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        if person_id:
            # Person-bound callers see their facts plus general (NULL person)
            # facts, never a different person's private facts.
            where.append("(person_id = ? OR person_id IS NULL)")
            params.append(person_id)

        sql = (
            f"SELECT {_SELECT_COLS} FROM facts "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY salience DESC, created_at DESC, fact_id DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._query(sql, params)
        return [self._row_to_fact(r) for r in rows]

    def get_fact(self, fact_id: int):
        """Fetch a single fact owned by this character, or None."""
        try:
            fact_id = int(fact_id)
        except (TypeError, ValueError):
            return None
        rows = self._query(
            "SELECT {cols} FROM facts WHERE fact_id = ? AND character_id = ?".format(
                cols=_SELECT_COLS
            ),
            [fact_id, self.character_id],
        )
        if not rows:
            return None
        return self._row_to_fact(rows[0])

    def count(self, character_id: str = None) -> int:
        """Total facts (all revisions) for a character."""
        cid = character_id or self.character_id
        rows = self._query(
            "SELECT COUNT(*) AS n FROM facts WHERE character_id = ?", [cid]
        )
        return int(rows[0]["n"]) if rows else 0

    def summary(self, *, person_id: str = None, topic: str = None,
                query: str = None, limit: int = RELEVANT_FACT_LIMIT) -> str:
        """Human/LLM-readable summary of this character's most relevant active
        facts, with raw stable person ids omitted (labeled by display name only
        when a profile is available)."""
        facts = self.retrieve(
            person_id=person_id, topic=topic, query=query,
            active_only=True, limit=limit,
        )
        return render_facts(self.character_id, facts)

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> dict:
        f = dict(row)
        if f.get("metadata_json"):
            try:
                f["metadata"] = json.loads(f["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                f["metadata"] = None
        else:
            f["metadata"] = None
        f.pop("metadata_json", None)
        return f


# ── per-character registry + contextvar resolution (same as identity/episodic) ──
_semantic_stores: dict[str, "SemanticMemoryStore"] = {}


def get_semantic_store(character_id: str = "sarah") -> "SemanticMemoryStore":
    """Look up (or lazily create) the semantic store for a character."""
    if character_id not in _semantic_stores:
        _semantic_stores[character_id] = SemanticMemoryStore(character_id=character_id)
    return _semantic_stores[character_id]


def _active_store() -> "SemanticMemoryStore":
    """Resolve the store for whichever character's tool-call loop is running."""
    return get_semantic_store(active_character_id.get())


def _clear_semantic_store_cache():
    """Drop cached store instances (tests only). Each store pins a storage_path
    at construction; redirecting SARAH_STATE_DIR to a fresh temp dir requires
    invalidating the cache so a later case doesn't reuse a stale path."""
    _semantic_stores.clear()


# ── model-visible summary ──────────────────────────────────────────────
def _person_label(character_id: str, person_id: str) -> str:
    """Human/presentation label for a person, omitting raw stable person id."""
    try:
        from modules.soul.person_profiles import get_person_profile_store
    except Exception:  # noqa: BLE001 - profiler store is optional for rendering
        return ""
    profile = get_person_profile_store(character_id).get_profile(person_id)
    if profile is None:
        return ""
    name = profile.get("display_name") or ""
    return name


def render_facts(character_id: str, facts: list) -> str:
    """Concise, model-visible rendering of facts.

    Raw stable person ids are never shown: a person is labeled by display name
    only (or not at all when unknown). Only active revisions are shown.
    """
    active = [f for f in facts if f.get("status") == "active"]
    if not active:
        return ""
    lines = []
    for fact in active:
        parts = [f"[{fact['topic']}] {fact['value']}"]
        if fact.get("person_id"):
            label = _person_label(character_id, fact["person_id"])
            if label:
                parts.append(f"about {label}")
        parts.append(f"confidence {fact['confidence']:.2f}")
        line = " - ".join(parts)
        if fact.get("source_episode_id"):
            line += f" [from episode #{fact['source_episode_id']}]"
        lines.append("- " + line)
    return "\n".join(lines)


def semantic_fact_summary(character_id: str = None, *, person_id: str = None,
                          limit: int = RELEVANT_FACT_LIMIT, topic: str = None,
                          query: str = None) -> str:
    """A concise semantic-memory summary the model can read each turn.

    Scope is derived the same way context assembly does: character from
    character_id (or active_character_id), person from person_id (or
    active_person_id). Results are bounded and rendered without raw person ids.
    """
    cid = character_id or active_character_id.get()
    person = person_id if person_id is not None else active_person_id.get()
    facts = get_semantic_store(cid).retrieve(
        person_id=person, topic=topic, query=query, active_only=True, limit=limit
    )
    return render_facts(cid, facts)
