#!/usr/bin/env python3
"""
Runtime Environment - Environment detection and configuration.

This module provides utilities for detecting the current runtime environment
(GitHub Actions, FC, CLI) and managing environment-specific configurations.
"""

import os
import json
from enum import Enum
from typing import Dict, Any, Optional
from pathlib import Path


class RuntimeEnvironment(Enum):
    """运行时环境枚举"""
    GITHUB_ACTIONS = "github_actions"
    FC = "fc"  # Function Compute
    CLI = "cli"  # Command Line Interface
    UNKNOWN = "unknown"


class EnvironmentConfig:
    """环境配置类"""

    def __init__(self):
        self.environment = self._detect_environment()
        self.config = self._load_config()

    def _detect_environment(self) -> RuntimeEnvironment:
        """检测当前运行环境"""
        # 检查 GitHub Actions 环境变量
        if os.getenv("GITHUB_ACTIONS") == "true":
            return RuntimeEnvironment.GITHUB_ACTIONS

        # 检查 FC 环境变量（阿里云 Function Compute）
        if os.getenv("FC_FUNC_CODE_PATH") or os.getenv("FC_RUNTIME"):
            return RuntimeEnvironment.FC

        # 检查 CLI 环境（默认）
        # 如果以上都不是，则认为是 CLI 环境
        return RuntimeEnvironment.CLI

    def _load_config(self) -> Dict[str, Any]:
        """加载环境配置"""
        config = {
            "environment": self.environment.value,
            "is_github_actions": self.environment == RuntimeEnvironment.GITHUB_ACTIONS,
            "is_fc": self.environment == RuntimeEnvironment.FC,
            "is_cli": self.environment == RuntimeEnvironment.CLI,
        }

        # GitHub Actions 特定配置
        if self.environment == RuntimeEnvironment.GITHUB_ACTIONS:
            config.update({
                "github": {
                    "workspace": os.getenv("GITHUB_WORKSPACE", ""),
                    "repository": os.getenv("GITHUB_REPOSITORY", ""),
                    "event_name": os.getenv("GITHUB_EVENT_NAME", ""),
                    "event_path": os.getenv("GITHUB_EVENT_PATH", ""),
                    "run_id": os.getenv("GITHUB_RUN_ID", ""),
                    "token": os.getenv("GITHUB_TOKEN", ""),
                }
            })

        # FC 特定配置
        elif self.environment == RuntimeEnvironment.FC:
            config.update({
                "fc": {
                    "func_code_path": os.getenv("FC_FUNC_CODE_PATH", ""),
                    "runtime": os.getenv("FC_RUNTIME", ""),
                    "instance_id": os.getenv("FC_INSTANCE_ID", ""),
                    "memory_size": os.getenv("FC_MEMORY_SIZE", ""),
                    "timeout": os.getenv("FC_TIMEOUT", ""),
                    "oss_mount_path": "/mnt/oss",  # 默认 OSS 挂载路径
                }
            })

        # CLI 特定配置
        else:
            config.update({
                "cli": {
                    "cwd": os.getcwd(),
                    "user": os.getenv("USER", ""),
                    "home": os.getenv("HOME", ""),
                }
            })

        return config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def is_github_actions(self) -> bool:
        """是否在 GitHub Actions 环境中"""
        return self.environment == RuntimeEnvironment.GITHUB_ACTIONS

    def is_fc(self) -> bool:
        """是否在 FC 环境中"""
        return self.environment == RuntimeEnvironment.FC

    def is_cli(self) -> bool:
        """是否在 CLI 环境中"""
        return self.environment == RuntimeEnvironment.CLI

    def get_workspace_path(self) -> Path:
        """获取工作区路径"""
        if self.is_github_actions():
            workspace = self.get("github.workspace")
            return Path(workspace) if workspace else Path.cwd()
        elif self.is_fc():
            # FC 环境使用 OSS 挂载路径作为工作区
            oss_path = self.get("fc.oss_mount_path", "/mnt/oss")
            return Path(oss_path)
        else:
            # CLI 环境使用当前目录
            return Path.cwd()

    def get_shared_repos_path(self) -> Path:
        """获取共享仓库路径"""
        if self.is_fc():
            # FC 环境使用 OSS 挂载路径下的 repos 目录
            oss_path = self.get("fc.oss_mount_path", "/mnt/oss")
            return Path(oss_path) / "repos"
        else:
            # 其他环境使用工作区父目录下的 repos
            workspace = self.get_workspace_path()
            return workspace.parent / "repos"

    def get_github_event_data(self) -> Optional[Dict[str, Any]]:
        """获取 GitHub Actions 事件数据"""
        if not self.is_github_actions():
            return None

        event_path = self.get("github.event_path")
        if not event_path or not Path(event_path).exists():
            return None

        try:
            with open(event_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def get_github_token(self) -> Optional[str]:
        """获取 GitHub token"""
        return self.get("github.token")

    def get_repository_info(self) -> Optional[Dict[str, str]]:
        """获取仓库信息"""
        if self.is_github_actions():
            repo = self.get("github.repository")
            if repo and "/" in repo:
                owner, name = repo.split("/", 1)
                return {"owner": owner, "name": name}
        return None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.config.copy()


# 全局环境配置实例
_env_config: Optional[EnvironmentConfig] = None


def get_environment_config() -> EnvironmentConfig:
    """获取全局环境配置实例"""
    global _env_config
    if _env_config is None:
        _env_config = EnvironmentConfig()
    return _env_config


def detect_environment() -> RuntimeEnvironment:
    """检测当前运行环境"""
    return get_environment_config().environment


def is_github_actions() -> bool:
    """是否在 GitHub Actions 环境中"""
    return get_environment_config().is_github_actions()


def is_fc() -> bool:
    """是否在 FC 环境中"""
    return get_environment_config().is_fc()


def is_cli() -> bool:
    """是否在 CLI 环境中"""
    return get_environment_config().is_cli()