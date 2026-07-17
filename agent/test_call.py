import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["@playwright/mcp@latest"],
)


async def test_call():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("Calling browser_navigate...")
            result = await session.call_tool(
                "browser_navigate",
                arguments={"url": "https://www.youtube.com"}
            )
            print("navigate result received.\n")

            print("Calling browser_snapshot...")
            snapshot = await session.call_tool("browser_snapshot", arguments={})

            text = snapshot.content[0].text
            print(f"Snapshot length: {len(text)} chars\n")
            print("First 1500 chars of snapshot:\n")
            print(text[:1500])

            await session.call_tool("browser_close", arguments={})


if __name__ == "__main__":
    asyncio.run(test_call())