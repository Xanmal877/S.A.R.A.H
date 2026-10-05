#!/usr/bin/env python3
"""sarah_ctl - the operator's approval surface for Sarah's action proposals.

Sarah's autonomous loop is observe-and-suggest only: it may *propose* an action
(propose_action mints a proposal in status "proposed") but can never execute
one. This CLI is the other half of that consent boundary - the human decision
that turns a proposal into exactly one execution.

    sarah_ctl pending                 # what is she asking for?
    sarah_ctl show <id>              # what exactly would run? (tool + raw args)
    sarah_ctl approve <id>           # yes - now it MAY run once
    sarah_ctl reject <id>            # no - terminal, cannot run
    sarah_ctl run <id>               # execute it, exactly once

approve and run are deliberately SEPARATE verbs. Approving records a decision;
running is a second, explicit act. One extra keystroke buys a second audit line
and a real safety margin - and it means a proposal can never execute as a side
effect of a decision that was made about something else.

`run` uses the same store primitives the orchestrator's gate uses
(ActionProposalStore.validate_and_consume -> executor.execute ->
record_outcome -> interpret_outcome), so:

  * the proposal must be character-scoped to this character,
  * it must be approved, unexpired, and match tool+args EXACTLY,
  * it is consumed ATOMICALLY before execution, so it can never authorize a
    second run - even if the first run failed.

Unlike ToolOrchestrator._execute_gated (which only consumes proposals whose
tool is classified approval_required, because that is the only case a model
ever supplies a proposal_id for), this path consumes *every* proposal it runs.
A proposal is a consent artifact; consuming it exactly once is its contract,
whatever the tool's risk category.

No new store, no bypass: this is a thin operator-driven caller of the existing
ActionProposalStore. Nothing here widens the autonomous loop's authority.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.soul.action_proposals import (  # noqa: E402
    get_action_proposal_store,
    render_proposals,
)
from modules.soul.action_proposals.action_proposals import (  # noqa: E402
    PROPOSAL_LIST_LIMIT,
)
from modules.soul.identity_state.identity_state import active_character_id  # noqa: E402
from modules.tools.executor import executor  # noqa: E402
from modules.tools.init_tools import register_all_tools  # noqa: E402


def _store(character_id: str):
    # Pin the character contextvar so every store this call touches (proposals,
    # and the goal/episode stores the outcome interpreter links into) resolves
    # to the same character - exactly as the ToolOrchestrator does per request.
    active_character_id.set(character_id)
    return get_action_proposal_store(character_id)


def cmd_pending(args) -> int:
    store = _store(args.character)
    pending = store.list_pending(limit=args.limit)
    if not pending:
        print("No action proposals awaiting approval.")
        return 0
    print(render_proposals(pending))
    print(f"\n{len(pending)} proposal(s) awaiting a decision. "
          f"Use: sarah_ctl show <id>")
    return 0


def cmd_show(args) -> int:
    store = _store(args.character)
    entry = store.get(args.proposal_id)
    if entry is None:
        print(f"No action proposal with id '{args.proposal_id}'.", file=sys.stderr)
        return 1
    # Raw args ARE shown here - and only here. This is the operator's view, the
    # one place a human must be able to read exactly what would run before
    # approving it. Model-visible renderings (list_pending etc.) deliberately
    # omit them.
    order = ("id", "status", "tool", "risk_category", "person_id", "goal_id",
             "created_at", "expires_at", "actor", "decision")
    for key in order:
        print(f"{key:14}: {entry.get(key)}")
    print(f"{'rationale':14}: {entry.get('rationale') or '-'}")
    print(f"{'evidence':14}: {entry.get('evidence') or '-'}")
    print(f"{'args':14}: {json.dumps(entry.get('args', {}), indent=2, sort_keys=True)}")
    if entry.get("outcome"):
        print(f"{'outcome':14}: {entry['outcome']}")
    print("history:")
    for h in entry.get("history", []):
        print(f"  {h.get('at')}  {h.get('action')}  "
              f"{h.get('old', '') or ''}->{h.get('new', '') or ''}  "
              f"{h.get('note') or ''}")
    return 0


def cmd_approve(args) -> int:
    store = _store(args.character)
    entry = store.get(args.proposal_id)
    if entry is None:
        print(f"No action proposal with id '{args.proposal_id}'.", file=sys.stderr)
        return 1
    if entry["status"] != "proposed":
        print(f"Proposal '{args.proposal_id}' is '{entry['status']}' "
              f"and cannot be approved.", file=sys.stderr)
        return 1
    updated = store.approve(args.proposal_id, actor="operator",
                            decision=args.note or "")
    if updated is None:
        print(f"Proposal '{args.proposal_id}' could not be approved.", file=sys.stderr)
        return 1
    print(f"Approved {updated['id']} ({updated['tool']}). "
          f"It has NOT run. To execute it exactly once: "
          f"sarah_ctl run {updated['id']}")
    return 0


def cmd_reject(args) -> int:
    store = _store(args.character)
    entry = store.get(args.proposal_id)
    if entry is None:
        print(f"No action proposal with id '{args.proposal_id}'.", file=sys.stderr)
        return 1
    if entry["status"] in ("executed", "failed", "rejected"):
        print(f"Proposal '{args.proposal_id}' is '{entry['status']}' "
              f"and cannot be rejected.", file=sys.stderr)
        return 1
    updated = store.reject(args.proposal_id, actor="operator",
                           decision=args.note or "")
    if updated is None:
        print(f"Proposal '{args.proposal_id}' could not be rejected.", file=sys.stderr)
        return 1
    print(f"Rejected {updated['id']} ({updated['tool']}). It cannot be executed.")
    return 0


async def _run(args) -> int:
    store = _store(args.character)
    entry = store.get(args.proposal_id)
    if entry is None:
        print(f"No action proposal with id '{args.proposal_id}'.", file=sys.stderr)
        return 1
    tool = entry["tool"]

    # Atomic single-use gate: present + approved + unexpired + exact tool/args
    # match, consumed in the same locked step. A refusal here is a clear,
    # operator-facing message and nothing is executed.
    consumed = store.validate_and_consume(args.proposal_id, tool, entry["args"])
    if "error" in consumed:
        print(consumed["error"], file=sys.stderr)
        return 1
    # From here the proposal IS consumed. Whether the run succeeds or fails it
    # can never be executed again from this id.

    register_all_tools()
    try:
        result = await executor.execute(tool, **entry["args"])
    except Exception as e:  # noqa: BLE001 - report any executor failure
        err = f"Error executing {tool}: {e!s}"
        recorded = store.record_outcome(args.proposal_id, err[:4000], success=False)
        _interpret(recorded, args.character)
        print(err, file=sys.stderr)
        return 2

    result_text = result if isinstance(result, str) else str(result)
    success = not result_text.startswith("Error")
    recorded = store.record_outcome(args.proposal_id, result_text, success=success)
    _interpret(recorded, args.character)

    print(f"Executed {args.proposal_id} ({tool}) - "
          f"{'success' if success else 'FAILED'}.")
    print(result_text)
    return 0 if success else 2


def _interpret(recorded, character_id: str) -> None:
    """Feed the outcome into the same interpreter the orchestrator uses, so an
    operator-approved run lands in Sarah's experience (journal + safe goal
    transitions) exactly like an in-process run.

    Agent-less here on purpose: no live Soul/mental_state exists in a one-shot
    CLI, so the fixed mood nudge is skipped while all journal/goal bookkeeping
    still happens - the interpreter's documented agent-less design. Any failure
    inside is logged and swallowed; the tool result above is unaffected.
    """
    if recorded is None:
        return
    try:
        from modules.soul.experience.outcome_interpreter import interpret_outcome
        summary = interpret_outcome(recorded, mental_state=None,
                                   character_id=character_id)
        if summary.get("journaled"):
            print("Outcome recorded in the reflection journal.")
    except Exception as e:  # noqa: BLE001 - interpretation must never break the CLI
        print(f"Warning: outcome interpretation failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="sarah_ctl",
        description="Operator approval surface for Sarah's action proposals.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("-c", "--character", default="sarah",
                    help="character whose proposals to operate on (default: sarah)")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pending", help="list proposals awaiting a decision")
    p.add_argument("--limit", type=int, default=PROPOSAL_LIST_LIMIT)
    p.set_defaults(func=cmd_pending)

    p = sub.add_parser("show", help="show one proposal in full, including raw args")
    p.add_argument("proposal_id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("approve", help="approve a proposed action (does not run it)")
    p.add_argument("proposal_id")
    p.add_argument("--note", default="", help="operator decision note (audited)")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("reject", help="reject a proposed action (terminal)")
    p.add_argument("proposal_id")
    p.add_argument("--note", default="", help="operator decision note (audited)")
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser("run", help="execute an approved proposal, exactly once")
    p.add_argument("proposal_id")
    p.set_defaults(func="run")

    args = ap.parse_args()
    if args.func == "run":
        return asyncio.run(_run(args))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
