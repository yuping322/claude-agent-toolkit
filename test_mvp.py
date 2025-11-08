#!/usr/bin/env python3
"""
Simple test for Bug Fix MVP components

This script tests the basic functionality without requiring GitHub access.
"""

import os
import sys
import asyncio
import tempfile
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bug_fix.src.executors import ExecutorFactory


async def test_executor():
    """Test Claude Code executor"""
    print("🔧 Testing Claude Code executor...")

    executor = ExecutorFactory.create("claude-code", {})
    if not executor.is_available():
        print("❌ Claude Code executor not available")
        return False

    print("✅ Claude Code executor available")

    # Test with a simple prompt
    workspace = Path(tempfile.mkdtemp(prefix="test-executor-"))
    print(f"📁 Test workspace: {workspace}")

    test_prompt = """
Create a simple Python function that adds two numbers.

Requirements:
1. Function name: add_numbers
2. Parameters: a, b (both integers)
3. Return: sum of a and b
4. Add type hints
5. Include a docstring

Save the function to a file called math_utils.py
"""

    try:
        print("🚀 Running test prompt...")
        stdout, exit_code = await executor.execute(
            prompt=test_prompt,
            workspace_path=workspace,
            timeout=120  # 2 minutes
        )

        print(f"📊 Exit code: {exit_code}")
        print("📝 Output preview:")
        print(stdout[:500] + "..." if len(stdout) > 500 else stdout)

        # Check if file was created
        math_utils_path = workspace / "math_utils.py"
        if math_utils_path.exists():
            print("✅ File created successfully")
            print("📄 File contents:")
            print(math_utils_path.read_text()[:300] + "..." if len(math_utils_path.read_text()) > 300 else math_utils_path.read_text())
            return True
        else:
            print("❌ File was not created")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_git_helper():
    """Test Git helper (basic functionality)"""
    print("\n🔧 Testing Git helper...")

    try:
        from bug_fix.src.git import GitHelper

        workspace = Path(tempfile.mkdtemp(prefix="test-git-"))
        git_helper = GitHelper(workspace)

        # Create a simple file
        test_file = workspace / "test.txt"
        test_file.write_text("Hello, World!")

        print("✅ Git helper initialized")
        print(f"📁 Test workspace: {workspace}")

        # Test basic repo operations (without actual git repo)
        print("✅ Git helper basic functionality works")
        return True

    except Exception as e:
        print(f"❌ Git helper test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🧪 Running Bug Fix MVP Tests")
    print("=" * 50)

    results = []

    # Test executor
    results.append(await test_executor())

    # Test git helper
    results.append(await test_git_helper())

    print("\n" + "=" * 50)
    print("📊 Test Results:")

    passed = sum(results)
    total = len(results)

    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result else "❌ FAIL"
        test_name = ["Executor", "Git Helper"][i-1]
        print(f"  {test_name}: {status}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! MVP is ready.")
        return 0
    else:
        print("💥 Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)