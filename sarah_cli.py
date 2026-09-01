import asyncio
import sys

from agents.sarah import SarahAgent
from modules.audio.tts import tts
from modules.llmClient import LLMClient
from modules.tools.init_tools import register_all_tools
from modules.tools.tool_orchestrator import ToolOrchestrator


async def run_interactive():
    print("=== S.A.R.A.H. Resident AI System ===")
    print("Type 'exit' or 'quit' to leave.")

    # Initialize Agent and LLM
    agent = SarahAgent()
    llm_client = LLMClient.from_node_config()
    orchestrator = ToolOrchestrator(llm_client, agent=agent)

    # Ensure tools are registered
    register_all_tools()

    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue

            print("S.A.R.A.H. is thinking...", end="\r")
            response = await orchestrator.process_request(user_input)
            print(f"S.A.R.A.H.: {response}")
            await tts.speak(response)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

async def run_single_command(command):
    agent = SarahAgent()
    llm_client = LLMClient.from_node_config()
    orchestrator = ToolOrchestrator(llm_client, agent=agent)
    register_all_tools()
    
    response = await orchestrator.process_request(command)
    print(response)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Combine all arguments into a single command string
        cmd = " ".join(sys.argv[1:])
        asyncio.run(run_single_command(cmd))
    else:
        asyncio.run(run_interactive())
