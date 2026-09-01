"""
Fully hands-free entry point: say "Hey Jarvis" (see modules/audio/wake_word.py
for why not "Hey Sarah" yet), speak your request, and Sarah answers out loud.
No keyboard required.

Usage: python3 sarah_voice.py
"""
import asyncio
import logging
import sys

from agents.sarah import SarahAgent
from modules.audio.stt import SpeechToText
from modules.audio.tts import tts
from modules.audio.wake_word import DEFAULT_WAKE_WORD, WakeWordListener
from modules.llmClient import LLMClient
from modules.tools.init_tools import register_all_tools
from modules.tools.tool_orchestrator import ToolOrchestrator

logging.basicConfig(level=logging.INFO)


async def main():
    # Without this, stdout is fully block-buffered whenever it's not a
    # live terminal (e.g. run in the background with `>` redirected to a
    # log file) - every print() below would sit in memory and never reach
    # the log until the buffer filled or the process exited. That's why
    # "You: ..." / "S.A.R.A.H.: ..." never showed up when this ran as a
    # background process before.
    sys.stdout.reconfigure(line_buffering=True)

    print(f"=== S.A.R.A.H. Voice Mode === (say \"{DEFAULT_WAKE_WORD.replace('_', ' ').title()}\" to talk, Ctrl+C to quit)")

    agent = SarahAgent()
    llm_client = LLMClient.from_node_config()
    orchestrator = ToolOrchestrator(llm_client, agent=agent)
    register_all_tools()

    wake_word = WakeWordListener()
    stt = SpeechToText()

    while True:
        try:
            await wake_word.wait()
            print("Listening...")
            text = await stt.listen_and_transcribe()
            if not text.strip():
                print("(heard nothing usable)")
                continue

            print(f"You: {text}")
            response = await orchestrator.process_request(text)
            print(f"S.A.R.A.H.: {response}")
            await tts.speak(response)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.exception(f"Voice loop error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
