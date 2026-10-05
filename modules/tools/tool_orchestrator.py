import json
import logging
import os

from modules.soul.action_proposals.action_proposals import get_risk_category
from modules.soul.action_proposals.action_proposals import _active_store as _proposal_active_store
from modules.soul.identity_state.identity_state import active_character_id
from modules.tools.executor import executor
from modules.tools.tool_registry import registry

logger = logging.getLogger("ToolOrchestrator")

# Bare control characters that are valid inside a Python string but illegal
# inside a JSON *string literal*. The escaped form we substitute is what the
# model should have emitted in the first place.
_CONTROL_ESCAPES = {
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _escape_bare_control_chars(text: str) -> str:
    """Escape raw control characters that appear *inside* JSON string literals.

    Only characters between an opening and closing `"` are touched, and only
    ones that are illegal in JSON strings - so ordinary text, structural
    whitespace between tokens, and already-escaped sequences are left exactly
    as they were. This is a lossless repair (it restores the two-character
    escape the model omitted); it never drops, reorders, or invents content.
    """
    out = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            elif ch in _CONTROL_ESCAPES:
                out.append(_CONTROL_ESCAPES[ch])
                continue
            elif ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
        elif ch == '"':
            in_string = True
        out.append(ch)
    return "".join(out)


def _parse_model_json(response_text: str):
    """Decode the first complete JSON object in a model response.

    Tries the strict decoder first (fast path), then a single bounded repair
    that escapes bare control characters inside string literals. The repair
    exists because the cloud reasoning model intermittently emits a literal
    newline inside `final_answer` instead of the escaped `\\n`, which is invalid
    JSON and used to kill the entire reasoning turn ("Invalid control character
    at ..."). A genuine parse failure still raises json.JSONDecodeError - it is
    never swallowed, and nothing is ever fabricated to paper over it.
    """
    start = response_text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no JSON object found in response", response_text, 0)
    try:
        decision, _end = json.JSONDecoder().raw_decode(response_text, start)
        return decision
    except json.JSONDecodeError:
        repaired = _escape_bare_control_chars(response_text)
        if repaired == response_text:
            raise  # nothing repairable - surface the real parse failure
        decision, _end = json.JSONDecoder().raw_decode(repaired, start)
        logger.info("Repaired bare control characters inside a model JSON string.")
        return decision


class ToolOrchestrator:
    """
    Handles the multi-turn reasoning loop:
    1. Prompt LLM with context and available tools.
    2. Parse tool requests.
    3. Execute tools and return results.
    4. Loop until a final answer is provided.
    """
    def __init__(self, llm_client, agent=None, character_id: str = None, character_name: str = None,
                 allowed_tools: set = None, observe_only: bool = False):
        self.llm_client = llm_client
        self.agent = agent
        # Explicit character_id/character_name let a caller with no full
        # BaseCharacter (e.g. the Discord bot in discord/main.py, which
        # doesn't run the soul/state-machine loop) still identify who's
        # talking, instead of always defaulting to Sarah.
        self.character_id = character_id or getattr(agent, "character_id", "sarah")
        self.character_name = character_name or getattr(agent, "characterName", self.character_id.capitalize())
        self.max_iterations = 5
        # None = full registry (the desktop daemon, trusted local operator).
        # A set = hard allowlist - enforced in process_request's dispatch,
        # not just hidden from the prompt, since an LLM can still try to call
        # a tool it wasn't told about (bad instruction-following, or a
        # prompt-injected message). Same reasoning as modules/hive/server.py's
        # SUPPORTED_TYPES whitelist: an externally-reachable surface (there:
        # hive peers, here: any Discord user typing a trigger word) never
        # gets the full ungated registry, which includes run_command.
        self.allowed_tools = allowed_tools
        # observe_only is the autonomous-loop policy (requirement: unattended
        # autonomy is observe-and-suggest only). When set, the effective
        # allowlist is the intersection of allowed_tools (if any) with the
        # minimal read-only/observe set below. Anything else - even a tool
        # that made it past a *non-observe* allowlist - is refused with a
        # clear "approval required" message. This is code-enforced, not
        # prompt-enforced: it cannot be disabled by anything the model says.
        self.observe_only = observe_only
        self._OBSERVE_ALLOWLIST = {
            "get_recent_logs", "get_recent_changes", "get_identity_summary",
            "get_system_info", "service_status", "list_failed_services",
            "list_containers", "list_images", "container_logs",
            "list_media_players", "media_status", "get_clipboard",
            "list_windows", "git_status", "git_log", "git_diff",
            "retrieve_memory", "get_opinion",
        }
        # The effective allowlist actually used for dispatch (see below).
        self._effective_allowlist = self._compute_effective_allowlist()

    def _compute_effective_allowlist(self):
        """Effective tool allowlist after observing the observe-only policy.

        None  -> full registry (no restriction; normal interactive behavior).
        set   -> that set intersected with the observe allowlist when
                 observe_only is set, otherwise the set as-is.

        Interactive/trusted callers pass neither, so they are unaffected.
        Discord's DISCORD_ALLOWED_TOOLS stays exactly as before.
        """
        if not self.observe_only:
            return self.allowed_tools
        observe = self._OBSERVE_ALLOWLIST
        if self.allowed_tools is not None:
            return self.allowed_tools & observe
        return observe

    def _get_tool_definitions(self):
        tools = registry.list_tools()
        if self._effective_allowlist is not None:
            tools = {name: desc for name, desc in tools.items() if name in self._effective_allowlist}
        defs = "\n".join([f"- {name}: {desc}" for name, desc in tools.items()])
        return defs

    async def process_request(self, user_request, system_context=""):
        # Tool calls (form_opinion, add_goal, ...) resolve "whose identity"
        # via this contextvar rather than a fixed global - see
        # modules/soul/identity_state/identity_state.py. Set per-request,
        # not just at construction, since asyncio.Task copies the current
        # context at creation time.
        active_character_id.set(self.character_id)

        tool_defs = self._get_tool_definitions()

        # Load this character's identity manifest (path resolved relative to
        # this file, not hardcoded, so it survives the project directory
        # moving/renaming). Falls back to a bare-bones generic prompt if this
        # character has no manifest yet (e.g. Tama - nothing has been written
        # for her voice/style, unlike agents/sarah_identity.md) rather than
        # silently reusing Sarah's.
        agents_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "agents",
        )
        identity_path = os.path.join(agents_dir, f"{self.character_id}_identity.md")
        try:
            with open(identity_path, "r") as f:
                identity = f.read()
        except OSError as e:
            logger.warning(f"No identity manifest at {identity_path} ({e}); using a generic fallback prompt.")
            identity = (
                f"You are {self.character_name}, an autonomous agent with your own persistent "
                f"identity, memory, and goals - not a generic assistant."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    f"{identity}\n\n"
                    f"You are {self.character_name}. You are an agent, not an advisor. "
                    f"You have direct access to the system via these tools:\n"
                    f"{tool_defs}\n\n"
                    f"OPERATIONAL RULES:\n"
                    f"1. BE AUTONOMOUS: If a goal is clear, investigate and act. Do not ask for individual commands.\n"
                    f"2. BE ASSERTIVE: 'I found the problem. I'm fixing it.'\n"
                    f"3. BE THOROUGH: Generate hypotheses, investigate before concluding, and ground every claim in "
                    f"evidence you actually inspected (logs, config, system state), not a guess. Discard bad theories "
                    f"quickly and say so.\n"
                    f"4. BE SAFE: Ask before destructive or irreversible actions.\n\n"
                    f"APPROVAL RULE: Read-only/observe tools and ordinary "
                    f"non-destructive tools are allowed directly. High-risk or "
                    f"destructive operations (shell, packages, services, "
                    f"containers, git mutation, remote shell/files, browser "
                    f"mutation, media control, clipboard write, and "
                    f"identity/memory/profile/fact/goal writes) require an "
                    f"operator-approved action proposal. To run one you MUST "
                    f"first call propose_action to obtain a proposal id, wait for "
                    f"operator approval (approve_action), then call the tool "
                    f"again INCLUDING the 'proposal_id' argument with the exact "
                    f"same args you proposed. Without an approved matching "
                    f"proposal the action is refused.\n\n"
                    f"To use a tool, respond ONLY with a JSON object:\n"
                    f'{{"tool": "tool_name", "args": {{"arg_name": "value"}}}}'
                    f"\nWhen you have the final answer or have completed the task, respond with:\n"
                    f'{{"final_answer": "Your response to the user"}}'
                    f"\n\nOUTPUT FORMAT (strict): reply with the single JSON object and nothing "
                    f"else. It must be valid JSON on ONE logical line - there must be no raw "
                    f"line breaks inside any string value. Write a newline inside a string as "
                    f"the two characters \\n (escaped), never as a literal line break. "
                    f"Unescaped control characters make the JSON unparseable and the turn is lost."
                )
            },
            {"role": "user", "content": f"Context: {system_context}\n\nRequest: {user_request}"}
        ]

        current_prompt = self._build_prompt(messages)
        
        for i in range(self.max_iterations):
            logger.info(f"Reasoning cycle {i+1}/{self.max_iterations}")
            response_text = await self.llm_client.generate_decision(current_prompt)
            
            try:
                # Parse the FIRST complete, well-formed JSON object in the
                # response, ignoring anything before/after it. raw_decode
                # respects nesting (a naive find('{')..rfind('}') span, or a
                # non-greedy \{.*?\} regex, both break as soon as the model
                # emits a nested object like {"tool": "x", "args": {...}} or
                # trailing prose/a second JSON blob after the real answer).
                # _parse_model_json also repairs the one known malformed-output
                # case (bare control chars inside a string) without hiding a
                # real parse failure.
                try:
                    decision = _parse_model_json(response_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse LLM response as JSON: {e}\nRaw: {response_text!r}")
                    return f"LLM failed to provide valid structured response: {response_text}"

                if "final_answer" in decision:
                    return decision["final_answer"]
                
                if "tool" in decision:
                    tool_name = decision["tool"]
                    args = decision.get("args", {})

                    if self._effective_allowlist is not None and tool_name not in self._effective_allowlist:
                        logger.warning("Blocked disallowed tool call: %s (context=%s)", tool_name,
                                       "observe_only" if self.observe_only else "allowlist")
                        if self.observe_only:
                            # Autonomous loop policy: observe-and-suggest only.
                            # Code-enforced - the agent cannot disable it via
                            # its own output. Any write/act tool gets a clear
                            # "approval required" message instead of running.
                            result = (
                                f"Action '{tool_name}' requires operator approval and was not "
                                f"executed. As an observe-and-suggest autonomous loop you may "
                                f"only use read-only/observe tools."
                            )
                        else:
                            result = f"Error: tool '{tool_name}' is not permitted in this context."
                    else:
                        # Non-observe path. Read-only observes run normally.
                        # Approval-required (high-risk/destructive) tools need an
                        # operator-approved, current-character, unexpired, exact-
                        # match proposal unless one is supplied; otherwise the
                        # action is refused with a clear message. Ordinary non-
                        # destructive tools keep running without a proposal.
                        proposal_id = args.pop("proposal_id", None)
                        result = await self._execute_gated(tool_name, args, proposal_id)
                    
                    # Append tool result to conversation
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "system", "content": f"Tool {tool_name} result: {result}"})
                    current_prompt = self._build_prompt(messages)
                else:
                    return f"LLM response missing 'tool' or 'final_answer': {response_text}"
                    
            except Exception as e:
                logger.exception(f"Error in reasoning cycle: {e}")
                return f"Error during reasoning: {e!s}"

        return "Error: Maximum reasoning iterations reached without a final answer."

    def _build_prompt(self, messages):
        prompt = ""
        for msg in messages:
            prompt += f"{msg['role'].upper()}: {msg['content']}\n\n"
        return prompt

    async def _execute_gated(self, tool_name, args, proposal_id):
        """Execution path honoring the code-enforced approval policy.

        - read-only/observe tools: always run (no proposal needed).
        - ordinary non-destructive interactive tools: run (no proposal needed).
        - approval-required (high-risk/destructive) tools: run ONLY when a
          valid current-character, approved, unexpired, exact-match proposal id
          is supplied, and the proposal is consumed atomically (single-use).
          Otherwise refuse with a clear approval-required message. The tool
          is never executed without that gate.

        This is the *non-observe* gate. Autonomous observe-only operates under
        a stricter policy handled separately above (blocked disallowed/observe
        tools are refused outright regardless of any proposal).
        """
        risk = get_risk_category(tool_name)
        if risk == "approval_required":
            if not proposal_id:
                return self._approval_required_message(tool_name)
            store = _proposal_active_store()
            consumed = store.validate_and_consume(proposal_id, tool_name, args)
            if "error" in consumed:
                return consumed["error"]
            # Approved + exact match + atomically consumed: authorized to run
            # exactly this one time. The proposal is already single-use; whether
            # the run succeeds or fails it must NEVER run again from this id.
            try:
                result = await executor.execute(tool_name, **args)
            except Exception as e:  # noqa: BLE001 - report any executor failure
                logger.exception("Executor raised for approved proposal %s", proposal_id)
                err = f"Error executing {tool_name}: {e!s}"
                # Bound the failure note to what we persist (never the raw
                # arbitrary args), transition proposed->failed so the consumed
                # single-use approval is not left dangling as 'executed'.
                recorded = store.record_outcome(proposal_id, err[:4000], success=False)
                self._interpret_outcome(recorded)
                return err
            success = not (isinstance(result, str) and result.startswith("Error"))
            recorded = store.record_outcome(proposal_id, result, success=success)
            self._interpret_outcome(recorded)
            return result

        # read-only / ordinary interactive non-destructive tools:
        # no proposal required - preserve normal behavior.
        return await executor.execute(tool_name, **args)

    def _interpret_outcome(self, recorded_proposal):
        """Best-effort deterministic interpretation of a recorded action outcome.

        Invokes modules.soul.experience.outcome_interpreter AFTER
        store.record_outcome so the interpreter turns the executor success
        boolean into journal/goal/mood updates. It is wired here (the sole call
        site) and is fully guarded: any failure inside the interpreter is logged
        and swallowed - it must NEVER alter the underlying tool result or the
        already-recorded proposal outcome.

        Agent-less design: when this orchestrator has no live agent/Soul (e.g. a
        tool-call loop without a BaseCharacter, or under test), no mental_state
        is passed and the interpreter skips the mood nudge while still doing all
        goal/journal bookkeeping.
        """
        try:
            from modules.soul.experience.outcome_interpreter import interpret_outcome
        except Exception as e:  # noqa: BLE001 - interpreter is optional plumbing
            logger.warning("Outcome interpreter unavailable; skipping: %s", e)
            return
        mental_state = None
        agent = getattr(self, "agent", None)
        if agent is not None:
            soul = getattr(agent, "soul", None)
            if soul is not None:
                mental_state = getattr(soul, "mental_state", None)
        try:
            interpret_outcome(
                recorded_proposal,
                mental_state=mental_state,
                character_id=self.character_id,
            )
        except Exception:  # noqa: BLE001 - never let interpretation break the call
            logger.exception("Outcome interpretation failed for proposal %s; "
                             "tool result is unaffected", recorded_proposal.get("id"))

    def _approval_required_message(self, tool_name: str) -> str:
        return (
            f"Action '{tool_name}' requires operator approval and was not "
            f"executed. This operation is classified as approval-required. "
            f"Propose it (propose_action) and, once the operator approves, "
            f"resubmit with the approved proposal id."
        )
