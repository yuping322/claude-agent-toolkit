#!/usr/bin/env python3
"""
Claude Bug Fix Agent - Claude-based implementation using Claude Agent Toolkit.

This module provides a Claude-based implementation of the BugFixAgentInterface.
"""

from typing import Dict, Any
from pathlib import Path
import sys

from .base import BaseBugFixAgent, AgentCapabilities

# Add src to path to import claude_agent_toolkit
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from claude_agent_toolkit import Agent, BaseTool, tool, ExecutorType


class ClaudeBugFixAgent(BaseBugFixAgent):
    """Claude-based implementation of bug fix agent using Claude Agent Toolkit."""

    def __init__(self, tools: list[BaseTool], workspace_path: str):
        super().__init__()
        self.workspace_path = Path(workspace_path)
        self.agent = Agent(
            system_prompt="""You are an expert software engineer who analyzes GitHub issues and creates fixes.

Your task is to:
1. Analyze the issue title and description carefully
2. Examine the codebase structure and understand the project
3. Identify the specific files and code that need to be modified
4. Create precise code changes to fix the issue
5. Test that your changes are correct and follow best practices
6. Provide clear explanations of what was changed

Focus on creating working solutions that:
- Fix the exact problem described in the issue
- Follow the project's existing code style and patterns
- Include appropriate error handling
- Don't break existing functionality

Be thorough and methodical in your analysis.""",
            tools=tools,
            model="sonnet",
            executor=ExecutorType.SUBPROCESS  # Use subprocess executor
        )

        # Update capabilities
        self._capabilities = AgentCapabilities(
            can_plan=True,
            can_edit_files=True,
            supports_streaming=False,
            supports_eval=True
        )

    async def analyze_codebase(self) -> Dict[str, Any]:
        """Analyze the codebase structure and key files."""
        analysis_prompt = """
Please analyze this codebase structure and key files to understand the project:

1. What type of project is this?
2. What are the main components/modules?
3. What coding patterns and conventions are used?
4. What dependencies and frameworks are involved?

Provide a brief summary of the project architecture.
"""
        return await self.agent.run(analysis_prompt)

    async def analyze_issue(self, issue_number: int, issue_title: str, issue_body: str) -> Dict[str, Any]:
        """Analyze a specific GitHub issue."""
        issue_analysis_prompt = f"""
Now analyze this specific GitHub issue:

ISSUE #{issue_number}
Title: {issue_title}
Description:
{issue_body}

Based on your understanding of the codebase, please:
1. What exactly is the problem described in this issue?
2. Which files are likely involved?
3. What type of fix is needed (bug fix, feature addition, documentation, etc.)?
4. What specific changes need to be made?

Be very specific about which files and functions need to be modified.
"""
        return await self.agent.run(issue_analysis_prompt)

    async def create_fix(self, issue_number: int, issue_title: str, issue_body: str) -> Dict[str, Any]:
        """Create a fix for the issue."""
        fix_prompt = f"""
Based on your analysis, please create a fix for this issue:

ISSUE #{issue_number}: {issue_title}

Please:
1. Identify the exact files that need to be modified
2. Show the specific code changes needed
3. Explain why these changes fix the problem
4. Ensure the changes follow the project's coding standards

If you need to examine specific files, use the available tools to read their contents first.
"""
        return await self.agent.run(fix_prompt)

    async def implement_changes(self) -> Dict[str, Any]:
        """Implement the changes in the codebase."""
        implementation_prompt = """
Now implement the fix you designed:

1. Use the modify_file tool to make the necessary code changes
2. Make sure each change is precise and correct
3. Test that the changes look right by reading the modified files

Remember to provide the exact old content and new content for each file modification.
"""
        return await self.agent.run(implementation_prompt)