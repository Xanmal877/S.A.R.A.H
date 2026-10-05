# ===============================
# DEMO USAGE
# ===============================

import asyncio

from agents.sarah import SarahAgent
from modules.llmClient import LLMClient
# Register the tool layer before the loop starts. modules/tools/init_tools.py
# auto-registers all 88 tools on import - but nothing in the daemon's import
# chain ever imported it, so the daemon's registry was EMPTY and every tool
# call the autonomous loop made failed with "Tool not found in registry."
# She could observe nothing and act on nothing. (The CLI and voice
# entrypoints call register_all_tools() explicitly; the daemon never did.)
import modules.tools.init_tools  # noqa: F401 - import side effect registers all tools


async def main():
    # Create S.A.R.A.H agent
    sarah = SarahAgent()

    # Startup diagnostic: configure reasoning runtime + whether its model
    # tag is cloud-routed. Pure config inspection - no network calls, no
    # prompt content (see LLMClient.describe_runtime).
    print("=== S.A.R.A.H Agent System Demo ===")
    print(LLMClient.from_node_config().describe_runtime())
    print(f"Personality: {sarah.personalityModule.personalityType}")
    print(f"Role: {sarah.personalityModule.role}")
    print(f"Strategy: {sarah.personalityModule.strategy}")
    print("=" * 40)
    
    # Run the agent (in real system, this would be the main loop)
    try:
        await sarah.Run()
    except KeyboardInterrupt:
        print(f"\n{sarah.characterName} shutting down...")

if __name__ == "__main__":
    asyncio.run(main())