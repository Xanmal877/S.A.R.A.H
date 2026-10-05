# ===============================
# CHARACTER RUNTIME
# ===============================
#
# Historically this module also defined the old Autumn's-Dungeoneering state
# machine: a ``StateMachine`` base plus ``IdleState`` / ``WorkState`` /
# ``ExploreState`` classes and the ``_probabilistic_decision`` fallback that
# picked between them at random.
#
# None of that is reachable from the live runtime. ``agents/baseAgent.Run()``
# drives ``StateMachineLogic()`` below, which does perception + reflection
# scheduling; the Idle/Work/Explore handlers were constructed in ``__init__``
# and then never invoked by any code path. They were dead weight that read like
# live behaviour - the exact class of defect this project keeps growing - so
# they were removed (along with ``stateMachine.py``).
#
# ``SarahStateMachine`` keeps only the parts the runtime actually uses, and no
# longer inherits from the deleted ``StateMachine`` base.

import asyncio
import logging
from typing import Optional

from modules.llmClient import LLMClient
from modules.observationModule import ObservationModule
from modules.perception import ScreenWatcher
from modules.personaMapper import PersonaMapper
from modules.reflection import ReflectionScheduler

logger = logging.getLogger("SarahStateMachine")


class SarahStateMachine:
    """The character runtime's autonomous driver.

    Two responsibilities, both live:

    1. Own the per-character cognitive services (LLM client, persona mapper,
       observation module, local screen watcher).
    2. ``StateMachineLogic()`` - called once per 1s tick by
       ``BaseCharacter.Run()`` - tick the reflection scheduler, which gates
       perception (short interval) and reflection (longer interval) and runs
       reflection in the background (at most one in flight).

    The attribute name ``stateMachine`` on ``BaseCharacter`` is what the rest of
    the runtime resolves this object by (see ``agents/baseAgent.py``), so it
    stays even though the class is no longer a state machine in the old sense.
    """

    def __init__(self, agent=None):
        self.agent = agent
        self.currentState = None
        self.isProcessingState = False

        # LLM Integration Modules
        self.llm_client = LLMClient.from_node_config()
        self.persona_mapper = PersonaMapper()
        self.observation_module = ObservationModule(agent)

        # Continuous screen awareness. A LOCAL vision model does the actual
        # looking and redaction - it never leaves this machine (see
        # LLMClient.is_local / ScreenWatcher). Only its sanitized text
        # description is ever handed to self.llm_client (which may be the
        # cloud engine) below.
        self.vision_client = LLMClient(model="gemma4:e4b", api_type="ollama")
        self.screen_watcher = ScreenWatcher(vision_client=self.vision_client, interval=7.0)

        # Set by BaseCharacter._start_hive() only on role="core" nodes.
        self.hive_core = None

        # Reflection scheduler: coordinates perception and reflection intervals
        # Will be created in _setup_scheduler() after agent is initialized
        self.reflection_scheduler: Optional[ReflectionScheduler] = None
        self.orchestrator_timeout_s = 120.0  # configurable timeout for LLM processing

    def _setup_scheduler(self):
        """Initialize the reflection scheduler after agent is ready."""
        if self.reflection_scheduler is not None:
            return  # already set up

        async def perception_fn():
            await self.screen_watcher.maybe_capture()

        async def reflection_fn():
            await self._do_reflection()

        self.reflection_scheduler = ReflectionScheduler(
            perception_fn=perception_fn,
            reflection_fn=reflection_fn,
            perception_interval_s=1.0,
            reflection_interval_s=60.0,
            suggestion_cache_size=50,
        )
        # Trigger first perception/reflection immediately
        self.reflection_scheduler._perception_last_s = -float('inf')
        self.reflection_scheduler._reflection_last_s = -float('inf')

    async def StateMachineLogic(self, scheduler: Optional[ReflectionScheduler] = None):
        """
        Main state machine logic. Optionally accepts a scheduler for testing.
        If no scheduler provided, uses self.reflection_scheduler (created on first call).

        Do NOT call screen_watcher.maybe_capture directly - the scheduler handles that.
        """
        if self.agent is not None and getattr(self.agent, "isProcessingState", False):
            return

        try:
            # Set up scheduler on first call if not injected
            if scheduler is None:
                if self.reflection_scheduler is None:
                    self._setup_scheduler()
                scheduler = self.reflection_scheduler

            # Perception is gated by the scheduler; this returns immediately
            # if the interval hasn't elapsed (default 1s)
            await scheduler.maybe_perceive()

            # Reflection runs in background on its own interval (default 60s)
            # if no task is already in flight. This returns immediately if gated.
            await scheduler.maybe_reflect()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Never kill the daemon on a background-loop error, but do surface
            # it in the logs so a recurring failure is visible and debuggable
            # rather than silently swallowed.
            logger.exception("Error in autonomous StateMachineLogic: %s", e)

    async def _do_reflection(self):
        """Background reflection task: aggregate context and process with orchestrator."""
        try:
            # 1. Aggregate Context
            # The raw screenshot goes only to the local vision model, which
            # redacts sensitive content on the way out (see
            # modules/perception/screen_watcher.py). What comes back here is
            # already safe to hand to self.llm_client, cloud or not.
            screen_text = self.screen_watcher.get_summary()
            hive_summary = self.hive_core.get_hive_summary() if self.hive_core else None
            body_state = self.observation_module._body_state(self.agent)

            # Reusable context path (identity + mental state + goal/task +
            # available perception). This folds the same per-character
            # identity/manifest the tool layer resolves via active_character_id.
            from modules.context import assemble_autonomous_context
            world_state = assemble_autonomous_context(
                self.agent, screen_text=screen_text, hive_summary=hive_summary,
                body_state=body_state,
            )

            # Deterministically select the single explicit goal this turn should
            # focus on (an active/proposed non-terminal goal, drive-aware but
            # fully deterministic). Selection never creates/governs goals and may
            # be empty when nothing actionable exists - we then fall back to the
            # generic observe-and-suggest behavior exactly as before.
            goal_dec = None
            try:
                from modules.soul.goals.goal_selection import select_goal
                goal_dec = select_goal(
                    getattr(self.agent, "character_id", "sarah"),
                    drives=self.agent.soul.mental_state.drives,
                )
            except Exception:  # noqa: BLE001 - selection must never break the loop
                goal_dec = None

            selected = goal_dec["selected"] if goal_dec else None
            goal_focus = ""
            if selected:
                goal_focus = (
                    f"\n[SELECTED GOAL] (deterministic focus for this turn)\n"
                    f"{selected['title']} [{selected['status']}, priority "
                    f"{selected['priority']}]\n"
                    f"why: {goal_dec['reason']}"
                )

            # Use the ToolOrchestrator for autonomous reasoning
            # Instead of fixed states, we ask her what she wants to do.
            # observe_only=True restricts her to a read-only observe
            # allowlist (policy, see ToolOrchestrator) - she may never act.
            from modules.tools.tool_orchestrator import ToolOrchestrator
            orchestrator = ToolOrchestrator(
                self.llm_client, agent=self.agent, observe_only=True,
            )

            prompt = (
                f"You are {self.agent.characterName} in your autonomous loop. "
                f"Current context:\n{world_state}\n"
                f"{goal_focus}\n\n"
                f"You observe ONLY, in service of the selected goal above (if a "
                f"goal is present). Look only for what might inform the next step "
                f"for that goal and suggest concrete next steps for it. If no "
                f"goal was selected, simply observe generally. If you spot "
                f"something worth reporting to the operator, say so clearly. You "
                f"do not take action on your own and you do not create, modify, "
                f"or complete goals; you only notice and suggest. What have you "
                f"observed / what next step do you suggest for the goal?"
            )

            # Wrap orchestrator processing in asyncio.wait_for with configurable timeout
            response_text = await asyncio.wait_for(
                orchestrator.process_request(prompt, system_context=world_state),
                timeout=self.orchestrator_timeout_s,
            )

            # De-duplicate suggestions: only log if not recently seen
            scheduler = self.reflection_scheduler
            if scheduler and not scheduler.is_duplicate_suggestion(response_text):
                print(f"[S.A.R.A.H. Autonomous]: {response_text}")
                scheduler.record_suggestion(response_text)
                # Persist this successful (non-duplicate) autonomous reflection
                # output to this character's bounded reflection journal
                # (system-written only; no registry/Discord exposure). The
                # goal_id (if any) is captured so the journal links the turn to
                # the goal it was in service of. Best-effort: a journal write
                # failure must never break the autonomous loop.
                self._persist_autonomous_reflection(response_text, goal_dec)
            elif scheduler:
                logger.debug(f"Suppressed duplicate reflection: {response_text[:80]}...")

        except asyncio.TimeoutError:
            logger.warning(f"Reflection timeout after {self.orchestrator_timeout_s}s")
        except Exception as e:
            logger.exception("Error in reflection task: %s", e)

    def _persist_autonomous_reflection(self, response_text: str, goal_dec) -> None:
        """Best-effort persistence of a successful autonomous reflection output.

        Only called for scheduler-deduplicated (i.e. not recently seen) output,
        so the journal holds distinct reflections rather than a flood of repeats.
        System-written only: the reflection journal is NOT a tool and is not
        exposed to the registry or Discord."""
        try:
            from modules.soul.reflection_log.reflection_log import (
                ENTRY_AUTONOMOUS,
                SOURCE_AUTONOMOUS_LOOP,
                get_reflection_log_store,
            )
            goal_id = None
            if isinstance(goal_dec, dict):
                selected = goal_dec.get("selected")
                if isinstance(selected, dict):
                    goal_id = selected.get("goal_id")
            store = get_reflection_log_store(getattr(self.agent, "character_id", "sarah"))
            store.append(
                kind=ENTRY_AUTONOMOUS,
                content=response_text,
                goal_id=goal_id,
                source=SOURCE_AUTONOMOUS_LOOP,
            )
        except Exception as e:  # noqa: BLE001 - journal write must never break the loop
            logger.warning("Could not persist autonomous reflection: %s", e)
