import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Parameters for spawning the Playwright MCP server as a subprocess.
# This is the exact same thing "npx @playwright/mcp@latest" does on the
# command line -- we're just letting the Python MCP SDK manage the
# subprocess lifecycle instead of running it manually.
SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["@playwright/mcp@latest"],
)


async def list_tools():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()

            print(f"\nConnected. {len(tools_result.tools)} tools available:\n")

            for tool in tools_result.tools:
                print(f"- {tool.name}")
                if tool.description:
                    first_line = tool.description.strip().split("\n")[0]
                    print(f"    {first_line}")

            return tools_result.tools


if __name__ == "__main__":
    asyncio.run(list_tools())