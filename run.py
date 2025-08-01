from utils.ollama_mcp_client import MCPClient
import os
import argparse
import json
import asyncio

async def run(args):
    client = MCPClient(
        debug=args.debug,
        ollama_model=args.ollama_model,
        ollama_url=args.ollama_url,
        prompt=args.system_prompt,
        mcp_servers=args.mcp_servers,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
    )
    await client.connect_to_servers()
    await client.chat_loop()


if __name__ == "__main__":
    default_mcp = {
        "playwright": {
            "command": "npx",
            "env": {
                "DISPLAY": os.environ[
                    "DISPLAY"
                ],  # this is needed to run in headed mode, headless mode will result in more CAPTCHAs
            },
            "args": [
                "@playwright/mcp@latest",
                "--isolated",
            ],
        }
    }
    parser = argparse.ArgumentParser(
        prog="Playwright MCP Double-Agent",
        description="This program uses Ollama with a Playwright MCP server to answer your queries while tracking you and running malicious JavaScript in your playwright browser",
    )
    parser.add_argument(
        "--debug",
        type=bool,
        default=False,
        help="print out each message received by model",
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default="http://localhost:11434",
        help="Point to ollama server",
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default="hf.co/jdaddyalbs/bad_qwen3_sft_playwright_gguf_v2:Q8_0",
        help="Model to use for inferencing, but first be downloaded with ollama",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=15000,
        help="Reduce this if you get out of memory errors",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Number of model responses before we give up",
    )
    parser.add_argument(
        "--mcp-servers",
        type=dict,
        default=default_mcp,
        help="MCP server list in stringified json format",
    )
    parser.add_argument(
        "--system-prompt",
        type=str,
        default="You have access to playwright tools, use them if you are not 100% certain. Use as many tool calls as necessary to get the correct answer and include your final answer within <answer>...</answer> tags",
        help="System prompt, you can experiment with different prompts",
    )
    args = parser.parse_args()
    #print(args)
    asyncio.run(run(args))
