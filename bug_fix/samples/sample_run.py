"""Minimal sample: run a single prompt locally using current executors.

Usage:
    python bug_fix/samples/sample_run.py --prompt "Add logging to git helper" \
        --repo https://github.com/example/repo.git --branch main

This sample will:
1. Prepare a RuntimeConfig-like dict (pre-migration)
2. Instantiate ClaudeCodeExecutor (if available)
3. Execute prompt inside a temp workspace
4. Print stdout and exit code
"""
from pathlib import Path
import tempfile
import argparse
import os
from executors import ExecutorFactory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--repo", required=False)
    parser.add_argument("--branch", default="main")
    args = parser.parse_args()

    workspace = Path(tempfile.mkdtemp(prefix="bugfix-sample-"))
    print(f"[workspace] {workspace}")

    executor = ExecutorFactory.create("claude-code", {})
    if not executor.is_available():
        print("Executor not available (install claude-code CLI first).")
        return

    stdout, code = os.environ.get("PYTHONASYNCIODEBUG") or __import__("asyncio").run(
        executor.execute(prompt=args.prompt, workspace_path=workspace)
    )
    print("--- stdout ---")
    print(stdout)
    print(f"[exit_code] {code}")


if __name__ == "__main__":
    main()
