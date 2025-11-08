#!/usr/bin/env python3
"""
Runtime Context Loader - Context loading and configuration management.

This module provides utilities for loading execution context from various
sources (environment variables, config files, CLI arguments) and managing
runtime configuration.
"""

import os
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field

from .environment import get_environment_config, RuntimeEnvironment
from .paths import get_path_manager


@dataclass
class ExecutionContext:
    """执行上下文"""

    # 基本信息
    repo_url: str = ""
    branch: str = "main"
    issue_title: str = ""
    issue_body: str = ""
    issue_number: Optional[int] = None

    # 认证信息
    github_token: Optional[str] = None

    # 执行配置
    agent_type: str = "claude"  # claude, cursor, custom
    executor_type: str = "claude_code"  # claude_code, cursor, custom
    worktree_mode: bool = True

    # 路径配置
    workspace_path: Optional[Path] = None
    shared_repos_path: Optional[Path] = None

    # 调试和日志
    debug: bool = False
    log_level: str = "INFO"

    # 额外配置
    extra_config: Dict[str, Any] = field(default_factory=dict)


class ContextLoader:
    """上下文加载器"""

    def __init__(self):
        self.env_config = get_environment_config()
        self.path_manager = get_path_manager()

    def load_from_github_actions(self) -> ExecutionContext:
        """从 GitHub Actions 环境加载上下文"""
        context = ExecutionContext()

        # 从环境变量获取基本信息
        context.repo_url = f"https://github.com/{self.env_config.get('github.repository', '')}"
        context.branch = os.getenv("GITHUB_HEAD_REF", os.getenv("GITHUB_REF_NAME", "main"))
        context.github_token = self.env_config.get_github_token()

        # 从事件数据获取 issue 信息
        event_data = self.env_config.get_github_event_data()
        if event_data:
            self._extract_issue_from_event(context, event_data)

        # 设置路径
        context.workspace_path = self.path_manager.workspace_path
        context.shared_repos_path = self.path_manager.shared_repos_path

        return context

    def load_from_fc(self) -> ExecutionContext:
        """从 FC 环境加载上下文"""
        context = ExecutionContext()

        # FC 环境通常通过环境变量或配置文件传递参数
        # 这里可以从环境变量或 OSS 挂载的配置文件中读取

        # 基本配置
        context.repo_url = os.getenv("BUG_FIX_REPO_URL", "")
        context.branch = os.getenv("BUG_FIX_BRANCH", "main")
        context.issue_title = os.getenv("BUG_FIX_ISSUE_TITLE", "")
        context.issue_body = os.getenv("BUG_FIX_ISSUE_BODY", "")
        context.github_token = os.getenv("BUG_FIX_GITHUB_TOKEN", "")

        # 解析 issue number
        issue_number_str = os.getenv("BUG_FIX_ISSUE_NUMBER", "")
        if issue_number_str.isdigit():
            context.issue_number = int(issue_number_str)

        # 设置路径
        context.workspace_path = self.path_manager.workspace_path
        context.shared_repos_path = self.path_manager.shared_repos_path

        return context

    def load_from_cli_args(self) -> ExecutionContext:
        """从 CLI 参数加载上下文"""
        parser = self._create_argument_parser()
        args = parser.parse_args()

        context = ExecutionContext()

        # 基本信息
        context.repo_url = args.repo_url or ""
        context.branch = args.branch or "main"
        context.issue_title = args.issue_title or ""
        context.issue_body = args.issue_body or ""
        context.issue_number = args.issue_number

        # 认证信息
        context.github_token = args.github_token or os.getenv("GITHUB_TOKEN")

        # 执行配置
        context.agent_type = args.agent or "claude"
        context.executor_type = args.executor or "claude_code"
        context.worktree_mode = not args.no_worktree

        # 调试配置
        context.debug = args.debug
        context.log_level = "DEBUG" if args.debug else "INFO"

        # 设置路径
        context.workspace_path = self.path_manager.workspace_path
        context.shared_repos_path = self.path_manager.shared_repos_path

        return context

    def load_from_config_file(self, config_path: Union[str, Path]) -> ExecutionContext:
        """从配置文件加载上下文"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")

        context = ExecutionContext()

        # 从配置数据填充上下文
        for key, value in config_data.items():
            if hasattr(context, key):
                setattr(context, key, value)

        # 设置路径（如果配置中没有指定）
        if context.workspace_path is None:
            context.workspace_path = self.path_manager.workspace_path
        if context.shared_repos_path is None:
            context.shared_repos_path = self.path_manager.shared_repos_path

        return context

    def load_context(self, source: Optional[str] = None) -> ExecutionContext:
        """根据环境自动加载上下文"""
        if source == "github_actions" or self.env_config.is_github_actions():
            return self.load_from_github_actions()
        elif source == "fc" or self.env_config.is_fc():
            return self.load_from_fc()
        elif source == "cli":
            return self.load_from_cli_args()
        else:
            # 自动检测
            if self.env_config.is_github_actions():
                return self.load_from_github_actions()
            elif self.env_config.is_fc():
                return self.load_from_fc()
            else:
                return self.load_from_cli_args()

    def _create_argument_parser(self) -> argparse.ArgumentParser:
        """创建命令行参数解析器"""
        parser = argparse.ArgumentParser(description="Bug Fix Agent")

        # 仓库信息
        parser.add_argument("--repo-url", help="GitHub repository URL")
        parser.add_argument("--branch", default="main", help="Branch name (default: main)")

        # Issue 信息
        parser.add_argument("--issue-title", help="Issue title")
        parser.add_argument("--issue-body", help="Issue body/description")
        parser.add_argument("--issue-number", type=int, help="Issue number")

        # 认证
        parser.add_argument("--github-token", help="GitHub token")

        # 执行配置
        parser.add_argument("--agent", choices=["claude", "cursor", "custom"],
                          default="claude", help="Agent type (default: claude)")
        parser.add_argument("--executor", choices=["claude_code", "cursor", "custom"],
                          default="claude_code", help="Executor type (default: claude_code)")
        parser.add_argument("--no-worktree", action="store_true",
                          help="Disable worktree mode (clone directly)")

        # 调试
        parser.add_argument("--debug", action="store_true", help="Enable debug mode")

        return parser

    def _extract_issue_from_event(self, context: ExecutionContext, event_data: Dict[str, Any]):
        """从 GitHub 事件数据中提取 issue 信息"""
        # 处理 issues 事件
        if "issue" in event_data:
            issue = event_data["issue"]
            context.issue_title = issue.get("title", "")
            context.issue_body = issue.get("body", "")
            context.issue_number = issue.get("number")

        # 处理 pull_request 事件（如果需要处理 PR 中的 issue）
        elif "pull_request" in event_data:
            pr = event_data["pull_request"]
            # 从 PR 标题和描述中提取 issue 信息
            title = pr.get("title", "")
            body = pr.get("body", "")

            # 尝试从标题中提取 issue 信息
            if title:
                context.issue_title = title
            if body:
                context.issue_body = body

        # 处理 workflow_dispatch 事件（手动触发）
        elif "inputs" in event_data:
            inputs = event_data["inputs"]
            context.issue_title = inputs.get("issue_title", "")
            context.issue_body = inputs.get("issue_body", "")
            issue_number_str = inputs.get("issue_number", "")
            if issue_number_str and issue_number_str.isdigit():
                context.issue_number = int(issue_number_str)


def load_execution_context(source: Optional[str] = None) -> ExecutionContext:
    """加载执行上下文的便捷函数"""
    loader = ContextLoader()
    return loader.load_context(source)