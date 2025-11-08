#!/usr/bin/env python3
"""
Bug Fix MVP Demo

This script demonstrates the minimal viable product for the bug fix agent.
It shows how to use the core components to fix a simple issue.

Usage:
    python demo_mvp.py

Requirements:
- ANTHROPIC_API_KEY environment variable set
- Claude Code CLI installed
"""

import os
import sys
import asyncio
import tempfile
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bug_fix.src.executors import ExecutorFactory


async def demo_simple_task():
    """Demonstrate a simple bug fix task"""
    print("🐛 Bug Fix MVP Demo")
    print("=" * 50)

    # Create a temporary workspace
    workspace = Path(tempfile.mkdtemp(prefix="mvp-demo-"))
    print(f"📁 Demo workspace: {workspace}")

    # Create a sample Python file with a bug
    buggy_file = workspace / "calculator.py"
    buggy_file.write_text("""def add_numbers(a, b):
    # This function has a bug - it subtracts instead of adds
    return a - b

def multiply_numbers(a, b):
    return a * b

# Test the functions
if __name__ == "__main__":
    print("2 + 3 =", add_numbers(2, 3))  # Should print 5, but prints -1
    print("2 * 3 =", multiply_numbers(2, 3))  # Should print 6
""")

    print("📝 Created buggy calculator.py file")
    print("🐛 Bug: add_numbers function subtracts instead of adds")

    # Create executor
    executor = ExecutorFactory.create("claude-code", {})
    if not executor.is_available():
        print("❌ Claude Code executor not available")
        return False

    # Fix the bug
    fix_prompt = """
Please fix the bug in calculator.py.

The add_numbers function is supposed to add two numbers, but it's currently subtracting them.
Change the subtraction operator (-) to addition operator (+) on line 3.

Also, add type hints to the function parameters and return type for better code quality.
"""

    print("🔧 Asking Claude Code to fix the bug...")
    stdout, exit_code = await executor.execute(
        prompt=fix_prompt,
        workspace_path=workspace,
        timeout=300  # 5 minutes
    )

    print(f"📊 Exit code: {exit_code}")
    print("📝 Claude Code output:")
    print("-" * 30)
    print(stdout[:1000] + "..." if len(stdout) > 1000 else stdout)
    print("-" * 30)

    # Check if the file was fixed
    if buggy_file.exists():
        fixed_content = buggy_file.read_text()
        print("📄 Fixed file content:")
        print("-" * 30)
        print(fixed_content)
        print("-" * 30)

        # Test if the bug is fixed
        if "return a + b" in fixed_content:
            print("✅ Bug fixed! Function now adds instead of subtracts")
        else:
            print("❌ Bug not fixed")

        # Check for type hints
        if ": int" in fixed_content and "-> int" in fixed_content:
            print("✅ Type hints added")
        else:
            print("⚠️  Type hints not added")

    return exit_code == 0


async def demo_code_generation():
    """Demonstrate code generation capability"""
    print("\n🤖 Code Generation Demo")
    print("=" * 50)

    workspace = Path(tempfile.mkdtemp(prefix="codegen-demo-"))
    print(f"📁 Demo workspace: {workspace}")

    executor = ExecutorFactory.create("claude-code", {})
    if not executor.is_available():
        print("❌ Claude Code executor not available")
        return False

    # Generate a simple utility module
    gen_prompt = """
Create a Python utility module called 'string_utils.py' with the following functions:

1. reverse_string(text: str) -> str: Reverse a string
2. is_palindrome(text: str) -> bool: Check if string is a palindrome (case-insensitive)
3. count_words(text: str) -> int: Count words in a string
4. capitalize_words(text: str) -> str: Capitalize first letter of each word

Include proper type hints, docstrings, and handle edge cases.
Add a main block that demonstrates all functions.
"""

    print("🎨 Generating string utilities module...")
    stdout, exit_code = await executor.execute(
        prompt=gen_prompt,
        workspace_path=workspace,
        timeout=300
    )

    print(f"📊 Exit code: {exit_code}")

    # Check generated file
    utils_file = workspace / "string_utils.py"
    if utils_file.exists():
        print("✅ string_utils.py created successfully")
        content = utils_file.read_text()
        print(f"📄 Generated {len(content)} characters of code")

        # Count functions
        function_count = content.count("def ")
        print(f"📋 Contains {function_count} functions")

        # Show a preview
        lines = content.split('\n')
        print("📝 Code preview (first 15 lines):")
        print("-" * 30)
        for i, line in enumerate(lines[:15]):
            print("2d")
        if len(lines) > 15:
            print("...")
        print("-" * 30)

    return exit_code == 0


async def main():
    """Run the MVP demo"""
    print("🚀 Bug Fix Agent - Minimal Viable Product Demo")
    print("This demo shows the core capabilities of the bug fix agent.")
    print()

    # Check environment
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY environment variable not set")
        print("   Please set it to run the demo")
        return 1

    results = []

    # Demo 1: Bug fixing
    results.append(await demo_simple_task())

    # Demo 2: Code generation
    results.append(await demo_code_generation())

    print("\n" + "=" * 50)
    print("📊 Demo Results:")

    passed = sum(results)
    total = len(results)

    demo_names = ["Bug Fixing", "Code Generation"]
    for i, result in enumerate(results):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {demo_names[i]}: {status}")

    print(f"\n🎯 Overall: {passed}/{total} demos successful")

    if passed == total:
        print("🎉 MVP demo completed successfully!")
        print("\n💡 The bug fix agent can:")
        print("   • Analyze and fix bugs in existing code")
        print("   • Generate new code from specifications")
        print("   • Work with various programming languages")
        print("   • Use Claude Code's powerful AI capabilities")
        print("\n🚀 Ready for integration into larger systems!")
        return 0
    else:
        print("💥 Some demos failed. Check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)