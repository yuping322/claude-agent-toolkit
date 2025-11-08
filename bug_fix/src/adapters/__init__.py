#!/usr/bin/env python3
"""
Adapters Module - Environment-specific adapters.

This module provides adapters for different runtime environments
(GitHub Actions, FC, CLI) to handle platform-specific functionality.
"""

from .github_actions import GitHubActionsAdapter
from .fc_service import FCServiceAdapter
from .cli import CLIAdapter

__all__ = [
    "GitHubActionsAdapter",
    "FCServiceAdapter",
    "CLIAdapter",
]