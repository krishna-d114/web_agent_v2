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

async def get_openai_tools(session: ClientSession) -> list[dict]:
    result = await session.list_tools()
    tools = [
        mcp_tool_to_openai_schema(t)
        for t in result.tools
        if t.name not in EXCLUDED_TOOLS
    ]

    # Synthetic tool: lets the LLM zoom into a specific memory entry it
    # saw in the index. Handled locally in main.py, not routed through MCP.
    tools.append({
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "Read the full content of a previously saved skill file, given its path from the memory index (e.g. 'youtube/play_video.md').",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    })

    # Synthetic tool: signals task completion. If successful, can
    # optionally include a new skill to save to memory.
    tools.append({
        "type": "function",
        "function": {
            "name": "mark_task_complete",
            "description": "Call this when the task has been fully completed, or when you determine it cannot be completed. If successful, optionally describe a reusable skill worth saving to memory for future tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "skill_site": {
                        "type": "string",
                        "description": "Lowercase site name, e.g. 'youtube', 'amazon'. Omit if nothing worth saving.",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Short filename-safe skill name, e.g. 'play_video'.",
                    },
                    "skill_type": {
                        "type": "string",
                        "enum": ["static_link", "url_pattern", "no_cache"],
                        "description": "static_link = one fixed reusable URL. url_pattern = templated URL with a substitutable term. no_cache = target changes over time, don't cache a link, just record the workflow.",
                    },
                    "skill_content": {
                        "type": "string",
                        "description": "Full markdown body for the skill file: what the task is, the Type, the link/pattern (if any), and notes on when/how to reuse it.",
                    },
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
