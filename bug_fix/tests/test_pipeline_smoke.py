import pytest
from pathlib import Path
import tempfile
from executors import ExecutorFactory

@pytest.mark.asyncio
async def test_smoke_execute_prompt():
    ex = ExecutorFactory.create("claude-code", {})
    tmp = Path(tempfile.mkdtemp(prefix="bugfix-pipeline-"))
    stdout, code = await ex.execute(prompt="Create a TODO list in README.md", workspace_path=tmp)
    # Even if CLI missing, we expect a string output and an int code
    assert isinstance(stdout, str)
    assert isinstance(code, int)
    # Workspace should exist
    assert tmp.exists()
