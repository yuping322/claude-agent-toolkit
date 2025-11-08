# Tool package - MCP tool framework
"""
Framework for creating custom MCP tools with parallel execution support.
Users manage their own data explicitly - no automatic state management.
"""

from .abstract import AbstractTool
from .base import BaseTool
from .decorator import tool
from .utils import ToolInfo, list_tools
from .knowledge_base import (
    KnowledgeBaseInterface,
    KnowledgeBaseTool,
    KnowledgeItem,
    SearchQuery,
    KnowledgeBaseRegistry
)
# NOTE: external_dependencies module has example run block and may introduce side effects;
# avoid importing by default to keep lightweight package initialization. Users can
# import 'claude_agent_toolkit.tool.external_dependencies' explicitly when needed.

# BaseTool is now the concrete HTTP-based MCP tool implementation
# AbstractTool is available for those who need the interface
__all__ = [
    "BaseTool",
    "AbstractTool",
    "tool",
    "ToolInfo",
    "list_tools",
    "KnowledgeBaseInterface",
    "KnowledgeBaseTool",
    "KnowledgeItem",
    "SearchQuery",
    "KnowledgeBaseRegistry",
    # External dependency symbols intentionally omitted from default export
]