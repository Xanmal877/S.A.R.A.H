import json
import logging
import os
from modules.tools.tool_registry import registry
from modules.tools.executor import executor
from modules.soul.identity_state.identity_state import active_character_id

logger = logging.getLogger("ToolOrchestrator")

class ToolOrchestrator:
    """
    Handles the multi-turn reasoning loop:
    1. Prompt LLM with context and available tools.
    2. Parse tool requests.
    3. Execute tools and return results.
    4. Loop until a final answer is provided.
    """
    def __init__(self, llm_client, agent=None, character_id: str = None, character_name: str = None,
                 allowed_tools: set = None):
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

    def _get_tool_definitions(self):
        tools = registry.list_tools()
        if self.allowed_tools is not None:
            tools = {name: desc for name, desc in tools.items() if name in self.allowed_tools}
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
                    f"To use a tool, respond ONLY with a JSON object:\n"
                    f'{{"tool": "tool_name", "args": {{"arg_name": "value"}}}}'
                    f"\nWhen you have the final answer or have completed the task, respond with:\n"
                    f'{{"final_answer": "Your response to the user"}}'
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
                start_idx = response_text.find('{')
                if start_idx == -1:
                    return f"LLM failed to provide structured response: {response_text}"
                try:
                    decision, _end = json.JSONDecoder().raw_decode(response_text, start_idx)
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse LLM response as JSON: {e}\nRaw: {response_text!r}")
                    return f"LLM failed to provide valid structured response: {response_text}"

                if "final_answer" in decision:
                    return decision["final_answer"]
                
                if "tool" in decision:
                    tool_name = decision["tool"]
                    args = decision.get("args", {})

                    if self.allowed_tools is not None and tool_name not in self.allowed_tools:
                        logger.warning(f"Blocked disallowed tool call: {tool_name}")
                        result = f"Error: tool '{tool_name}' is not permitted in this context."
                    else:
                        logger.info(f"Calling tool {tool_name} with {args}")
                        result = await executor.execute(tool_name, **args)
                    
                    # Append tool result to conversation
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "system", "content": f"Tool {tool_name} result: {result}"})
                    current_prompt = self._build_prompt(messages)
                else:
                    return f"LLM response missing 'tool' or 'final_answer': {response_text}"
                    
            except Exception as e:
                logger.exception(f"Error in reasoning cycle: {e}")
                return f"Error during reasoning: {str(e)}"

        return "Error: Maximum reasoning iterations reached without a final answer."

    def _build_prompt(self, messages):
        prompt = ""
        for msg in messages:
            prompt += f"{msg['role'].upper()}: {msg['content']}\n\n"
        return prompt
