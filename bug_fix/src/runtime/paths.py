#!/usr/bin/env python3
"""
Runtime Paths - Path management and normalization utilities.

This module provides utilities for managing file paths across different
runtime environments (GitHub Actions, FC, CLI) with proper normalization.
"""

import os
from pathlib import Path
from typing import Optional, Union, List
from .environment import get_environment_config


class PathManager:
    """路径管理器"""

    def __init__(self):
        self.env_config = get_environment_config()
        self._workspace_path: Optional[Path] = None
        self._shared_repos_path: Optional[Path] = None

    @property
    def workspace_path(self) -> Path:
        """工作区路径"""
        if self._workspace_path is None:
            self._workspace_path = self.env_config.get_workspace_path()
        return self._workspace_path

    @property
    def shared_repos_path(self) -> Path:
        """共享仓库路径"""
        if self._shared_repos_path is None:
            self._shared_repos_path = self.env_config.get_shared_repos_path()
        return self._shared_repos_path

    def resolve_workspace_path(self, *path_components: Union[str, Path]) -> Path:
        """解析工作区内的路径"""
        return self.workspace_path.joinpath(*path_components).resolve()

    def resolve_shared_repo_path(self, repo_hash: str) -> Path:
        """解析共享仓库路径"""
        return self.shared_repos_path / repo_hash

    def normalize_path(self, path: Union[str, Path]) -> Path:
        """标准化路径"""
        path_obj = Path(path)
        if not path_obj.is_absolute():
            # 相对路径相对于工作区
            path_obj = self.workspace_path / path_obj
        return path_obj.resolve()

    def relative_to_workspace(self, path: Union[str, Path]) -> Path:
        """获取相对于工作区的路径"""
        abs_path = self.normalize_path(path)
        try:
            return abs_path.relative_to(self.workspace_path)
        except ValueError:
            # 如果无法相对化，返回绝对路径
            return abs_path

    def ensure_directory(self, path: Union[str, Path]) -> Path:
        """确保目录存在"""
        path_obj = self.normalize_path(path)
        path_obj.mkdir(parents=True, exist_ok=True)
        return path_obj

    def is_within_workspace(self, path: Union[str, Path]) -> bool:
        """检查路径是否在工作区内"""
        try:
            abs_path = self.normalize_path(path)
            abs_path.relative_to(self.workspace_path)
            return True
        except ValueError:
            return False

    def list_files(self, directory: Union[str, Path], pattern: str = "*") -> List[Path]:
        """列出目录中的文件"""
        dir_path = self.normalize_path(directory)
        if not dir_path.exists() or not dir_path.is_dir():
            return []

        return list(dir_path.glob(pattern))

    def get_repo_hash(self, repo_url: str) -> str:
        """生成仓库的唯一哈希（用于共享仓库路径）"""
        import hashlib
        # 移除可能的 token 和协议差异，生成一致的哈希
        normalized_url = repo_url
        if "@" in normalized_url:
            # 移除 token
            normalized_url = normalized_url.replace("@", "").split("://")[-1]
        normalized_url = normalized_url.replace("git@", "").replace("https://", "").replace("http://", "").replace(".git", "")
        hash_obj = hashlib.md5(normalized_url.encode())
        return hash_obj.hexdigest()[:16]


# 全局路径管理器实例
_path_manager: Optional[PathManager] = None


def get_path_manager() -> PathManager:
    """获取全局路径管理器实例"""
    global _path_manager
    if _path_manager is None:
        _path_manager = PathManager()
    return _path_manager


def resolve_workspace_path(*path_components: Union[str, Path]) -> Path:
    """解析工作区内的路径"""
    return get_path_manager().resolve_workspace_path(*path_components)


def resolve_shared_repo_path(repo_hash: str) -> Path:
    """解析共享仓库路径"""
    return get_path_manager().resolve_shared_repo_path(repo_hash)


def normalize_path(path: Union[str, Path]) -> Path:
    """标准化路径"""
    return get_path_manager().normalize_path(path)


def relative_to_workspace(path: Union[str, Path]) -> Path:
    """获取相对于工作区的路径"""
    return get_path_manager().relative_to_workspace(path)


def ensure_directory(path: Union[str, Path]) -> Path:
    """确保目录存在"""
    return get_path_manager().ensure_directory(path)


def is_within_workspace(path: Union[str, Path]) -> bool:
    """检查路径是否在工作区内"""
    return get_path_manager().is_within_workspace(path)


def list_files(directory: Union[str, Path], pattern: str = "*") -> List[Path]:
    """列出目录中的文件"""
    return get_path_manager().list_files(directory, pattern)


def get_repo_hash(repo_url: str) -> str:
    """生成仓库的唯一哈希"""
    return get_path_manager().get_repo_hash(repo_url)