import pytest
from pathlib import Path
import tempfile
from executors import ExecutorFactory

@pytest.mark.asyncio
async def test_claude_executor_availability():
    ex = ExecutorFactory.create("claude-code", {})
    assert ex.get_name() in {"claude-code", "claude"}
    # availability may be false in CI without CLI installed; just assert attribute exists
    assert hasattr(ex, 'is_available')

@pytest.mark.asyncio
async def test_execute_no_cli_graceful():
    ex = ExecutorFactory.create("claude-code", {})
    tmp = Path(tempfile.mkdtemp(prefix="bugfix-test-"))
    # If CLI not installed, should return informative error or non-zero code gracefully
    stdout, code = await ex.execute(prompt="Print hello", workspace_path=tmp)
    assert isinstance(stdout, str)
    assert isinstance(code, int)
