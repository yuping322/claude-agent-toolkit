#!/usr/bin/env python3
"""
GitHub Actions Adapter - Integration with GitHub Actions environment.

This module provides the GitHubActionsAdapter class for handling
GitHub Actions specific functionality like issue parsing, PR creation,
and workflow management.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..runtime import ExecutionContext, get_environment_config
from ..git import GitHelper, generate_pr_title, generate_pr_description

logger = logging.getLogger(__name__)


class GitHubActionsAdapter:
    """GitHub Actions 适配器"""

    def __init__(self):
        self.env_config = get_environment_config()
        self.git_helper: Optional[GitHelper] = None

    def is_available(self) -> bool:
        """检查是否在 GitHub Actions 环境中"""
        return self.env_config.is_github_actions()

    def get_execution_context(self) -> ExecutionContext:
        """从 GitHub Actions 环境获取执行上下文"""
        from ..runtime import load_execution_context
        return load_execution_context("github_actions")

    def get_event_data(self) -> Optional[Dict[str, Any]]:
        """获取 GitHub 事件数据"""
        return self.env_config.get_github_event_data()

    def parse_issue_from_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """从事件数据解析 issue 信息"""
        issue_info = {
            "title": "",
            "body": "",
            "number": None,
            "url": "",
            "labels": []
        }

        # 处理 issues 事件
        if "issue" in event_data:
            issue = event_data["issue"]
            issue_info.update({
                "title": issue.get("title", ""),
                "body": issue.get("body", ""),
                "number": issue.get("number"),
                "url": issue.get("html_url", ""),
                "labels": [label["name"] for label in issue.get("labels", [])]
            })

        # 处理 pull_request 事件
        elif "pull_request" in event_data:
            pr = event_data["pull_request"]
            issue_info.update({
                "title": pr.get("title", ""),
                "body": pr.get("body", ""),
                "number": pr.get("number"),
                "url": pr.get("html_url", ""),
                "labels": [label["name"] for label in pr.get("labels", [])]
            })

        # 处理 workflow_dispatch 事件
        elif "inputs" in event_data:
            inputs = event_data["inputs"]
            issue_info.update({
                "title": inputs.get("issue_title", ""),
                "body": inputs.get("issue_body", ""),
                "number": inputs.get("issue_number"),
            })

        return issue_info

    def should_process_issue(self, issue_info: Dict[str, Any]) -> bool:
        """判断是否应该处理这个 issue"""
        # 检查是否是 bug 相关的标签
        bug_labels = ["bug", "fix", "bugfix", "defect", "issue"]
        labels = [label.lower() for label in issue_info.get("labels", [])]

        has_bug_label = any(label in bug_labels for label in labels)

        # 检查标题是否包含 bug 关键词
        title = issue_info.get("title", "").lower()
        has_bug_keywords = any(keyword in title for keyword in ["bug", "fix", "error", "issue"])

        return has_bug_label or has_bug_keywords

    def create_pull_request(self,
                          repo_url: str,
                          branch: str,
                          title: str,
                          body: str,
                          changes: List[Dict[str, Any]],
                          token: Optional[str] = None) -> Dict[str, Any]:
        """创建拉取请求"""
        try:
            import requests
        except ImportError:
            logger.error("requests library not available for GitHub API calls")
            return {"error": "requests library not available"}

        # 解析仓库信息
        owner, repo = self._extract_repo_info(repo_url)
        if not owner or not repo:
            return {"error": "Invalid repository URL"}

        # 准备 API 请求
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # 获取默认分支
        default_branch = self._get_default_branch(owner, repo, token) or "main"

        payload = {
            "title": title,
            "body": body,
            "head": branch,
            "base": default_branch
        }

        try:
            response = requests.post(api_url, json=payload, headers=headers)
            response.raise_for_status()

            pr_data = response.json()
            return {
                "success": True,
                "url": pr_data.get("html_url"),
                "number": pr_data.get("number"),
                "title": pr_data.get("title")
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create PR: {e}")
            return {"error": str(e)}

    def add_labels_to_pr(self,
                        repo_url: str,
                        pr_number: int,
                        labels: List[str],
                        token: Optional[str] = None) -> bool:
        """为 PR 添加标签"""
        try:
            import requests
        except ImportError:
            logger.error("requests library not available")
            return False

        owner, repo = self._extract_repo_info(repo_url)
        if not owner or not repo:
            return False

        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/labels"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            response = requests.post(api_url, json={"labels": labels}, headers=headers)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to add labels to PR: {e}")
            return False

    def comment_on_issue(self,
                        repo_url: str,
                        issue_number: int,
                        comment: str,
                        token: Optional[str] = None) -> bool:
        """在 issue 上发表评论"""
        try:
            import requests
        except ImportError:
            logger.error("requests library not available")
            return False

        owner, repo = self._extract_repo_info(repo_url)
        if not owner or not repo:
            return False

        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            response = requests.post(api_url, json={"body": comment}, headers=headers)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to comment on issue: {e}")
            return False

    def set_workflow_output(self, name: str, value: str):
        """设置 GitHub Actions workflow 输出"""
        if self.is_available():
            # 使用 GitHub Actions 的 set-output 命令
            os.system(f'echo "::set-output name={name}::{value}"')

    def upload_artifact(self, name: str, path: str):
        """上传 GitHub Actions artifact"""
        if self.is_available():
            # 这里可以实现 artifact 上传逻辑
            # 实际实现可能需要使用 actions/upload-artifact
            logger.info(f"Would upload artifact: {name} from {path}")

    def _extract_repo_info(self, repo_url: str) -> tuple[Optional[str], Optional[str]]:
        """从仓库 URL 提取 owner 和 repo"""
        import re
        match = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$', repo_url)
        if not match:
            return None, None
        return match.group(1), match.group(2)

    def _get_default_branch(self, owner: str, repo: str, token: Optional[str] = None) -> Optional[str]:
        """获取仓库的默认分支"""
        try:
            import requests
        except ImportError:
            return None

        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {
            "Authorization": f"token {token}" if token else "",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            repo_data = response.json()
            return repo_data.get("default_branch")
        except requests.exceptions.RequestException:
            return None