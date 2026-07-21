import json
import time
from pathlib import Path


class RunLogger:
    def __init__(self, run_id: str, task: str, arm: str):
        self.run_dir = Path("runs") / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.steps = []
        self.task = task
        self.arm = arm
        self.start_time = time.time()

        self.memory_available = False
        self.memory_files_read = []

    def set_memory_available(self, available: bool):
        self.memory_available = available

    def log_memory_file_read(self, path: str):
        self.memory_files_read.append(path)

    def log_step(self, step_num: int, tool_name: str, arguments: dict,
                 result_summary: str, tokens_used: int = 0):
        self.steps.append({
            "step": step_num,
            "tool": tool_name,
            "arguments": arguments,
            "result_summary": result_summary[:300],
            "tokens_used": tokens_used,
            "timestamp": time.time(),
        })

    def finalize(self, success: bool, reason: str):
        elapsed = time.time() - self.start_time

        summary = {
            "task": self.task,
            "arm": self.arm,
            "success": success,
            "reason": reason,
            "num_steps": len(self.steps),
            "total_tokens": sum(s["tokens_used"] for s in self.steps),
            "elapsed_seconds": round(elapsed, 2),
            "memory_available": self.memory_available,
            "memory_files_read": self.memory_files_read,
            "steps": self.steps,
        }

        with open(self.run_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        return summary