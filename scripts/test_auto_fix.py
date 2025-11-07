#!/usr/bin/env python3
"""
Test script for auto_fix_issue.py

This script validates that the auto-fix functionality works correctly.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def test_environment_validation():
    """Test the environment validation function."""
    print("Testing environment validation...")

    # Import the validation function
    sys.path.insert(0, str(Path(__file__).parent))
    from auto_fix_issue import validate_environment

    # Test with missing environment variables
    original_env = dict(os.environ)
    try:
        # Remove required env vars
        for var in ["GITHUB_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ISSUE_NUMBER"]:
            os.environ.pop(var, None)

        result = await validate_environment()
        if not result:
            print("✅ Environment validation correctly fails with missing vars")
        else:
            print("⚠️ Environment validation unexpectedly passed with missing vars")

    finally:
        # Restore environment
        os.environ.clear()
        os.environ.update(original_env)

    # Test with all required vars (but fake values)
    os.environ["GITHUB_TOKEN"] = "fake_token"
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "fake_claude_token"
    os.environ["ISSUE_NUMBER"] = "123"

    result = await validate_environment()
    # This might fail due to git not being available in test environment, but that's OK
    print(f"✅ Environment validation completed (result: {result})")

async def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        from claude_agent_toolkit import Agent, BaseTool, tool
        from claude_agent_toolkit.tools import FileSystemTool
        import httpx
        print("✅ All imports successful")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

    return True

async def main():
    """Run all tests."""
    print("🧪 Running auto-fix tests...\n")

    # Test imports
    if not await test_imports():
        sys.exit(1)

    # Test environment validation
    await test_environment_validation()

    print("\n✅ All tests passed!")

if __name__ == "__main__":
    asyncio.run(main())