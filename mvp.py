#!/usr/bin/env python3
"""
Minimal Viable Product (MVP) for Bug Fix Agent

This script demonstrates the core functionality of the bug fix agent:
1. Analyze a GitHub issue
2. Create a fix using Claude Code
3. Apply changes to a repository
4. Create a pull request

Usage:
    python mvp.py --issue-url "https://github.com/owner/repo/issues/123" --token "your_github_token"

Requirements:
- claude-agent-sdk
- GitPython
- ANTHROPIC_API_KEY environment variable
"""

import os
import sys
import argparse
import tempfile
import asyncio
from pathlib import Path
from typing import Optional

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bug_fix.src.bug_fix_agent import ClaudeBugFixAgent, create_bug_fix_agent
from bug_fix.src.executors import ExecutorFactory
from bug_fix.src.git import GitHelper, extract_github_repo_info


class BugFixMVP:
    """Minimal Viable Product for Bug Fix Agent"""

    def __init__(self, github_token: str, workspace_path: Optional[Path] = None):
        self.github_token = github_token
        self.workspace_path = workspace_path or Path(tempfile.mkdtemp(prefix="bugfix-mvp-"))

        # Initialize components
        self.executor = None
        self.agent = None
        self.git_helper = None

        print(f"🐛 Bug Fix MVP initialized")
        print(f"📁 Workspace: {self.workspace_path}")

    async def initialize(self) -> bool:
        """Initialize all components"""
        try:
            # Check Claude Code executor
            print("🔧 Checking Claude Code executor...")
            self.executor = ExecutorFactory.create("claude-code", {})
            if not self.executor.is_available():
                print("❌ Claude Code CLI not available. Please install it first.")
                print("   Visit: https://docs.anthropic.com/claude/docs/desktop-setup")
                return False
            print("✅ Claude Code executor ready")

            # Check environment variables
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("❌ ANTHROPIC_API_KEY not set")
                return False
            print("✅ Anthropic API key configured")

            # Initialize Git helper
            self.git_helper = GitHelper(self.workspace_path)
            print("✅ Git helper initialized")

            return True

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            return False

    async def run_bug_fix(
        self,
        issue_url: str,
        repo_url: Optional[str] = None,
        branch: str = "main"
    ) -> bool:
        """Run the complete bug fix workflow"""
        try:
            # Parse issue URL
            print(f"🎯 Processing issue: {issue_url}")

            # Extract repo info from issue URL if not provided
            if not repo_url:
                # Convert issue URL to repo URL
                # https://github.com/owner/repo/issues/123 -> https://github.com/owner/repo
                if "/issues/" in issue_url:
                    repo_url = issue_url.split("/issues/")[0]
                    print(f"📦 Inferred repo URL: {repo_url}")
                else:
                    print("❌ Could not infer repo URL from issue URL")
                    return False

            # Extract issue number
            if "/issues/" in issue_url:
                issue_number = int(issue_url.split("/issues/")[1])
            else:
                print("❌ Could not extract issue number from URL")
                return False

            print(f"📋 Issue #{issue_number}")

            # Step 1: Clone/pull repository
            print("📥 Setting up repository...")
            if not self.git_helper.pull_latest(repo_url, branch, self.github_token):
                print("❌ Failed to setup repository")
                return False
            print("✅ Repository ready")

            # Step 2: Create agent (placeholder - we'll use direct executor for MVP)
            print("🤖 Initializing bug fix agent...")

            # For MVP, we'll use a simple approach: analyze issue and create fix in one step
            analysis_prompt = f"""
Please analyze GitHub issue #{issue_number} and create a fix.

Issue URL: {issue_url}

Please:
1. Understand what the issue is about
2. Examine the codebase structure
3. Identify the files that need to be changed
4. Create the necessary code changes
5. Test that the changes work

Be specific about file paths and code changes needed.
"""

            print("🔍 Analyzing issue and creating fix...")
            stdout, exit_code = await self.executor.execute(
                prompt=analysis_prompt,
                workspace_path=self.workspace_path,
                timeout=600  # 10 minutes
            )

            if exit_code != 0:
                print(f"❌ Analysis failed (exit code: {exit_code})")
                print("Output:", stdout[:500])
                return False

            print("✅ Analysis completed")
            print("📝 Analysis output preview:")
            print(stdout[:300] + "..." if len(stdout) > 300 else stdout)

            # Step 3: Check for changes
            if not self.git_helper._has_pending_changes():
                print("⚠️  No changes were made. The issue might already be fixed or no changes needed.")
                return True

            # Step 4: Validate changes
            print("🔍 Validating changes...")
            changed_files = []
            result = self.git_helper._run_git_safe("status", "--porcelain")
            if result[0]:
                changed_files = [
                    line.split()[1] if len(line.split()) > 1 else line.split()[0]
                    for line in result[1].split('\n') if line.strip()
                ]

            if changed_files:
                is_valid, error_msg = self.git_helper.validate_changes(changed_files)
                if not is_valid:
                    print(f"⚠️  Validation issues: {error_msg}")
                    print("Continuing anyway for MVP demo...")

            # Step 5: Create commit and PR
            print("💾 Creating commit...")
            commit_sha = self.git_helper.commit_changes(f"Fix issue #{issue_number}")
            if not commit_sha:
                print("❌ No changes to commit")
                return False

            print(f"✅ Changes committed: {commit_sha[:8]}")

            # Step 6: Create feature branch and push
            print("🚀 Creating pull request...")
            feature_branch = f"fix-issue-{issue_number}"

            if not self.git_helper.create_feature_branch(feature_branch, branch):
                print("❌ Failed to create feature branch")
                return False

            # Stage and commit changes again on the feature branch
            self.git_helper.stage_files(changed_files)
            commit_sha = self.git_helper.commit_changes(f"Fix issue #{issue_number}")

            if not self.git_helper.push_branch(feature_branch, "origin", self.github_token):
                print("❌ Failed to push branch")
                return False

            print(f"✅ Branch pushed: {feature_branch}")

            # Step 7: Create GitHub PR
            owner, repo = extract_github_repo_info(repo_url)
            if owner and repo:
                pr_url = await self._create_github_pr(owner, repo, issue_number, feature_branch, branch)
                if pr_url:
                    print(f"🎉 Pull Request created: {pr_url}")
                    return True

            print("✅ Bug fix workflow completed (no PR created)")
            return True

        except Exception as e:
            print(f"❌ Bug fix failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _create_github_pr(self, owner: str, repo: str, issue_number: int, head_branch: str, base_branch: str) -> Optional[str]:
        """Create GitHub Pull Request"""
        import requests

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        pr_data = {
            "title": f"Fix issue #{issue_number}",
            "body": f"Automated fix for issue #{issue_number}\n\nThis PR was created by the Bug Fix Agent MVP.",
            "head": head_branch,
            "base": base_branch
        }

        try:
            response = requests.post(api_url, json=pr_data, headers=headers, timeout=30)
            if response.status_code == 201:
                pr_info = response.json()
                return pr_info.get("html_url")
            else:
                print(f"❌ Failed to create PR: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ PR creation failed: {e}")
            return None


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Bug Fix Agent MVP")
    parser.add_argument("--issue-url", required=True, help="GitHub issue URL")
    parser.add_argument("--repo-url", help="GitHub repository URL (optional, inferred from issue URL)")
    parser.add_argument("--branch", default="main", help="Base branch (default: main)")
    parser.add_argument("--token", help="GitHub token (can also set GITHUB_TOKEN env var)")
    parser.add_argument("--workspace", help="Workspace directory (default: temp dir)")

    args = parser.parse_args()

    # Get GitHub token
    github_token = args.token or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("❌ GitHub token required. Use --token or set GITHUB_TOKEN environment variable.")
        return 1

    # Create workspace
    workspace_path = Path(args.workspace) if args.workspace else None

    # Initialize MVP
    mvp = BugFixMVP(github_token, workspace_path)

    if not await mvp.initialize():
        return 1

    # Run bug fix
    success = await mvp.run_bug_fix(
        issue_url=args.issue_url,
        repo_url=args.repo_url,
        branch=args.branch
    )

    if success:
        print("\n🎉 MVP completed successfully!")
        return 0
    else:
        print("\n💥 MVP failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)