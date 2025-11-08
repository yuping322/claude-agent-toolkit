#!/usr/bin/env python3
"""
Runtime Module - Environment detection, path management, and context loading.

This module provides utilities for managing runtime environments, paths,
and execution contexts across different platforms (GitHub Actions, FC, CLI).
"""

from .environment import (
    RuntimeEnvironment,
    EnvironmentConfig,
    get_environment_config,
    detect_environment,
    is_github_actions,
    is_fc,
    is_cli
)

from .paths import (
    PathManager,
    get_path_manager,
    resolve_workspace_path,
    resolve_shared_repo_path,
    normalize_path,
    relative_to_workspace,
    ensure_directory,
    is_within_workspace,
    list_files,
    get_repo_hash
)

from .context_loader import (
    ExecutionContext,
    ContextLoader,
    load_execution_context
)

__all__ = [
    # Environment
    "RuntimeEnvironment",
    "EnvironmentConfig",
    "get_environment_config",
    "detect_environment",
    "is_github_actions",
    "is_fc",
    "is_cli",

    # Paths
    "PathManager",
    "get_path_manager",
    "resolve_workspace_path",
    "resolve_shared_repo_path",
    "normalize_path",
    "relative_to_workspace",
    "ensure_directory",
    "is_within_workspace",
    "list_files",
    "get_repo_hash",

    # Context
    "ExecutionContext",
    "ContextLoader",
    "load_execution_context",
]