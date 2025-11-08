#!/usr/bin/env python3
"""
Git Module - Git operations and PR formatting utilities.

This module provides Git repository management and pull request
formatting capabilities for the bug fix platform.
"""

from .helper import GitHelper, extract_github_repo_info
from .pr_formatter import (
    generate_pr_title,
    generate_pr_description,
    infer_labels_from_changes,
    format_file_changes_for_pr
)

__all__ = [
    # Git operations
    "GitHelper",
    "extract_github_repo_info",

    # PR formatting
    "generate_pr_title",
    "generate_pr_description",
    "infer_labels_from_changes",
    "format_file_changes_for_pr",
]