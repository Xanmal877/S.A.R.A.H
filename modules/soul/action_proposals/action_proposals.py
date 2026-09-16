"""
Persistent, versioned, per-character action-proposal store.

The autonomous runtime is observe/suggest only. When the runtime *or* an
interactive caller wants to perform a non-observe operation that the policy
categorizes as approval-required (shell, packages, services, containers, git
mutation, remote shell/files, browser mutation, media control, clipboard
write, identity/memory/profile/fact/goal writes, ...), it must first surface an
explicit proposal for the operator to review and approve. Only an approved,
unexpired proposal for the exact same tool+args, owned by the current
character, may be executed - and doing so consumes it atomically so a proposal
(and therefore an operator consent decision) can never authorize the operation
twice.

Each proposal lives under
~/.sarah/state/{character_id}/action_proposals.json (honoring SARAH_STATE_DIR
via modules.memory.json_file_store.state_dir), is versioned so a later phase
can migrate without misreading old files, and keeps an append-only audit
`history` for every status/content change.

Proposal layout (a sibling of goals.json / identity_state.json):

  {
    "version": 1,
    "proposals": {
      "<proposal_id>": {
        "id": "proposal-...",            # stable id (tools reference by this)
        "person_id": str|None,           # optional caller/person binding (None=character-general)
        "goal_id": str|None,             # optional link to an explicit goal
        "tool": str,                     # exact tool name to run
        "args": { ... },                 # sanitized (pure-JSON) args to match
        "rationale": str,                # why this action is needed
        "evidence": str,                 # what was inspected to justify it
        "risk_category": one of readonly|ordinary|approval_required
        "status": proposed|approved|rejected|expired|executed|failed
        "created_at": str, "expires_at": str,
        "decision": str|None,            # operator decision text on approve/reject
        "actor": str|None,               # who approved/rejected (operator id)
        "outcome": str,                  # execution result / failure note
        "history": [{ at, action, field?, old?, new?, note?, actor? }]  # append-only audit
      }
    }
  }

Unknown versions fail closed (loaded as empty) rather than guessing at a shape
the code doesn't understand - same rule as goals / person_profiles.

The store is character-scoped: a proposal a character writes is isolated from
every other character's proposals, and the orchestrator's approval-gate only
ever looks in the current character's store, so an approved proposal can never
authorize work for a *different* character (person/character isolation is
inherent in the store keying).

Within a character's store, an optional `person_id` binds a proposal to a
specific caller (e.g. "discord:{author}", "local:operator"). A bound
active_person_id (from the trusted application boundary) can only operate on
proposals whose person_id matches (or, for access, whose person_id is None -
character-general proposals remain accessible to any bound caller). The
execution gate refuses a proposal whose person_id disagrees with the bound
caller. When no caller is bound, a proposal's person_id is advisory metadata.

Args are stored as pure JSON so the execution path can compare the requested
tool+args for an *exact* match, but model-visible rendering (list_pending etc.)
omits raw args to avoid leaking potentially-sensitive argument values into
model text.
"""

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timedelta

from modules.memory.json_file_store import state_dir
from modules.soul.identity_state.identity_state import active_character_id
from modules.soul.identity_state.identity_state import active_person_id

logger = logging.getLogger("ActionProposalStore")

# Schema version for an action_proposals file. Bump + add a migration (don't
# silently rewrite) if the on-disk shape ever changes.
PROPOSALS_VERSION = 1

# Proposal lifecycle states.
PROPOSAL_STATUSES = ("proposed", "approved", "rejected", "expired", "executed", "failed")
# Statuses that are still awaiting an operator decision.
PENDING_STATUSES = ("proposed", "approved")

# Risk categories assigned by the tool classification table (see
# get_risk_category below).
RISK_READONLY = "readonly"
RISK_ORDINARY = "ordinary"
RISK_APPROVAL_REQUIRED = "approval_required"
RISK_CATEGORIES = (RISK_READONLY, RISK_ORDINARY, RISK_APPROVAL_REQUIRED)

# Default proposal lifetime before it expires and can no longer be executed.
DEFAULT_TTL_SECONDS = 86400  # 24h

# Bound for list_pending / listing results.
PROPOSAL_LIST_LIMIT = 50

# A short, stable, opaque id for a proposal (per-character store, so ids never
# need to be globally unique across characters).
PROPOSAL_ID_RE = re.compile(r"^proposal-[0-9a-f]{8}$")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _new_proposal_id() -> str:
    return f"proposal-{uuid.uuid4().hex[:8]}"


def _coerce_iso(value):
    """Return the given ISO timestamp string (or None) - used for expiry math
    without importing timezone semantics into every caller."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _sanitize_args(args) -> dict:
    """Return a pure-JSON-safe copy of the request args.

    Tool arguments arrive as a JSON string from the model. This parses them
    into a nested dict/list/scalar structure that round-trips through JSON and
    can be compared for an *exact* match at execution time. Anything that is
    not JSON-serializable is coerced to a string rather than silently dropped,
    so the stored representation stays complete but safe.
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            args = {"raw": args}

    def _clean(value):
        if isinstance(value, dict):
            return {str(k): _clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_clean(v) for v in value]
        if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
            return value
        return str(value)

    cleaned = _clean(args)
    return cleaned if isinstance(cleaned, dict) else {"value": cleaned}


# ── tool risk classification ─────────────────────────────────────────────
# Read-only / observe tools: purely informational, never require approval even
# under a non-observe interactive request. A superset conceptually of the
# orchestrator's observe allowlist, but used for the *non-observe* approval
# gate (observe-only is stricter and governed separately).
READONLY_TOOLS = {
    "get_system_info", "search_packages", "service_status", "list_failed_services",
    "list_containers", "list_images", "container_logs",
    "list_media_players", "media_status", "get_clipboard", "list_windows",
    "git_status", "git_log", "git_diff", "get_recent_logs", "get_recent_changes",
    "browser_read_page", "browser_accessibility_tree", "browser_network_log",
    "retrieve_episodes", "get_memory_summary", "retrieve_facts",
    "get_semantic_fact_summary", "get_person_profile", "list_person_profiles",
    "list_active_goals", "retrieve_memory", "get_opinion", "get_identity_summary",
}

# Tools that MUST carry an operator-approved proposal before execution. This is
# the code-enforced classification: shell, packages, services, containers, git
# mutation, remote shell/files, browser mutation, media control, clipboard
# write, and identity/memory/profile/fact/goal writes.
APPROVAL_REQUIRED_TOOLS = {
    # shell
    "run_command", "shell",
    # packages
    "install_package", "remove_package", "update_system",
    # services
    "start_service", "stop_service", "restart_service",
    # containers
    "start_container", "stop_container", "restart_container",
    # git mutation
    "git_pull", "git_commit",
    # remote shell / remote files
    "run_remote_command", "push_file_to_peer", "pull_file_from_peer",
    # browser mutation
    "browser_navigate", "browser_click", "browser_type", "browser_screenshot",
    "browser_clear_network_log", "browser_start_trace", "browser_stop_trace",
    # media control
    "media_play_pause", "media_next", "media_previous",
    # clipboard write
    "set_clipboard",
    # identity / memory / profile / fact / goal writes
    "form_opinion", "add_interest", "add_dislike", "add_relationship_note",
    "add_goal", "complete_goal",
    "store_memory", "record_change",
    "record_episode", "consolidate_episode", "add_semantic_fact",
    "upsert_person_profile", "set_person_preference",
    "set_person_consent_boundary", "add_person_relationship_note",
    "create_goal", "update_goal", "mark_goal_active", "mark_goal_blocked",
    "request_goal_approval", "complete_goal_explicit", "abandon_goal",
}


def get_risk_category(tool_name: str) -> str:
    """Return the risk category for a tool name.

    approval_required means the orchestrator will refuse to run it (even on a
    non-observe interactive request) without a valid operator-approved proposal.
    readonly tools / ordinary non-destructive tools run normally without a
    proposal under a non-observe request. The observe_only autonomous policy is
    stricter and handled separately in the orchestrator.
    """
    if tool_name in READONLY_TOOLS:
        return RISK_READONLY
    if tool_name in APPROVAL_REQUIRED_TOOLS:
        return RISK_APPROVAL_REQUIRED
    return RISK_ORDINARY


class ActionProposalStore:
    """Persistent, versioned action-proposal store for a single character.

    Layout:
      { "version": 1,
        "proposals": { "<proposal_id>": { ...proposal... } } }

    Single-use enforcement: validate_and_consume runs under a module-level lock
    so two concurrent in-process consumers can never both authorize the same
    proposal. A proposal is transitioned to executed/failed exactly once.
    """

    def __init__(self, character_id: str = "sarah", storage_path: str = None):
        self.character_id = character_id
        self.storage_path = storage_path or os.path.join(
            state_dir(character_id), "action_proposals.json"
        )
        self.storage_path = os.path.expanduser(self.storage_path)
        self._lock = threading.Lock()
        self._proposals: dict = {}
        self._version = PROPOSALS_VERSION
        self._load()

    # ── persistence ───────────────────────────────────────────────────
    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load action proposals from %s: %s", self.storage_path, e)
            return
        version = saved.get("version")
        if version != PROPOSALS_VERSION:
            logger.warning(
                "Action proposals at %s have unsupported version %r (expected %d); "
                "loading as empty. A migration would be needed - not guessed.",
                self.storage_path, version, PROPOSALS_VERSION,
            )
            return
        self._proposals = saved.get("proposals", {}) or {}
        self._version = version

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as e:
            logger.warning("Could not save action proposals to %s: %s", self.storage_path, e)

    # ── lifecycle ────────────────────────────────────────────────────
    def propose(self, tool: str, args, *, rationale: str = "", evidence: str = "",
                risk_category: str = None, goal_id: str = None, person_id: str = None,
                ttl_seconds: int = DEFAULT_TTL_SECONDS) -> "Optional[str]":
        """Create a new proposal in 'proposed' status and return its stable id
        (or None on invalid input / storage failure). `args` is sanitized to
        pure JSON. `risk_category` is derived from the tool unless the caller
        already knows it (the propose tool always supplies the classified value
        for integrity). `person_id` optionally binds the proposal to a specific
        caller; when the trusted application boundary has bound
        active_person_id, the proposal is forced to that caller and a model-supplied
        different person_id is refused."""
        tool = (tool or "").strip()
        if not tool:
            logger.warning("Proposal tool must be non-empty; refusing to create.")
            return None
        # Caller identity boundary: with active_person_id bound (e.g. Discord ->
        # "discord:{author}", CLI/voice -> "local:operator"), the model cannot
        # propose/assign an action for a different person. With no caller bound,
        # the supplied person_id (if any) is stored as advisory metadata.
        active_person = active_person_id.get()
        if active_person is not None and person_id not in (None, active_person):
            logger.warning(
                "Refusing proposal: caller %r cannot bind action to person %r.",
                active_person, person_id,
            )
            return None
        risk = get_risk_category(tool)
        if risk_category in RISK_CATEGORIES:
            risk = risk_category
        try:
            ttl = max(60, int(ttl_seconds))
        except (TypeError, ValueError):
            ttl = DEFAULT_TTL_SECONDS
        pid = _new_proposal_id()
        now = _now_iso()
        created_dt = datetime.fromisoformat(now)
        expires_at = (created_dt + timedelta(seconds=ttl)).isoformat(timespec="microseconds")
        resolved_person = active_person if active_person is not None else person_id
        entry = {
            "id": pid,
            "person_id": resolved_person or None,
            "goal_id": goal_id or None,
            "tool": tool,
            "args": _sanitize_args(args),
            "rationale": rationale or "",
            "evidence": evidence or "",
            "risk_category": risk,
            "status": "proposed",
            "created_at": now,
            "expires_at": expires_at,
            "decision": None,
            "actor": None,
            "outcome": "",
            "history": [{
                "at": now,
                "action": "propose",
                "new": {
                    "tool": tool,
                    "risk_category": risk,
                    "goal_id": goal_id or None,
                    "person_id": resolved_person or None,
                },
                "actor": "model",
            }],
        }
        with self._lock:
            self._proposals[pid] = entry
            self._save()
        return pid

    def get(self, proposal_id: str) -> "Optional[dict]":
        with self._lock:
            entry = self._proposals.get(proposal_id)
            if entry is not None:
                self._expire_if_needed_locked(entry)
                self._save()
            # Shallow copy; the args dict is immutable for matching purposes.
            return dict(entry) if entry is not None else None

    def _person_access_error_locked(self, entry) -> "Optional[str]":
        """Return a refusal reason when the bound caller may not operate on a
        proposal by direct id. A bound caller may access proposals whose
        person_id is None (character-general) or matches them; they may never
        access another person's proposal. Returns None when access is allowed.
        """
        active_person = active_person_id.get()
        if active_person is not None:
            prop_person = entry.get("person_id") if entry is not None else None
            if prop_person not in (None, active_person):
                return "Refused: the current caller cannot access another person's action proposal."
        return None

    def approve(self, proposal_id: str, actor: str = "operator", decision: str = "") -> "Optional[dict]":
        """Approve a 'proposed' proposal so its matching operation may run.
        Appends an approval decision to the audit. Returns the updated proposal
        or None if not found / in a terminal or non-proposed state."""
        with self._lock:
            entry = self._proposals.get(proposal_id)
            if entry is None:
                return None
            access = self._person_access_error_locked(entry)
            if access is not None:
                logger.warning("Person access refused on approve: %s", access)
                return None
            self._expire_if_needed_locked(entry)
            if entry["status"] != "proposed":
                return None
            old = entry["status"]
            now = _now_iso()
            entry["status"] = "approved"
            entry["decision"] = decision or None
            entry["actor"] = actor or "operator"
            entry["history"].append({
                "at": now,
                "action": "status",
                "field": "status",
                "old": old,
                "new": "approved",
                "note": decision or None,
                "actor": actor or "operator",
            })
            self._save()
            return dict(entry)

    def reject(self, proposal_id: str, actor: str = "operator", decision: str = "") -> "Optional[dict]":
        """Reject a 'proposed'/'approved' proposal (terminal state; cannot be
        executed). Appends an audit entry."""
        with self._lock:
            entry = self._proposals.get(proposal_id)
            if entry is None:
                return None
            access = self._person_access_error_locked(entry)
            if access is not None:
                logger.warning("Person access refused on reject: %s", access)
                return None
            if entry["status"] in ("executed", "failed", "rejected"):
                return None
            old = entry["status"]
            now = _now_iso()
            entry["status"] = "rejected"
            entry["decision"] = decision or None
            entry["actor"] = actor or "operator"
            entry["history"].append({
                "at": now,
                "action": "status",
                "field": "status",
                "old": old,
                "new": "rejected",
                "note": decision or None,
                "actor": actor or "operator",
            })
            self._save()
            return dict(entry)

    def _visible_to_active_person(self, entry) -> bool:
        """True when the bound caller (active_person_id) is allowed to see a
        proposal. A bound caller may see proposals whose person_id is None
        (character-general) or matches them; with no caller bound, all proposals
        are visible. Used to scope list/list_pending to the active caller."""
        active_person = active_person_id.get()
        if active_person is None:
            return True
        prop_person = entry.get("person_id")
        return prop_person in (None, active_person)

    def list_pending(self, limit: int = PROPOSAL_LIST_LIMIT) -> list:
        """List proposals still awaiting an operator decision (proposed or
        approved), oldest first. Read-only, bounded, and scoped to the bound
        caller when active_person_id is set."""
        with self._lock:
            pending = []
            for entry in self._proposals.values():
                if entry["status"] not in ("proposed", "approved"):
                    continue
                if not self._visible_to_active_person(entry):
                    continue
                pending.append(dict(entry))
        pending.sort(key=lambda p: p.get("created_at", ""))
        return pending[:limit]

    def list(self, status: str = None, limit: int = PROPOSAL_LIST_LIMIT) -> list:
        """List proposals optionally filtered by exact status, newest first.
        Scoped to the bound caller when active_person_id is set."""
        with self._lock:
            result = []
            for entry in self._proposals.values():
                if status and entry.get("status") != status:
                    continue
                if not self._visible_to_active_person(entry):
                    continue
                result.append(dict(entry))
        result.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        return result[:limit]

    # ── consumption / outcome (single-use gate) ──────────────────────
    def validate_and_consume(self, proposal_id: str, tool: str, args) -> "Optional[dict]":
        """Validate that a proposal is (a) present in THIS character's store,
        (b) approved, (c) not expired, and (d) matches the requested tool+args
        exactly - and if so atomically consume it (mark executed) so it can
        never be used again.

        Returns the (consumed) proposal entry on success, or a dict
        {"error": msg} on refusal. The error is a clear, operator-facing
        refusal message so the orchestrator can report exactly why an action
        was refused.
        """
        with self._lock:
            entry = self._proposals.get(proposal_id)
            if entry is None:
                # Store is character-scoped, so a proposal from another
                # character simply does not exist here - inherent isolation.
                return {"error": (
                    f"Approval required: proposal '{proposal_id}' was not found or "
                    f"does not belong to the current character. Request an operator "
                    f"approval (propose_action) and submit the approved proposal id."
                )}
            access = self._person_access_error_locked(entry)
            if access is not None:
                return {"error": (
                    f"Approval required: proposal '{proposal_id}' belongs to a "
                    "different caller. The current caller cannot consume another "
                    "person's action proposal."
                )}
            self._expire_if_needed_locked(entry)
            if entry["status"] == "expired":
                return {"error":
                        f"Approval required: proposal '{proposal_id}' has expired "
                        "before execution. Propose it again for operator approval."}
            if entry["status"] != "approved":
                from_state = entry["status"]
                return {"error": (
                    f"Approval required: proposal '{proposal_id}' is '{from_state}' "
                    "and has not been approved by the operator."
                )}
            if entry["tool"] != tool:
                return {"error": (
                    f"Approval required: proposal '{proposal_id}' approves tool "
                    f"'{entry['tool']}', not '{tool}'. The approved proposal is "
                    "exact to the requested tool."
                )}
            if entry.get("args") != _sanitize_args(args):
                return {"error": (
                    f"Approval required: proposal '{proposal_id}' approves a "
                    "specific set of arguments that does not match this request. "
                    "The approved proposal is exact to the requested args."
                )}
            # Atomically consume: mark executed before handing back.
            old = entry["status"]
            now = _now_iso()
            entry["status"] = "executed"
            entry["history"].append({
                "at": now,
                "action": "status",
                "field": "status",
                "old": old,
                "new": "executed",
                "note": "proposal consumed - authorizes exactly one execution",
            })
            self._save()
            return dict(entry)

    def record_outcome(self, proposal_id: str, result: str, success: bool) -> "Optional[dict]":
        """Record the outcome of a consumed/executed proposal. On failure (the
        tool errored), the proposal transitions to 'failed'; on success it stays
        'executed' with the outcome string attached. Links outcome to the
        proposal's goal and an episodic event without embedding raw args."""
        with self._lock:
            entry = self._proposals.get(proposal_id)
            if entry is None:
                return None
            now = _now_iso()
            entry["outcome"] = (result or "")[:4000]
            if not success:
                old = entry["status"]
                entry["status"] = "failed"
                entry["history"].append({
                    "at": now,
                    "action": "status",
                    "field": "status",
                    "old": old,
                    "new": "failed",
                    "note": "execution failed",
                })
            self._save()
            link = dict(entry)
        self._link_outcome(link)
        return link

    def _expire_if_needed_locked(self, entry):
        if entry["status"] not in ("proposed", "approved"):
            return
        expires = _coerce_iso(entry.get("expires_at"))
        if expires is not None and datetime.now() > expires:
            old = entry["status"]
            entry["status"] = "expired"
            entry["history"].append({
                "at": _now_iso(),
                "action": "status",
                "field": "status",
                "old": old,
                "new": "expired",
                "note": "proposal expired before approval/execution",
            })

    def _link_outcome(self, proposal: dict):
        """Best-effort linkage of a finished proposal outcome to its goal and
        an episodic event, WITHOUT embedding sensitive raw arguments."""
        if proposal.get("goal_id") and proposal.get("status"):
            try:
                from modules.memory.episodic_memory import _active_store as _ep_active
                from modules.soul.goals import _active_store as _goal_active
                episode_id = _ep_active().record(
                    "action",
                    (f"Proposed action '{proposal['tool']}' -> "
                     f"{proposal['status']} "
                     f"({proposal.get('risk_category') or 'unknown'}). "
                     + (f"Link: goal {proposal['goal_id']}." if proposal["goal_id"] else "")
                     + (" Outcome recorded." if proposal.get("outcome") else "")),
                    source="action_proposals",
                    confidence=1.0,
                    salience=0.5,
                    goal_id=proposal["goal_id"],
                )
                goal_store = _goal_active()
                if episode_id is not None:
                    goal_store.update_goal(
                        proposal["goal_id"],
                        linked_episode_ids=[episode_id],
                        audit_actor="action_proposals",
                    )
            except Exception as e:  # noqa: BLE001 - linkage is best-effort
                logger.warning("Could not link proposal outcome to goal/episode: %s", e)

    # ── serialization ────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"version": self._version, "proposals": self._proposals}

    def count(self, status: str = None) -> int:
        if status:
            return sum(1 for p in self._proposals.values() if p.get("status") == status)
        return len(self._proposals)


# ── per-character registry + contextvar resolution (same as identity/goals) ──
_proposal_stores: dict[str, "ActionProposalStore"] = {}


def get_action_proposal_store(character_id: str = "sarah") -> "ActionProposalStore":
    """Look up (or lazily create) the action-proposal store for a character."""
    if character_id not in _proposal_stores:
        _proposal_stores[character_id] = ActionProposalStore(character_id=character_id)
    return _proposal_stores[character_id]


def _active_store() -> "ActionProposalStore":
    """Resolve the store for whichever character's tool-call loop is running."""
    return get_action_proposal_store(active_character_id.get())


def _clear_action_proposal_store_cache():
    """Drop cached store instances (tests only). Each store pins a storage_path
    at construction; redirecting SARAH_STATE_DIR to a fresh temp dir requires
    invalidating the cache so a later case doesn't reuse a stale path."""
    _proposal_stores.clear()


# ── model-visible rendering ─────────────────────────────────────────────
def _render_proposal(proposal: dict) -> str:
    """A single model-visible proposal line. Raw args are intentionally NOT
    shown (they can carry sensitive command/file/payload values); the proposal
    references them by stable id only, and exact args are validated at
    execution time."""
    pid = proposal.get("id")
    head = f"{pid} [{proposal.get('risk_category')}] {proposal.get('tool')}" if pid \
        else f"[{proposal.get('risk_category')}] {proposal.get('tool')}"
    parts = [head, proposal.get("status", "")]
    if proposal.get("goal_id"):
        parts.append(f"goal {proposal['goal_id']}")
    if proposal.get("rationale"):
        parts.append(f"- {proposal['rationale']}")
    if proposal.get("decision"):
        parts.append(f"decision: {proposal['decision']}")
    return "- " + " · ".join(parts)


def render_proposals(proposals: list) -> str:
    """Concise, bounded, model-visible rendering of proposals (no raw args)."""
    if not proposals:
        return ""
    return "\n".join(_render_proposal(p) for p in proposals)
