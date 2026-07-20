import asyncio
import time
import uuid
import json

from agent.mcp_client import mcp_session, get_openai_tools, call_mcp_tool
from agent.llm import get_next_action, SYSTEM_PROMPT
from agent.logger import RunLogger
from agent import memory

MAX_STEPS = 15
TASK = input("tell the task: ")


async def run_task(task: str, arm: str = "with_memory"):
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    logger = RunLogger(run_id, task, arm)

    async with mcp_session() as session:
        tools = await get_openai_tools(session)

        memory_index = memory.get_memory_index(task) if arm == "with_memory" else "(memory disabled for this run)"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Task: {task}\n\nRelevant past experience (call read_skill_file to view full details on any entry):\n{memory_index}",
            },
        ]

        for step in range(1, MAX_STEPS + 1):
            assistant_msg, tokens_used = get_next_action(messages, tools)

            if not assistant_msg.tool_calls:
                print(f"[step {step}] No tool call returned, stopping")
                logger.finalize(False, "LLM returned no tool calls")
                await session.call_tool("browser_close", arguments={})
                return

            tool_call = assistant_msg.tool_calls[0]
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments) if isinstance(
                tool_call.function.arguments, str
            ) else tool_call.function.arguments

            print(f"[step {step}] {name}({arguments})")

            messages.append({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": [tool_call.model_dump()],
            })

            if name == "read_skill_file":
                result_text = memory.read_skill_file(arguments["path"])
                logger.log_step(step, name, arguments, result_text, tokens_used=tokens_used)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_text,
                })
                continue

            if name == "mark_task_complete":
                success = arguments.get("success", False)
                reason = arguments.get("reason", "")

                if success and arguments.get("skill_site") and arguments.get("skill_name"):
                    memory.save_skill(
                        task=task,
                        site=arguments["skill_site"],
                        skill_name=arguments["skill_name"],
                        skill_type=arguments.get("skill_type", "no_cache"),
                        content=arguments.get("skill_content", ""),
                    )

                summary = logger.finalize(success, reason)
                print(f"\nDone. success={summary['success']} steps={summary['num_steps']}")

                if success:
                    input("\nPress Enter to close the browser...")

                await session.call_tool("browser_close", arguments={})
                return

            result_text = await call_mcp_tool(session, name, arguments)
            logger.log_step(step, name, arguments, result_text, tokens_used=tokens_used)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            })

        print("Max steps reached without completion.")
        logger.finalize(False, "max_steps_reached")
        await session.call_tool("browser_close", arguments={})


if __name__ == "__main__":
    asyncio.run(run_task(TASK))