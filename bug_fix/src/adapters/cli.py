#!/usr/bin/env python3
"""
CLI Adapter - Command Line Interface adapter.

This module provides the CLIAdapter class for handling
CLI-specific functionality like argument parsing, output formatting,
and interactive user experience.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from ..runtime import ExecutionContext, get_environment_config

logger = logging.getLogger(__name__)


class CLIAdapter:
    """CLI 适配器"""

    def __init__(self):
        self.env_config = get_environment_config()
        self.start_time: Optional[datetime] = None

    def is_available(self) -> bool:
        """检查是否在 CLI 环境中"""
        return self.env_config.is_cli()

    def get_execution_context(self) -> ExecutionContext:
        """从 CLI 参数获取执行上下文"""
        from ..runtime import load_execution_context
        return load_execution_context("cli")

    def print_header(self):
        """打印程序头部信息"""
        print("=" * 60)
        print("🤖 Bug Fix Agent - Automated Bug Fixing Platform")
        print("=" * 60)
        print()

    def print_configuration(self, context: ExecutionContext):
        """打印配置信息"""
        print("📋 Configuration:")
        print(f"  Repository: {context.repo_url}")
        print(f"  Branch: {context.branch}")
        print(f"  Agent: {context.agent_type}")
        print(f"  Executor: {context.executor_type}")
        print(f"  Worktree Mode: {context.worktree_mode}")
        if context.issue_title:
            print(f"  Issue: {context.issue_title}")
        print()

    def start_execution(self):
        """开始执行"""
        self.start_time = datetime.now()
        print("🚀 Starting bug fix execution...")
        print()

    def print_stage_start(self, stage_name: str):
        """打印阶段开始信息"""
        print(f"▶️  Starting stage: {stage_name}")
        print("-" * 40)

    def print_stage_complete(self, stage_name: str, duration: Optional[float] = None):
        """打印阶段完成信息"""
        duration_str = f" ({duration:.1f}s)" if duration else ""
        print(f"✅ Stage completed: {stage_name}{duration_str}")
        print()

    def print_stage_error(self, stage_name: str, error: str):
        """打印阶段错误信息"""
        print(f"❌ Stage failed: {stage_name}")
        print(f"   Error: {error}")
        print()

    def print_progress(self, message: str, progress: Optional[float] = None):
        """打印进度信息"""
        if progress is not None:
            print(f"📊 {message} ({progress:.1f}%)")
        else:
            print(f"📊 {message}")

    def print_fix_summary(self, fix_result: Dict[str, Any]):
        """打印修复摘要"""
        print("🔧 Fix Summary:")
        changes = fix_result.get("changes", [])
        if changes:
            print(f"  Files changed: {len(changes)}")
            for change in changes:
                file_path = change.get("file", "unknown")
                print(f"    - {file_path}")
        else:
            print("  No files were changed")
        print()

    def print_evaluation_result(self, evaluation: Dict[str, Any]):
        """打印评估结果"""
        print("📈 Evaluation Result:")
        success = evaluation.get("success", False)
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  Status: {status}")

        if "score" in evaluation:
            score = evaluation["score"]
            print(f"  Score: {score}/100")

        if "issues" in evaluation:
            issues = evaluation["issues"]
            if issues:
                print(f"  Issues found: {len(issues)}")
                for issue in issues[:3]:  # 只显示前3个问题
                    print(f"    - {issue}")
                if len(issues) > 3:
                    print(f"    ... and {len(issues) - 3} more")
        print()

    def print_pr_info(self, pr_result: Dict[str, Any]):
        """打印 PR 信息"""
        if "url" in pr_result:
            print("🔗 Pull Request Created:")
            print(f"  URL: {pr_result['url']}")
            if "number" in pr_result:
                print(f"  Number: #{pr_result['number']}")
            print()
        else:
            print("⚠️  Pull Request creation failed or was skipped")
            print()

    def print_execution_summary(self, results: Dict[str, Any]):
        """打印执行摘要"""
        print("=" * 60)
        print("📊 Execution Summary")
        print("=" * 60)

        total_stages = len(results)
        completed_stages = sum(1 for r in results.values() if r.get("status") == "completed")
        failed_stages = sum(1 for r in results.values() if r.get("status") == "failed")

        print(f"Total stages: {total_stages}")
        print(f"Completed: {completed_stages}")
        print(f"Failed: {failed_stages}")

        if self.start_time:
            total_duration = (datetime.now() - self.start_time).total_seconds()
            print(f"Total duration: {total_duration:.1f}s")
        print()

        # 打印各阶段状态
        print("Stage Details:")
        for stage_name, result in results.items():
            status = result.get("status", "unknown")
            duration = result.get("duration")
            duration_str = f" ({duration:.1f}s)" if duration else ""
            status_icon = {
                "completed": "✅",
                "failed": "❌",
                "cancelled": "⏭️",
                "running": "⏳"
            }.get(status, "❓")
            print(f"  {status_icon} {stage_name}: {status}{duration_str}")

        print()

    def print_error(self, message: str):
        """打印错误信息"""
        print(f"❌ Error: {message}", file=sys.stderr)

    def print_warning(self, message: str):
        """打印警告信息"""
        print(f"⚠️  Warning: {message}")

    def print_success(self, message: str):
        """打印成功信息"""
        print(f"✅ {message}")

    def prompt_confirmation(self, message: str) -> bool:
        """提示用户确认"""
        while True:
            response = input(f"🤔 {message} (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no', '']:
                return False
            else:
                print("Please enter 'y' or 'n'")

    def save_results_to_file(self, results: Dict[str, Any], output_file: Optional[str] = None):
        """保存结果到文件"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"bug_fix_results_{timestamp}.json"

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            print(f"💾 Results saved to: {output_file}")
        except Exception as e:
            self.print_error(f"Failed to save results: {e}")

    def load_config_from_file(self, config_file: str) -> Optional[Dict[str, Any]]:
        """从文件加载配置"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.print_error(f"Failed to load config file: {e}")
            return None

    def show_help(self):
        """显示帮助信息"""
        help_text = """
Bug Fix Agent - Automated Bug Fixing Platform

USAGE:
    python -m bug_fix [OPTIONS]

OPTIONS:
    --repo-url URL          GitHub repository URL
    --branch BRANCH         Branch name (default: main)
    --issue-title TITLE     Issue title
    --issue-body BODY       Issue description
    --issue-number NUMBER   Issue number
    --github-token TOKEN    GitHub token
    --agent TYPE            Agent type: claude, cursor, custom (default: claude)
    --executor TYPE         Executor type: claude_code, cursor, custom (default: claude_code)
    --no-worktree           Disable worktree mode
    --debug                 Enable debug mode
    --output FILE           Save results to file
    --config FILE           Load configuration from file
    --help                  Show this help message

EXAMPLES:
    # Basic usage
    python -m bug_fix --repo-url https://github.com/user/repo --issue-title "Fix login bug"

    # With GitHub token
    python -m bug_fix --repo-url https://github.com/user/repo --github-token ghp_xxx --issue-number 123

    # From config file
    python -m bug_fix --config bug_fix_config.json

CONFIG FILE FORMAT:
    {
        "repo_url": "https://github.com/user/repo",
        "branch": "main",
        "issue_title": "Bug title",
        "issue_body": "Bug description",
        "github_token": "ghp_xxx",
        "agent_type": "claude",
        "executor_type": "claude_code"
    }
        """
        print(help_text)

    def get_user_input(self, prompt: str, default: str = "") -> str:
        """获取用户输入"""
        if default:
            response = input(f"{prompt} (default: {default}): ").strip()
            return response if response else default
        else:
            return input(f"{prompt}: ").strip()