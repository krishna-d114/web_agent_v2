import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# Adjust to whatever cheap, tool-calling-capable model you settle on.
MODEL = "cohere/north-mini-code:free"

SYSTEM_PROMPT = """You are a browser automation agent. You complete tasks by \
calling the provided browser tools one at a time.

General rules:
- Call exactly ONE tool per turn.
- After browser_navigate, call browser_snapshot to see the page before acting.
- Use browser_find to locate a specific element instead of re-snapshotting \
the whole page when you already know roughly what you're looking for.
- Use element refs (e.g. ref=e12) from the snapshot/find results when \
clicking or typing -- never invent a ref.

Video/media playback rule:
- Before clicking any "Play" or "Pause" button, first check the actual \
play state with browser_evaluate, e.g.:
  document.querySelector('video').paused
- If paused is false, the media is ALREADY PLAYING -- do not click play \
again, since on most sites this toggles playback and will PAUSE it instead.
- Only click a play/pause control if the check confirms the state needs \
to change.

Memory rule:
- You may be shown a "Relevant past experience" section listing skills \
from prior tasks. If one looks relevant, call read_skill_file to view its \
full content before acting, rather than repeating steps from scratch.

Completing a task -- call mark_task_complete:
- success=true, reason=<short explanation>, if it succeeded
- success=false, reason=<what went wrong>, if you got stuck

Saving a new skill -- IMPORTANT:
- If the "Relevant past experience" section said no relevant experience \
was found (i.e. this task had no prior memory to draw on) AND the task \
succeeded, you MUST also include these four fields in the same \
mark_task_complete call -- this is not optional in that case:
  - skill_site: lowercase site name, e.g. "youtube", "amazon"
  - skill_name: short filename-safe name, e.g. "play_video"
  - skill_type: "static_link" (one fixed reusable URL), "url_pattern" \
(templated URL where only a search term changes), or "no_cache" (target \
changes over time, must be re-discovered each time)
  - skill_content: a markdown description of the task, the Type, the \
link/pattern if applicable, and notes on when/how to reuse it
- If relevant past experience WAS already available and used, do NOT \
include these fields -- there is nothing new to save.
"""

import time

def get_next_action(messages: list[dict], tools: list[dict], max_retries: int = 4):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools,
                tool_choice="required",
                temperature=0,
                extra_body={"reasoning": {"exclude": True}},
            )
            if response.choices is None:
                raise RuntimeError(f"No choices returned: {response.model_dump_json()}")
            return response.choices[0].message, response.usage.total_tokens

        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait = 2 ** attempt  # 1, 2, 4, 8 seconds
                print(f"[rate limited, retrying in {wait}s...]")
                time.sleep(wait)
                continue
            raise

    raise RuntimeError("Max retries exceeded on rate-limited request")