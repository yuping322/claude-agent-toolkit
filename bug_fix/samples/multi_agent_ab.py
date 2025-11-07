"""Demonstration of A/B execution with two executors or future agents.

Currently both use ClaudeCodeExecutor (placeholder). Future: swap in different agent types.
"""
import tempfile
from pathlib import Path
import asyncio
from executors import ExecutorFactory

PROMPT = "Refactor git helper to add retry logic on network errors"

async def run_one(tag: str, prompt: str):
    workspace = Path(tempfile.mkdtemp(prefix=f"ab-{tag}-"))
    ex = ExecutorFactory.create("claude-code", {})
    if not ex.is_available():
        return tag, "(executor unavailable)", 1
    stdout, code = await ex.execute(prompt=prompt, workspace_path=workspace)
    return tag, stdout[:500], code

async def main():
    tasks = [run_one("A", PROMPT), run_one("B", PROMPT + " with more comments")]
    results = await asyncio.gather(*tasks)
    print("== A/B Results ==")
    for tag, out, code in results:
        print(f"[{tag}] exit={code}\n{out}\n---")

if __name__ == "__main__":
    asyncio.run(main())
