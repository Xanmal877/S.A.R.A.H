# ===============================
# DEMO USAGE
# ===============================

import asyncio

from agents.sarah import SarahAgent


async def main():
    # Create S.A.R.A.H agent
    sarah = SarahAgent()
    
    print("=== S.A.R.A.H Agent System Demo ===")
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