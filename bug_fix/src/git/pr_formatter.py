#!/usr/bin/env python3
"""
PR Formatter - Generate pull request descriptions and titles.

This module provides functions to format pull request descriptions
based on code changes and issue information.
"""

import re
from typing import List, Dict, Any, Optional
from pathlib import Path


def generate_pr_title(issue_title: str, changes_summary: str) -> str:
    """生成 PR 标题

    Args:
        issue_title: 原始 issue 标题
        changes_summary: 更改摘要

    Returns:
        PR 标题
    """
    # 移除常见的 issue 前缀
    clean_title = re.sub(r'^(bug|fix|feat|feature|enhancement|refactor|chore):\s*', '', issue_title, flags=re.IGNORECASE)

    # 如果标题太长，截断并添加省略号
    if len(clean_title) > 50:
        clean_title = clean_title[:47] + "..."

    return f"fix: {clean_title}"


def generate_pr_description(
    issue_title: str,
    issue_body: str,
    changes: List[Dict[str, Any]],
    repo_url: str,
    branch: str
) -> str:
    """生成 PR 描述

    Args:
        issue_title: Issue 标题
        issue_body: Issue 描述
        changes: 更改的文件列表
        repo_url: 仓库 URL
        branch: 分支名称

    Returns:
        PR 描述
    """
    # 提取仓库信息
    owner, repo = extract_github_repo_info(repo_url)
    if not owner or not repo:
        owner, repo = "unknown", "unknown"

    # 构建描述
    description_parts = []

    # 标题
    description_parts.append(f"## {issue_title}")
    description_parts.append("")

    # 问题描述
    if issue_body.strip():
        description_parts.append("### Problem")
        description_parts.append(issue_body.strip())
        description_parts.append("")

    # 更改摘要
    description_parts.append("### Changes")
    if changes:
        description_parts.append("Modified files:")
        for change in changes:
            file_path = change.get('file', 'unknown')
            description_parts.append(f"- `{file_path}`")
        description_parts.append("")

        # 统计信息
        total_files = len(changes)
        description_parts.append(f"**Total files changed:** {total_files}")
    else:
        description_parts.append("No files were modified.")
    description_parts.append("")

    # 相关链接
    description_parts.append("### Related")
    description_parts.append(f"- Repository: {repo_url}")
    description_parts.append(f"- Branch: `{branch}`")
    description_parts.append("")

    # 自动生成标签
    labels = infer_labels_from_changes(changes)
    if labels:
        description_parts.append("### Labels")
        description_parts.append(", ".join(f"`{label}`" for label in labels))
        description_parts.append("")

    return "\n".join(description_parts)


def infer_labels_from_changes(changes: List[Dict[str, Any]]) -> List[str]:
    """根据更改内容推断标签

    Args:
        changes: 更改的文件列表

    Returns:
        标签列表
    """
    labels = set()

    if not changes:
        return []

    # 分析文件类型
    file_extensions = []
    for change in changes:
        file_path = change.get('file', '')
        if '.' in file_path:
            ext = file_path.split('.')[-1].lower()
            file_extensions.append(ext)

    # 根据文件扩展名推断标签
    if any(ext in ['py', 'js', 'ts', 'java', 'cpp', 'c', 'go', 'rs'] for ext in file_extensions):
        labels.add('code')

    if any(ext in ['md', 'txt', 'rst'] for ext in file_extensions):
        labels.add('documentation')

    if any(ext in ['json', 'yaml', 'yml', 'toml', 'ini', 'cfg'] for ext in file_extensions):
        labels.add('configuration')

    if any(ext in ['test', 'spec'] for ext in ['py', 'js', 'ts', 'java'] if any(f'.{ext}' in ' '.join(file_extensions))):
        labels.add('testing')

    # 如果只有一种类型的文件，添加对应标签
    if len(set(file_extensions)) == 1:
        ext = list(set(file_extensions))[0]
        if ext == 'py':
            labels.add('python')
        elif ext in ['js', 'ts']:
            labels.add('javascript')
        elif ext == 'md':
            labels.add('documentation')

    return sorted(list(labels))


def extract_github_repo_info(repo_url: str) -> tuple[Optional[str], Optional[str]]:
    """从 GitHub URL 提取 owner 和 repo

    Args:
        repo_url: GitHub 仓库 URL

    Returns:
        Tuple[owner, repo]
    """
    match = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$', repo_url)
    if not match:
        return None, None

    owner = match.group(1)
    repo = match.group(2).replace('.git', '')
    return owner, repo


def format_file_changes_for_pr(changes: List[Dict[str, Any]]) -> str:
    """格式化文件更改信息用于 PR 描述

    Args:
        changes: 更改的文件列表

    Returns:
        格式化的更改描述
    """
    if not changes:
        return "No files were modified."

    lines = ["### Files Changed"]
    lines.append("")

    # 按文件类型分组
    by_type = {}
    for change in changes:
        file_path = change.get('file', 'unknown')
        if '.' in file_path:
            ext = file_path.split('.')[-1].lower()
        else:
            ext = 'other'

        if ext not in by_type:
            by_type[ext] = []
        by_type[ext].append(file_path)

    # 格式化输出
    for ext, files in sorted(by_type.items()):
        if ext == 'py':
            lines.append("**Python files:**")
        elif ext in ['js', 'ts']:
            lines.append("**JavaScript/TypeScript files:**")
        elif ext == 'md':
            lines.append("**Documentation:**")
        elif ext == 'json':
            lines.append("**Configuration:**")
        else:
            lines.append(f"**{ext.upper()} files:**")

        for file in sorted(files):
            lines.append(f"- `{file}`")
        lines.append("")

    # 统计信息
    total_files = len(changes)
    lines.append(f"**Total:** {total_files} file{'s' if total_files != 1 else ''} changed")

    return "\n".join(lines)