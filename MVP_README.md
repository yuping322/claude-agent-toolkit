# Bug Fix Agent - Minimal Viable Product (MVP)

This is a minimal viable product demonstrating the core functionality of the Bug Fix Agent system. It shows how to use Claude Code to automatically analyze, understand, and fix issues in codebases.

## Features

- 🐛 **Bug Detection & Fixing**: Automatically identify and fix bugs in code
- 🎨 **Code Generation**: Generate new code from natural language descriptions
- 🤖 **AI-Powered**: Uses Claude Code's advanced AI capabilities
- 🔧 **Extensible**: Modular design for easy extension to other agents
- 📊 **Observable**: Detailed logging and status tracking

## Quick Start

### Prerequisites

1. **Claude Code CLI**: Install from [Anthropic's website](https://docs.anthropic.com/claude/docs/desktop-setup)
2. **Python 3.12+**: Required for the agent toolkit
3. **Dependencies**: Install required packages:
   ```bash
   pip install claude-agent-sdk GitPython
   ```

### Environment Setup

Set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

### Run the Demo

```bash
# Run the MVP demo to see capabilities
python demo_mvp.py

# Run basic component tests
python test_mvp.py

# Run a simple bug fix example
python bug_fix/samples/sample_run.py --prompt "Add error handling to division function"
```

## Architecture

The MVP consists of three main components:

### 1. Executor (`bug_fix/executors.py`)
- **ClaudeCodeExecutor**: Uses Claude Code CLI via SDK
- **ExecutorFactory**: Creates appropriate executors
- **Multi-agent workflow**: Planner → Worker → Evaluator pattern

### 2. Agent Interface (`bug_fix/bug_fix_agent.py`)
- **BugFixAgentInterface**: Protocol for pluggable agents
- **ClaudeBugFixAgent**: Claude-based implementation
- **Factory pattern**: Easy agent swapping

### 3. Git Integration (`bug_fix/git_helpers.py`)
- **GitHelper**: Git operations using GitPython
- **Repository management**: Clone, pull, commit, push
- **PR creation**: Automated pull request generation

## Usage Examples

### Basic Bug Fix

```python
from bug_fix.executors import ExecutorFactory
import asyncio

async def fix_bug():
    executor = ExecutorFactory.create("claude-code", {})
    stdout, exit_code = await executor.execute(
        prompt="Fix the null pointer exception in user authentication",
        workspace_path=Path("./my-project")
    )
    print(f"Exit code: {exit_code}")
    print(stdout)

asyncio.run(fix_bug())
```

### Code Generation

```python
from bug_fix.executors import ExecutorFactory
import asyncio

async def generate_code():
    executor = ExecutorFactory.create("claude-code", {})
    stdout, exit_code = await executor.execute(
        prompt="Create a REST API endpoint for user registration with validation",
        workspace_path=Path("./api-project")
    )

asyncio.run(generate_code())
```

### Full Workflow (Planned)

```python
from mvp import BugFixMVP
import asyncio

async def full_workflow():
    mvp = BugFixMVP(github_token="your-token")

    if await mvp.initialize():
        success = await mvp.run_bug_fix(
            issue_url="https://github.com/owner/repo/issues/123",
            repo_url="https://github.com/owner/repo"
        )

asyncio.run(full_workflow())
```

## Configuration

### Environment Variables

- `ANTHROPIC_API_KEY`: Required for Claude Code
- `ANTHROPIC_BASE_URL`: Optional custom API endpoint
- `GITHUB_TOKEN`: Required for Git operations and PR creation

### Executor Configuration

```python
# Basic Claude Code executor
executor = ExecutorFactory.create("claude-code", {})

# Custom model
executor = ExecutorFactory.create("claude-code", {"model": "claude-sonnet-4-5-20250929"})

# Custom binary path
executor = ExecutorFactory.create("claude-code", {"binary_path": "/custom/path/claude"})
```

## Testing

Run the test suite:

```bash
# Component tests
python test_mvp.py

# Demo with real examples
python demo_mvp.py
```

## Limitations (MVP)

- Requires manual GitHub token setup
- No web interface (CLI only)
- Limited error recovery
- Single executor type (Claude Code only)
- No persistent state management

## Roadmap

The full system will include:

- 🌐 **Web Interface**: FastAPI-based REST API
- 🔄 **Multi-Environment**: GitHub Actions, FC, CLI support
- 🤖 **Multiple Agents**: Claude, Cursor, custom agents
- 📊 **Dashboard**: Real-time monitoring and logs
- 🔒 **Security**: Secrets detection and validation
- 🚀 **Scalability**: Distributed execution and queuing

## Contributing

This is an MVP demonstration. The full system is under development with comprehensive documentation, tests, and examples in the `docs/`, `tests/`, and `samples/` directories.

## License

MIT License - see LICENSE file for details.