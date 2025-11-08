#!/usr/bin/env python3
"""
Agent Registry - Dynamic registration and factory for bug fix agents.

This module provides a registry pattern for managing different agent implementations,
allowing easy extension and configuration of agents.
"""

from typing import Dict, Type, Any, Optional
from .base import BugFixAgentInterface
from .claude_agent import ClaudeBugFixAgent


class AgentRegistry:
    """Registry for bug fix agents with dynamic registration capabilities."""

    _agents: Dict[str, Type[BugFixAgentInterface]] = {}

    @classmethod
    def register(cls, name: str, agent_class: Type[BugFixAgentInterface]) -> None:
        """Register an agent implementation."""
        cls._agents[name] = agent_class

    @classmethod
    def get(cls, name: str) -> Type[BugFixAgentInterface]:
        """Get an agent class by name."""
        if name not in cls._agents:
            raise ValueError(f"Agent '{name}' not registered. Available agents: {list(cls._agents.keys())}")
        return cls._agents[name]

    @classmethod
    def list_agents(cls) -> list[str]:
        """List all registered agent names."""
        return list(cls._agents.keys())

    @classmethod
    def create_agent(cls, agent_type: str, **kwargs) -> BugFixAgentInterface:
        """Create an agent instance with the given parameters."""
        agent_class = cls.get(agent_type)
        return agent_class(**kwargs)


# Register built-in agents
AgentRegistry.register('claude', ClaudeBugFixAgent)


def create_bug_fix_agent(agent_type: str = "claude", **kwargs) -> BugFixAgentInterface:
    """
    Factory function to create bug fix agents.

    Args:
        agent_type: Type of agent to create
        **kwargs: Agent-specific initialization parameters

    Returns:
        BugFixAgentInterface: The created agent instance

    Example:
        agent = create_bug_fix_agent("claude", tools=my_tools, workspace_path="/path/to/workspace")
    """
    return AgentRegistry.create_agent(agent_type, **kwargs)