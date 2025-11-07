#!/usr/bin/env python3
"""
Auto-fix GitHub issues using Claude Agent Toolkit.

This script analyzes GitHub issues and automatically creates pull requests
with fixes using the Claude Agent Toolkit framework.
"""

import os
import sys
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# Add src to path to import claude_agent_toolkit
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_agent_toolkit import Agent, BaseTool, tool, ExecutorType
from claude_agent_toolkit.tools import FileSystemTool

from bug_fix_agent import create_bug_fix_agent

import httpx


async def validate_environment():
    """Validate that all required tools and tokens are available."""
    print("🔍 Validating environment...")

    # Check required environment variables
    required_vars = ["GITHUB_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ISSUE_NUMBER"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ Missing required environment variables: {missing_vars}")
        return False

    # Check git is available
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
        print(f"✅ Git available: {result.stdout.strip()}")
    except subprocess.CalledProcessError:
        print("❌ Git is not available")
        return False

    # Check if we're in a git repository
    workspace = os.getenv("GITHUB_WORKSPACE", "/github/workspace")
    try:
        result = subprocess.run(["git", "status"], capture_output=True, cwd=workspace)
        if result.returncode == 0:
            print("✅ In a git repository")
        else:
            print("❌ Not in a git repository")
            return False
    except subprocess.CalledProcessError:
        print("❌ Cannot check git status")
        return False

    # Check Claude Code CLI
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, check=True)
        print(f"✅ Claude Code available: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Claude Code not available: {e}")
        return False

    print("✅ Environment validation passed")
    return True


class GitHubTool(BaseTool):
    """Tool for GitHub operations."""

    def __init__(self, token: str, repo: str):
        super().__init__()
        self.token = token
        self.repo = repo
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    @tool()
    async def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """Get issue details from GitHub."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{self.repo}/issues/{issue_number}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    @tool()
    async def create_branch(self, branch_name: str, base_branch: str = "main") -> Dict[str, Any]:
        """Create a new branch from base branch."""
        async with httpx.AsyncClient() as client:
            # Get the SHA of the base branch
            response = await client.get(
                f"{self.base_url}/repos/{self.repo}/git/refs/heads/{base_branch}",
                headers=self.headers
            )
            response.raise_for_status()
            base_sha = response.json()["object"]["sha"]

            # Create new branch
            response = await client.post(
                f"{self.base_url}/repos/{self.repo}/git/refs",
                headers=self.headers,
                json={
                    "ref": f"refs/heads/{branch_name}",
                    "sha": base_sha
                }
            )
            response.raise_for_status()
            return response.json()

    @tool()
    async def create_pull_request(self, title: str, body: str, head: str, base: str = "main") -> Dict[str, Any]:
        """Create a pull request."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/repos/{self.repo}/pulls",
                headers=self.headers,
                json={
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base
                }
            )
            response.raise_for_status()
            return response.json()


class CodeAnalysisTool(BaseTool):
    """Tool for analyzing and modifying code."""

    def __init__(self, workspace_path: str):
        super().__init__()
        self.workspace_path = Path(workspace_path)

        # Set up file system permissions for the entire workspace
        permissions = [
            ("**/*.py", "read"),
            ("**/*.md", "read"),
            ("**/*.txt", "read"),
            ("**/*.yml", "read"),
            ("**/*.yaml", "read"),
            ("**/*.json", "read"),
            ("**/*.toml", "read"),
            ("**/*", "write"),  # Allow writing to all files for fixes
        ]

        self.fs_tool = FileSystemTool(
            permissions=permissions,
            root_dir=str(self.workspace_path)
        )

    @tool()
    async def analyze_codebase(self) -> Dict[str, Any]:
        """Analyze the codebase structure and key files."""
        structure = {}

        # Get main directories
        dirs = ["src", "tests", "docs", "examples"]
        for dir_name in dirs:
            dir_path = self.workspace_path / dir_name
            if dir_path.exists():
                structure[dir_name] = [f for f in dir_path.rglob("*.py") if f.is_file()]

        # Read key files
        key_files = ["README.md", "pyproject.toml", "setup.py", "requirements.txt"]
        key_content = {}
        for file_name in key_files:
            file_path = self.workspace_path / file_name
            if file_path.exists():
                try:
                    key_content[file_name] = file_path.read_text()
                except Exception as e:
                    key_content[file_name] = f"Error reading file: {e}"

        return {
            "structure": structure,
            "key_files": key_content
        }

    @tool()
    async def search_code(self, query: str, file_pattern: str = "*.py") -> Dict[str, Any]:
        """Search for code patterns in the codebase."""
        results = []
        for file_path in self.workspace_path.rglob(file_pattern):
            if file_path.is_file():
                try:
                    content = file_path.read_text()
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            results.append({
                                "file": str(file_path.relative_to(self.workspace_path)),
                                "line": i,
                                "content": line.strip()
                            })
                except Exception as e:
                    continue

        return {"results": results[:50]}  # Limit results

    @tool()
    async def create_commit(self, message: str, files: list) -> Dict[str, Any]:
        """Create a git commit with the specified files."""
        try:
            # Add files to git
            for file_path in files:
                subprocess.run(["git", "add", file_path], check=True, cwd=self.workspace_path)

            # Commit changes
            subprocess.run(["git", "commit", "-m", message], check=True, cwd=self.workspace_path)

            # Get commit hash
            result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=self.workspace_path)
            commit_hash = result.stdout.strip()

            return {"success": True, "commit_hash": commit_hash}
        except subprocess.CalledProcessError as e:
            return {"error": f"Git command failed: {e}"}
        except Exception as e:
            return {"error": str(e)}

    @tool()
    async def push_branch(self, branch_name: str) -> Dict[str, Any]:
        """Push a branch to remote repository."""
        try:
            subprocess.run(["git", "push", "origin", branch_name], check=True, cwd=self.workspace_path)
            return {"success": True}
        except subprocess.CalledProcessError as e:
            return {"error": f"Git push failed: {e}"}
        except Exception as e:
            return {"error": str(e)}


async def main():
    """Main function to analyze issue and create PR."""

    # Validate environment first
    if not await validate_environment():
        sys.exit(1)

    # Get environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    claude_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
    issue_number = int(os.getenv("ISSUE_NUMBER", "0"))
    issue_title = os.getenv("ISSUE_TITLE", "")
    issue_body = os.getenv("ISSUE_BODY", "")
    repo = os.getenv("GITHUB_REPOSITORY")
    workspace = os.getenv("GITHUB_WORKSPACE", "/github/workspace")

    print(f"🔧 Processing issue #{issue_number}: {issue_title}")

    # Initialize tools
    github_tool = GitHubTool(github_token, repo)
    code_tool = CodeAnalysisTool(workspace)

    # Configure git
    subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], cwd=workspace)
    subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=workspace)

    # Create bug fix agent (easily replaceable with different agent implementations)
    bug_fix_agent = create_bug_fix_agent(
        agent_type="claude",  # Can be changed to other agent types in the future
        tools=[github_tool, code_tool],
        workspace_path=workspace
    )

    # Step 1: Analyze the codebase first
    print("Step 1: Analyzing codebase...")
    analysis_result = await bug_fix_agent.analyze_codebase()
    print("Codebase analysis:", analysis_result)

    # Step 2: Analyze the specific issue
    print("Step 2: Analyzing issue...")
    issue_analysis = await bug_fix_agent.analyze_issue(issue_number, issue_title, issue_body)
    print("Issue analysis:", issue_analysis)

    # Step 3: Create the fix
    print("Step 3: Creating fix...")
    fix_result = await bug_fix_agent.create_fix(issue_number, issue_title, issue_body)
    print("Fix created:", fix_result)

    # Step 4: Implement the changes
    print("Step 4: Implementing changes...")
    implementation_result = await bug_fix_agent.implement_changes()
    print("Changes implemented:", implementation_result)

    # Create branch and PR
    branch_name = f"fix-issue-{issue_number}"
    commit_message = f"Fix issue #{issue_number}: {issue_title}"
    pr_title = f"🤖 Auto-fix for issue #{issue_number}: {issue_title}"
    pr_body = f"""## 🤖 Automatically Generated Fix

This PR was automatically created to fix issue #{issue_number}.

### Issue Summary
**Issue:** [{issue_title}](https://github.com/{repo}/issues/{issue_number})

{issue_body}

### Changes Made
- Analyzed the codebase and identified the problem
- Implemented the necessary code changes
- Followed project coding standards and patterns

### Testing
Please review the changes and test them thoroughly before merging.

---
*Generated by Claude Agent Toolkit*
"""

    try:
        # Create and switch to new branch
        print(f"Creating branch: {branch_name}")
        subprocess.run(["git", "checkout", "-b", branch_name], check=True, cwd=workspace)

        # Add all changes
        subprocess.run(["git", "add", "."], check=True, cwd=workspace)

        # Check if there are changes to commit
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=workspace)
        if result.stdout.strip():
            # Commit changes
            subprocess.run(["git", "commit", "-m", commit_message], check=True, cwd=workspace)

            # Push branch
            subprocess.run(["git", "push", "origin", branch_name], check=True, cwd=workspace)

            # Try to create PR using GitHub API
            try:
                pr = await github_tool.create_pull_request(pr_title, pr_body, branch_name)
                print(f"✅ Created PR: {pr['html_url']}")
            except Exception as pr_error:
                print(f"⚠️  Could not create PR automatically: {pr_error}")
                print(f"📝 Please create a PR manually from branch '{branch_name}' to main")
                print(f"🔗 Branch URL: https://github.com/{repo}/tree/{branch_name}")
                print(f"📋 Suggested PR title: {pr_title}")
                print(f"📄 Suggested PR body:\n{pr_body}")
        else:
            print("❌ No changes to commit")

    except subprocess.CalledProcessError as e:
        print(f"❌ Git operation failed: {e}")
        print(f"Command: {e.cmd}")
        print(f"Return code: {e.returncode}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())