#!/usr/bin/env python3
# knowledge_base_examples.py - Examples of knowledge base implementations

"""
Examples showing how to standardize external knowledge base dependencies.

This module demonstrates different approaches to integrating knowledge bases:
1. Direct implementation of KnowledgeBaseInterface
2. MCP-wrapped external services
3. Hybrid approaches combining multiple sources
"""

import json
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from .knowledge_base import (
    KnowledgeBaseInterface,
    KnowledgeItem,
    SearchQuery,
    KnowledgeBaseTool,
    KnowledgeBaseRegistry
)
from .mcp import StdioMCPTool, HttpMCPTool


class InMemoryKnowledgeBase(KnowledgeBaseInterface):
    """
    Simple in-memory knowledge base for testing and small-scale use.

    This implementation stores knowledge items in memory and supports
    basic text-based search without vector embeddings.
    """

    def __init__(self):
        self._items: Dict[str, KnowledgeItem] = {}

    async def search(self, query: SearchQuery) -> List[KnowledgeItem]:
        """Basic text search implementation."""
        results = []
        query_lower = query.query.lower()

        for item in self._items.values():
            if query_lower in item.content.lower():
                # Simple scoring based on content length vs query length
                score = len(query.query) / len(item.content)
                scored_item = item.model_copy()
                scored_item.score = score
                results.append(scored_item)

        # Sort by score and limit results
        results.sort(key=lambda x: x.score or 0, reverse=True)
        return results[:query.limit]

    async def store(self, items: List[KnowledgeItem]) -> List[str]:
        """Store items in memory."""
        stored_ids = []
        for item in items:
            self._items[item.id] = item
            stored_ids.append(item.id)
        return stored_ids

    async def retrieve(self, item_ids: List[str]) -> List[KnowledgeItem]:
        """Retrieve items by ID."""
        return [self._items[item_id] for item_id in item_ids if item_id in self._items]

    async def delete(self, item_ids: List[str]) -> List[str]:
        """Delete items by ID."""
        deleted_ids = []
        for item_id in item_ids:
            if item_id in self._items:
                del self._items[item_id]
                deleted_ids.append(item_id)
        return deleted_ids

    async def count(self) -> int:
        """Get total item count."""
        return len(self._items)


class MCPKnowledgeBaseAdapter(KnowledgeBaseInterface):
    """
    Adapter that wraps external MCP knowledge base services.

    This adapter allows any MCP-compliant knowledge base service to be
    used through the standardized KnowledgeBaseInterface, regardless of
    whether it's stdio-based or HTTP-based.
    """

    def __init__(self, mcp_tool: StdioMCPTool | HttpMCPTool):
        """
        Initialize with an MCP tool instance.

        Args:
            mcp_tool: Configured MCP tool that provides knowledge base operations
        """
        self.mcp_tool = mcp_tool

    async def search(self, query: SearchQuery) -> List[KnowledgeItem]:
        """Search using MCP tool."""
        # This would call the actual MCP tool's search method
        # For now, return empty list as placeholder
        # In real implementation, you'd use the MCP protocol to call the tool
        return []

    async def store(self, items: List[KnowledgeItem]) -> List[str]:
        """Store using MCP tool."""
        # MCP tool call would go here
        return [item.id for item in items]

    async def retrieve(self, item_ids: List[str]) -> List[KnowledgeItem]:
        """Retrieve using MCP tool."""
        # MCP tool call would go here
        return []

    async def delete(self, item_ids: List[str]) -> List[str]:
        """Delete using MCP tool."""
        # MCP tool call would go here
        return item_ids

    async def count(self) -> int:
        """Count using MCP tool."""
        # MCP tool call would go here
        return 0


class FileSystemKnowledgeBase(KnowledgeBaseInterface):
    """
    File system-based knowledge base that stores items as JSON files.

    This implementation persists knowledge items to disk, making it
    suitable for small to medium-sized knowledge bases that need persistence.
    """

    def __init__(self, storage_path: str):
        """
        Initialize file system knowledge base.

        Args:
            storage_path: Directory path to store knowledge items
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _item_path(self, item_id: str) -> Path:
        """Get file path for a knowledge item."""
        return self.storage_path / f"{item_id}.json"

    async def search(self, query: SearchQuery) -> List[KnowledgeItem]:
        """Search through stored files."""
        results = []
        query_lower = query.query.lower()

        for item_file in self.storage_path.glob("*.json"):
            try:
                with open(item_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    item = KnowledgeItem(**data)

                    if query_lower in item.content.lower():
                        score = len(query.query) / len(item.content)
                        item.score = score
                        results.append(item)
            except Exception:
                continue  # Skip corrupted files

        results.sort(key=lambda x: x.score or 0, reverse=True)
        return results[:query.limit]

    async def store(self, items: List[KnowledgeItem]) -> List[str]:
        """Store items as JSON files."""
        stored_ids = []
        for item in items:
            item_path = self._item_path(item.id)
            with open(item_path, 'w', encoding='utf-8') as f:
                json.dump(item.model_dump(), f, indent=2, ensure_ascii=False)
            stored_ids.append(item.id)
        return stored_ids

    async def retrieve(self, item_ids: List[str]) -> List[KnowledgeItem]:
        """Retrieve items from files."""
        items = []
        for item_id in item_ids:
            item_path = self._item_path(item_id)
            if item_path.exists():
                try:
                    with open(item_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        items.append(KnowledgeItem(**data))
                except Exception:
                    continue
        return items

    async def delete(self, item_ids: List[str]) -> List[str]:
        """Delete item files."""
        deleted_ids = []
        for item_id in item_ids:
            item_path = self._item_path(item_id)
            if item_path.exists():
                item_path.unlink()
                deleted_ids.append(item_id)
        return deleted_ids

    async def count(self) -> int:
        """Count JSON files."""
        return len(list(self.storage_path.glob("*.json")))


def create_standardized_knowledge_bases():
    """
    Factory function to create standardized knowledge base tools.

    This demonstrates how different knowledge base implementations
    can be created and used interchangeably through the same interface.
    """

    # In-memory knowledge base for temporary use
    memory_kb = KnowledgeBaseTool.create(
        backend=InMemoryKnowledgeBase(),
        name="memory_kb"
    )

    # File system knowledge base for persistence
    fs_kb = KnowledgeBaseTool.create(
        backend=FileSystemKnowledgeBase("./knowledge_storage"),
        name="filesystem_kb"
    )

    # MCP-wrapped external knowledge base (placeholder)
    # In real usage, you would configure actual MCP servers
    # external_kb = KnowledgeBaseTool.create(
    #     backend=MCPKnowledgeBaseAdapter(
    #         StdioMCPTool(
    #             command="node",
    #             args=["external_kb_server.js"],
    #             name="external_kb"
    #         )
    #     ),
    #     name="external_kb"
    # )

    return {
        "memory": memory_kb,
        "filesystem": fs_kb,
        # "external": external_kb
    }


# Example usage with agent
async def example_usage():
    """
    Example showing how to use standardized knowledge bases with agents.
    """

    # Create knowledge base tools
    kb_tools = create_standardized_knowledge_bases()

    # Create agent with knowledge base tools
    from ..agent.core import Agent

    agent = Agent(
        oauth_token="your_token_here",
        tools=list(kb_tools.values())
    )

    # Example: Store some knowledge
    store_result = await agent.run("""
    Store the following information in the memory knowledge base:
    - Company policy: Remote work is allowed up to 3 days per week
    - Tech stack: We use Python, React, and PostgreSQL
    - Meeting schedule: Standups are at 9 AM daily
    """)

    # Example: Search for information
    search_result = await agent.run("""
    Search the knowledge base for information about our tech stack
    """)

    print("Knowledge base integration complete!")


if __name__ == "__main__":
    # Register backends in the registry
    KnowledgeBaseRegistry.register("memory", InMemoryKnowledgeBase)
    KnowledgeBaseRegistry.register("filesystem", FileSystemKnowledgeBase)

    # Run example
    asyncio.run(example_usage())</content>
<parameter name="filePath">/Users/fengzhi/Downloads/git/claude_code_sdk/claude-agent-toolkit/src/claude_agent_toolkit/tool/knowledge_base_examples.py