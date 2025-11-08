#!/usr/bin/env python3
"""
Complete End-to-End Workflow Demo

This script demonstrates a complete development workflow using Claude Agent Toolkit:
1. Clone a repository from GitHub
2. Initialize the Claude Agent system
3. Use an agent to perform code analysis and modifications
4. Commit and push changes back to the repository

All steps are performed in a single Python script with proper error handling.
"""

import asyncio
import tempfile
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
import json
import time

from claude_agent_toolkit.system.initialize import initialize_system, get_agent_runtime
from claude_agent_toolkit.system.observability import EventBus, BaseEvent


class WorkflowEvent(BaseEvent):
    """Workflow-specific event."""
    phase: str
    status: str
    timestamp: float
from claude_agent_toolkit.tools.filesystem import FileSystemTool
from claude_agent_toolkit.tools.datatransfer import DataTransferTool


class CompleteWorkflow:
    """Complete end-to-end development workflow manager."""

    def __init__(self, repo_url: str, task_description: str, branch_name: str = "agent-improvements"):
        self.repo_url = repo_url
        self.task_description = task_description
        self.branch_name = branch_name
        self.work_dir: Optional[Path] = None
        self.repo_name = self._extract_repo_name(repo_url)
        self.agent_runtime = None
        self.event_bus = EventBus()
        self.workflow_events = []

    def _extract_repo_name(self, repo_url: str) -> str:
        """Extract repository name from URL."""
        return repo_url.split('/')[-1].replace('.git', '')

    async def _setup_event_monitoring(self):
        """Setup event monitoring for the workflow."""
        async def workflow_event_handler(event: WorkflowEvent):
            self.workflow_events.append(event)
            print(f"📊 Workflow: {event.phase} - {event.status}")
            if hasattr(event, 'data') and event.data:
                print(f"   Details: {event.data}")

        self.event_bus.subscribe("workflow", workflow_event_handler)

    async def _emit_workflow_event(self, phase: str, status: str, data: Optional[Dict[str, Any]] = None):
        """Emit a workflow event."""
        event = WorkflowEvent(
            event_type="workflow",
            phase=phase,
            status=status,
            data=data or {},
            timestamp=time.time()
        )
        await self.event_bus.publish("workflow", event)

    def _run_git_command(self, command: list, cwd: Optional[Path] = None) -> str:
        """Run a git command and return output."""
        try:
            result = subprocess.run(
                command,
                cwd=cwd or self.work_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise Exception(f"Git command failed: {' '.join(command)}\n{e.stderr}")

    def _run_command(self, command: list, cwd: Optional[Path] = None) -> str:
        """Run a shell command and return output."""
        try:
            result = subprocess.run(
                command,
                cwd=cwd or self.work_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise Exception(f"Command failed: {' '.join(command)}\n{e.stderr}")

    async def step_1_clone_repository(self):
        """Step 1: Clone the repository."""
        print("🔄 Step 1: Cloning repository...")
        await self._emit_workflow_event("clone", "starting")

        try:
            # Create temporary directory for the workflow
            self.work_dir = Path(tempfile.mkdtemp(prefix=f"workflow_{self.repo_name}_"))
            print(f"📁 Working directory: {self.work_dir}")

            # Clone the repository
            self._run_git_command(["git", "clone", self.repo_url, str(self.work_dir)])
            print(f"✅ Repository cloned: {self.repo_name}")

            # Check current branch
            current_branch = self._run_git_command(["git", "branch", "--show-current"])
            print(f"📋 Current branch: {current_branch}")

            await self._emit_workflow_event("clone", "completed", {
                "repo_name": self.repo_name,
                "working_dir": str(self.work_dir),
                "original_branch": current_branch
            })

        except Exception as e:
            await self._emit_workflow_event("clone", "failed", {"error": str(e)})
            raise

    async def step_2_create_feature_branch(self):
        """Step 2: Create a feature branch for our changes."""
        print("🔄 Step 2: Creating feature branch...")
        await self._emit_workflow_event("branch", "starting")

        try:
            # Create and switch to new branch
            self._run_git_command(["git", "checkout", "-b", self.branch_name])
            print(f"✅ Created and switched to branch: {self.branch_name}")

            # Verify branch
            current_branch = self._run_git_command(["git", "branch", "--show-current"])
            if current_branch != self.branch_name:
                raise Exception(f"Failed to switch to branch {self.branch_name}")

            await self._emit_workflow_event("branch", "completed", {
                "branch_name": self.branch_name
            })

        except Exception as e:
            await self._emit_workflow_event("branch", "failed", {"error": str(e)})
            raise

    async def step_3_initialize_agent_system(self):
        """Step 3: Initialize the Claude Agent system."""
        print("🔄 Step 3: Initializing Claude Agent system...")
        await self._emit_workflow_event("agent_init", "starting")

        try:
            # Create system configuration
            config_content = f"""
meta:
  environment: workflow_demo
  version: 1.0
logging:
  level: INFO
observability:
  enable: true
sandbox:
  default_strategy: subprocess
  strategies:
    subprocess:
      max_concurrency: 2
      hard_cpu_limit_pct: 80
      memory_limit_mb: 512
model_providers:
  workflow_provider:
    type: openrouter
    api_key: demo_key_12345
    base_url: https://openrouter.ai/api/v1
    model: anthropic/claude-3-haiku
mcp_services: {{}}
agents:
  code_analyzer:
    model_provider: workflow_provider
    dependency_pools: [workspace_pool]
dependency_pools:
  workspace_pool:
    type: filesystem
    paths: ["{self.work_dir}"]
tools:
  filesystem_tool:
    type: filesystem
    config:
      root_path: "{self.work_dir}"
  datatransfer_tool:
    type: datatransfer
    config:
      max_transfer_size: 1048576
"""

            # Write config to temporary file
            config_path = self.work_dir / "workflow_config.yaml"
            with open(config_path, 'w') as f:
                f.write(config_content)

            # Initialize the system
            await initialize_system(str(config_path))
            print("✅ Claude Agent system initialized")

            # Get agent runtime
            self.agent_runtime = get_agent_runtime("code_analyzer")
            print("✅ Agent runtime ready")

            await self._emit_workflow_event("agent_init", "completed", {
                "agent_name": "code_analyzer",
                "config_path": str(config_path)
            })

        except Exception as e:
            await self._emit_workflow_event("agent_init", "failed", {"error": str(e)})
            raise

    async def step_4_analyze_codebase(self):
        """Step 4: Analyze the codebase using the agent."""
        print("🔄 Step 4: Analyzing codebase...")
        await self._emit_workflow_event("analysis", "starting")

        try:
            # Get filesystem tool
            fs_tool = self.agent_runtime.get_tool("filesystem_tool")

            # List repository contents
            list_result = await fs_tool.execute("list_directory", {"path": str(self.work_dir)})
            if list_result.success:
                files = list_result.data.get("files", [])
                print(f"📂 Repository contains {len(files)} items")

                # Find Python files
                python_files = [f for f in files if f.get("name", "").endswith(".py")]
                print(f"🐍 Found {len(python_files)} Python files")

                # Analyze a sample file if available
                if python_files:
                    sample_file = python_files[0]["name"]
                    read_result = await fs_tool.execute("read_file", {"path": str(self.work_dir / sample_file)})
                    if read_result.success:
                        content = read_result.data["content"]
                        print(f"📖 Analyzed {sample_file} ({len(content)} characters)")

                        # Use agent to analyze the code
                        analysis_prompt = f"""
Analyze this Python file and suggest improvements:

File: {sample_file}
Content:
{content[:1000]}... (truncated for brevity)

Please provide:
1. Code quality assessment
2. Potential improvements
3. Best practices recommendations
"""

                        # For demo purposes, we'll simulate the analysis
                        # In real usage, this would call the model provider
                        print("🤖 Code analysis completed (simulated)")
                        analysis_result = {
                            "file": sample_file,
                            "quality_score": 85,
                            "recommendations": [
                                "Add type hints for better code clarity",
                                "Consider adding docstrings to functions",
                                "Add error handling for robustness"
                            ]
                        }

                        await self._emit_workflow_event("analysis", "completed", analysis_result)
                        return analysis_result
                    else:
                        print("⚠️  Could not read sample file")
                else:
                    print("⚠️  No Python files found for analysis")

            await self._emit_workflow_event("analysis", "completed", {"note": "No Python files to analyze"})

        except Exception as e:
            await self._emit_workflow_event("analysis", "failed", {"error": str(e)})
            raise

    async def step_5_implement_improvements(self):
        """Step 5: Implement code improvements."""
        print("🔄 Step 5: Implementing improvements...")
        await self._emit_workflow_event("implementation", "starting")

        try:
            # Create a simple improvement - add a README if it doesn't exist
            readme_path = self.work_dir / "README.md"
            if not readme_path.exists():
                readme_content = f"""# {self.repo_name}

This repository has been analyzed and improved by Claude Agent Toolkit.

## Recent Improvements

- Code analysis completed
- Documentation added
- Quality improvements implemented

## Workflow

This repository was processed using an automated workflow that:
1. Cloned the repository
2. Analyzed the codebase
3. Implemented improvements
4. Committed changes

## Development

To contribute to this project:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request
"""

                with open(readme_path, 'w') as f:
                    f.write(readme_content)

                print("✅ Added README.md with project documentation")

                # Create a simple utility script
                utils_path = self.work_dir / "utils.py"
                if not utils_path.exists():
                    utils_content = '''"""Utility functions for the project."""

import logging
from typing import Any, Dict

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def validate_config(config: Dict[str, Any]) -> bool:
    """Validate configuration dictionary."""
    required_keys = ['name', 'version']
    for key in required_keys:
        if key not in config:
            logger.error(f"Missing required config key: {key}")
            return False
    return True


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        return f"{seconds/60:.2f}m"
    else:
        return f"{seconds/3600:.2f}h"
'''

                    with open(utils_path, 'w') as f:
                        f.write(utils_content)

                    print("✅ Added utils.py with utility functions")

            await self._emit_workflow_event("implementation", "completed", {
                "files_created": ["README.md", "utils.py"],
                "improvements": ["Documentation", "Utility functions"]
            })

        except Exception as e:
            await self._emit_workflow_event("implementation", "failed", {"error": str(e)})
            raise

    async def step_6_commit_changes(self):
        """Step 6: Commit the changes."""
        print("🔄 Step 6: Committing changes...")
        await self._emit_workflow_event("commit", "starting")

        try:
            # Check git status
            status = self._run_git_command(["git", "status", "--porcelain"])
            if not status:
                print("⚠️  No changes to commit")
                await self._emit_workflow_event("commit", "skipped", {"reason": "no changes"})
                return

            print(f"📝 Changes to commit:\n{status}")

            # Add all changes
            self._run_git_command(["git", "add", "."])
            print("✅ Changes staged")

            # Create commit message
            commit_message = f"🤖 Agent improvements: {self.task_description}\n\n- Added comprehensive documentation\n- Implemented utility functions\n- Code quality improvements\n\nAutomated by Claude Agent Toolkit"

            # Commit changes
            self._run_git_command(["git", "commit", "-m", commit_message])
            print("✅ Changes committed")

            # Get commit hash
            commit_hash = self._run_git_command(["git", "rev-parse", "HEAD"])
            print(f"📋 Commit hash: {commit_hash}")

            await self._emit_workflow_event("commit", "completed", {
                "commit_hash": commit_hash,
                "commit_message": commit_message
            })

        except Exception as e:
            await self._emit_workflow_event("commit", "failed", {"error": str(e)})
            raise

    async def step_7_push_changes(self):
        """Step 7: Push changes to remote repository."""
        print("🔄 Step 7: Pushing changes...")
        await self._emit_workflow_event("push", "starting")

        try:
            # Push the branch
            self._run_git_command(["git", "push", "-u", "origin", self.branch_name])
            print(f"✅ Changes pushed to branch: {self.branch_name}")

            # Get remote URL for reference
            remote_url = self._run_git_command(["git", "remote", "get-url", "origin"])
            print(f"📡 Remote repository: {remote_url}")

            await self._emit_workflow_event("push", "completed", {
                "branch": self.branch_name,
                "remote_url": remote_url
            })

        except Exception as e:
            await self._emit_workflow_event("push", "failed", {"error": str(e)})
            raise

    async def step_8_cleanup(self):
        """Step 8: Cleanup temporary files."""
        print("🔄 Step 8: Cleaning up...")
        await self._emit_workflow_event("cleanup", "starting")

        try:
            if self.work_dir and self.work_dir.exists():
                # Note: In real usage, you might want to keep the directory for inspection
                # shutil.rmtree(self.work_dir)
                print(f"📁 Working directory preserved: {self.work_dir}")

            await self._emit_workflow_event("cleanup", "completed", {
                "working_dir": str(self.work_dir) if self.work_dir else None
            })

        except Exception as e:
            await self._emit_workflow_event("cleanup", "failed", {"error": str(e)})
            raise

    async def run_complete_workflow(self):
        """Run the complete workflow from start to finish."""
        print("🚀 Starting Complete Claude Agent Workflow")
        print("=" * 60)

        await self._setup_event_monitoring()

        try:
            # Execute all steps in sequence
            await self.step_1_clone_repository()
            await self.step_2_create_feature_branch()
            await self.step_3_initialize_agent_system()
            await self.step_4_analyze_codebase()
            await self.step_5_implement_improvements()
            await self.step_6_commit_changes()
            await self.step_7_push_changes()
            await self.step_8_cleanup()

            # Final summary
            print("\n🎉 Complete workflow finished successfully!")
            print("=" * 60)
            print("📊 Workflow Summary:")
            print(f"   Repository: {self.repo_name}")
            print(f"   Branch: {self.branch_name}")
            print(f"   Working Directory: {self.work_dir}")
            print(f"   Events Recorded: {len(self.workflow_events)}")

            # Show event summary
            successful_steps = sum(1 for e in self.workflow_events if e.status == "completed")
            total_steps = len([e for e in self.workflow_events if e.status in ["completed", "failed"]])
            print(f"   Success Rate: {successful_steps}/{total_steps} steps completed")

        except Exception as e:
            print(f"\n❌ Workflow failed: {e}")
            print("🔍 Check the error details above and try again")
            raise
        finally:
            # Always show final status
            print(f"\n📁 Working directory: {self.work_dir}")
            print("💡 You can inspect the changes in the working directory before cleanup")


async def main():
    """Main function to run the complete workflow."""

    # Configuration - you can modify these values
    REPO_URL = "https://github.com/octocat/Hello-World.git"  # Example repository (replace with real one)
    TASK_DESCRIPTION = "Add documentation and utility functions"
    BRANCH_NAME = "agent-improvements"

    print("🤖 Claude Agent Toolkit - Complete Workflow Demo")
    print("=" * 60)
    print(f"Repository: {REPO_URL}")
    print(f"Task: {TASK_DESCRIPTION}")
    print(f"Branch: {BRANCH_NAME}")
    print()
    print("⚠️  NOTE: This demo uses a mock workflow for demonstration purposes.")
    print("   To run with a real repository, ensure you have:")
    print("   - Git installed and configured")
    print("   - Access to the target repository")
    print("   - Proper authentication (SSH keys or tokens)")
    print()

    # For demo purposes, we'll run a simulated workflow
    # Uncomment the line below to run the real workflow
    # workflow = CompleteWorkflow(REPO_URL, TASK_DESCRIPTION, BRANCH_NAME)
    # await workflow.run_complete_workflow()

    print("🎯 This script demonstrates the complete workflow architecture.")
    print("💡 To run with a real repository, uncomment the workflow execution lines above.")
    print("🔧 Make sure to configure your repository URL and authentication first.")


if __name__ == "__main__":
    # Run the complete workflow
    asyncio.run(main())