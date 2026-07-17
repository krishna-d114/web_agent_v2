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
- When the task is fully done, call mark_task_complete with success=true \
and a short reason. If you get stuck and cannot proceed, call \
mark_task_complete with success=false and explain why.
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
    return response.choices[0].message