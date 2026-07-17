from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(
    command = "npx",
    args = ["@playwright/mcp@latest"],
)

EXCLUDED_TOOLS = {"browser_run_code_unsafe"}

@asynccontextmanager
async def mcp_session():
    """
    Opens one Playwright MCP session and keeps it alive for the
    duration of the `with` block. Everything inside shares the same
    browser -- no reopening between turns.
    """
    async with stdio_client(SERVER_PARAMS) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            yield session

def mcp_tool_to_openai_schema(tool) -> dict:
    """Converts one MCP tool definition into OpenAI's tool-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }

async def get_openai_tools(session: ClientSession)->list[dict]:
    """Fetches MCP tools and converts them, filtering out excluded ones."""
    result = await session.list_tools()
    tools = [
        mcp_tool_to_openai_schema(t)
        for t in result.tools
        if t.name not in EXCLUDED_TOOLS
    ]
    tools.append({
        "type": "function",
        "function": {
            "name": "mark_task_complete",
            "description": "Call this when the task has been fully completed, or when you determine it cannot be completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["success", "reason"],
            },
        },
    })

    return tools

async def call_mcp_tool(session:ClientSession,name:str,arguments:dict)->str:
    """calls a mcp tool and returns the result"""
    result = await session.call_tool(name,arguments = arguments)
    parts = [block.text for block in result.content if hasattr(block, "text")]
    return "\n".join(parts) if parts else "(no text content returned)"
