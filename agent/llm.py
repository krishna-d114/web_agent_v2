import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# Adjust to whatever cheap, tool-calling-capable model you settle on.
MODEL = "tencent/hy3:free"

SYSTEM_PROMPT = """You are a browser automation agent. You complete tasks by \
calling the provided browser tools one at a time.

Rules:
- Call exactly ONE tool per turn.
- After browser_navigate, call browser_snapshot to see the page before acting.
- Use browser_find to locate a specific element instead of re-snapshotting \
the whole page when you already know roughly what you're looking for.
- Use element refs (e.g. ref=e12) from the snapshot/find results when \
clicking or typing -- never invent a ref.
- You may be shown a "Relevant past experience" section listing skills \
from prior tasks. If one looks relevant, call read_skill_file to view its \
full content before acting, rather than repeating steps from scratch.

When the task is complete, call mark_task_complete:
- success=true, reason=<short explanation>, if it succeeded
- success=false, reason=<what went wrong>, if you got stuck

If successful, also decide whether this task revealed a reusable skill \
worth saving for next time. If so, include:
- skill_site: lowercase site name, e.g. "youtube", "amazon"
- skill_name: short filename-safe name, e.g. "play_video"
- skill_type: "static_link" if there's one fixed reusable URL (e.g. a \
channel page), "url_pattern" if there's a templated URL where only a \
search term changes (e.g. a site's search results URL), or "no_cache" if \
the correct target changes over time and must be re-discovered each time \
(e.g. "latest" release, live prices)
- skill_content: a short markdown description of the task, the Type, the \
link or pattern if applicable, and any notes on when/how to reuse it

Only include these fields if you genuinely learned something reusable -- \
omit them entirely if the task was one-off or too specific to generalize.
"""


def get_next_action(messages: list[dict], tools: list[dict]):
    """
    Sends the conversation so far to the LLM and returns its response.
    The caller is responsible for extracting tool_calls from it.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="required",
        temperature=0,
        extra_body={"reasoning": {"exclude": True}},
    )
    return response.choices[0].message,response.usage.total_tokens