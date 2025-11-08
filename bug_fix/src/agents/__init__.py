#!/usr/bin/env python3
"""
Agents module - Bug fix agent implementations and registry.

This module provides pluggable agent implementations for bug fixing,
with a registry pattern for easy extension and configuration.
"""

from .base import BugFixAgentInterface, BaseBugFixAgent, AgentCapabilities
from .claude_agent import ClaudeBugFixAgent
from .registry import AgentRegistry, create_bug_fix_agent

__all__ = [
    'BugFixAgentInterface',
    'BaseBugFixAgent',
    'AgentCapabilities',
    'ClaudeBugFixAgent',
    'AgentRegistry',
    'create_bug_fix_agent',
]