import asyncio
from modules.llmClient import LLMClient
from modules.hive.config import load_config

async def main():
    cfg = load_config()
    client = LLMClient(model=cfg['model'], api_type=cfg['api_type'],
                       base_url=cfg['base_url'], num_ctx=cfg['num_ctx'])
    out = await client.generate_decision(
        'Respond with ONLY the JSON object: {"final_answer": "hi"}')
    print('===RAW MODEL OUTPUT===')
    print(repr(out[:600]))
    print()
    print('===ROUTE===')
    print(client.describe_runtime())

asyncio.run(main())
