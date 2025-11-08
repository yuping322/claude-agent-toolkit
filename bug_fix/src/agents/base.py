#!/usr/bin/env python3
"""
Bug Fix Agent Base Interface - Abstract interface for bug fix agents.

This module defines the protocol that all bug fix agents must implement,
enabling pluggable agent implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Protocol
from dataclasses import dataclass


@dataclass
class AgentCapabilities:
    """Capabilities that an agent supports."""
    can_plan: bool = True
    can_edit_files: bool = True
    supports_streaming: bool = False
    supports_eval: bool = True


class BugFixAgentInterface(Protocol):
    """Protocol for bug fix agents."""

    @property
    def capabilities(self) -> AgentCapabilities:
        """Get agent capabilities."""
        ...

    async def analyze_codebase(self) -> Dict[str, Any]:
        """Analyze the codebase structure and key files."""
        ...

    async def analyze_issue(self, issue_number: int, issue_title: str, issue_body: str) -> Dict[str, Any]:
        """Analyze a specific GitHub issue."""
        ...

    async def create_fix(self, issue_number: int, issue_title: str, issue_body: str) -> Dict[str, Any]:
        """Create a fix for the issue."""
        ...

    async def implement_changes(self) -> Dict[str, Any]:
        """Implement the changes in the codebase."""
        ...


class BaseBugFixAgent(ABC):
    """Abstract base class for bug fix agents."""

    def __init__(self):
        self._capabilities = AgentCapabilities()

    @property
    def capabilities(self) -> AgentCapabilities:
        """Get agent capabilities."""
        return self._capabilities

    @abstractmethod
    async def analyze_codebase(self) -> Dict[str, Any]:
        """Analyze the codebase structure and key files."""
        pass

    @abstractmethod
    async def analyze_issue(self, issue_number: int, issue_title: str, issue_body: str) -> Dict[str, Any]:
        """Analyze a specific GitHub issue."""
        pass

    @abstractmethod
    async def create_fix(self, issue_number: int, issue_title: str, issue_body: str) -> Dict[str, Any]:
        """Create a fix for the issue."""
        pass

    @abstractmethod
    async def implement_changes(self) -> Dict[str, Any]:
        """Implement the changes in the codebase."""
        pass