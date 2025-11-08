#!/usr/bin/env python3
# knowledge_base.py - Standardized knowledge base tools for agents

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

from .abstract import AbstractTool
from .base import BaseTool
from .decorator import tool
from ..logging import get_logger

logger = get_logger('knowledge_base')


class KnowledgeItem(BaseModel):
    """Standardized knowledge item structure."""
    id: str = Field(..., description="Unique identifier for the knowledge item")
    content: str = Field(..., description="The actual knowledge content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding if available")
    score: Optional[float] = Field(None, description="Relevance score for search results")


class SearchQuery(BaseModel):
    """Standardized search query structure."""
    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, description="Maximum number of results")
    threshold: Optional[float] = Field(None, description="Similarity threshold")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Additional filters")


class KnowledgeBaseInterface(ABC):
    """
    Abstract interface for knowledge base implementations.

    This interface defines the standard operations that all knowledge bases
    should support, allowing agents to work with different knowledge sources
    in a unified way.
    """

    @abstractmethod
    async def search(self, query: SearchQuery) -> List[KnowledgeItem]:
        """
        Search the knowledge base for relevant items.

        Args:
            query: Search query with text, limits, and filters

        Returns:
            List of relevant knowledge items with scores
        """
        pass

    @abstractmethod
    async def store(self, items: List[KnowledgeItem]) -> List[str]:
        """
        Store new knowledge items in the knowledge base.

        Args:
            items: Knowledge items to store

        Returns:
            List of IDs for the stored items
        """
        pass

    @abstractmethod
    async def retrieve(self, item_ids: List[str]) -> List[KnowledgeItem]:
        """
        Retrieve specific knowledge items by ID.

        Args:
            item_ids: IDs of items to retrieve

        Returns:
            List of knowledge items (may be fewer if some IDs not found)
        """
        pass

    @abstractmethod
    async def delete(self, item_ids: List[str]) -> List[str]:
        """
        Delete knowledge items by ID.

        Args:
            item_ids: IDs of items to delete

        Returns:
            List of IDs that were successfully deleted
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """
        Get the total number of items in the knowledge base.

        Returns:
            Total count of knowledge items
        """
        pass


class KnowledgeBaseTool(BaseTool):
    """
    Standardized MCP tool for knowledge base operations.

    This tool provides a unified interface for agents to interact with
    different types of knowledge bases (vector databases, document stores,
    external APIs, etc.) through a consistent MCP protocol.

    Features:
    - Standardized search, store, retrieve, delete operations
    - Support for different knowledge base backends
    - Automatic schema validation and error handling
    - Configurable through dependency injection

    Usage:
        # Create a knowledge base tool with a specific backend
        kb_tool = KnowledgeBaseTool.create(
            backend=VectorKnowledgeBase(connection_string="..."),
            name="company_docs"
        )

        # Use with agent
        agent = Agent(tools=[kb_tool])
        result = await agent.run("Search for information about our API")
    """

    def __init__(
        self,
        backend: KnowledgeBaseInterface,
        name: str = "knowledge_base",
        *,
        workers: Optional[int] = None,
        log_level: str = "ERROR"
    ):
        """
        Initialize the KnowledgeBaseTool with a specific backend.

        Args:
            backend: Knowledge base implementation
            name: Tool name identifier
            workers: Number of worker processes
            log_level: Logging level
        """
        self.backend = backend
        self._tool_name = name

        # Initialize BaseTool
        super().__init__(workers=workers, log_level=log_level)

    @classmethod
    def create(
        cls,
        backend: KnowledgeBaseInterface,
        name: str = "knowledge_base",
        **kwargs
    ) -> "KnowledgeBaseTool":
        """
        Factory method to create a KnowledgeBaseTool.

        Args:
            backend: Knowledge base implementation
            name: Tool name identifier
            **kwargs: Additional arguments for BaseTool

        Returns:
            Configured KnowledgeBaseTool instance
        """
        return cls(backend=backend, name=name, **kwargs)

    def name(self) -> str:
        """Get tool name."""
        return self._tool_name

    @tool()
    async def search_knowledge(
        self,
        query: str,
        limit: int = 10,
        threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search the knowledge base for relevant information.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            threshold: Minimum similarity score (0.0 to 1.0)
            filters: Additional metadata filters

        Returns:
            Dict containing search results and metadata
        """
        try:
            search_query = SearchQuery(
                query=query,
                limit=limit,
                threshold=threshold,
                filters=filters or {}
            )

            results = await self.backend.search(search_query)

            return {
                "success": True,
                "query": query,
                "total_results": len(results),
                "results": [
                    {
                        "id": item.id,
                        "content": item.content,
                        "metadata": item.metadata,
                        "score": item.score
                    }
                    for item in results
                ]
            }

        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query
            }

    @tool()
    async def store_knowledge(
        self,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Store new knowledge items in the knowledge base.

        Args:
            items: List of knowledge items to store. Each item should have:
                  - content: The knowledge content (required)
                  - metadata: Additional metadata (optional)
                  - id: Custom ID (optional, auto-generated if not provided)

        Returns:
            Dict containing storage results and assigned IDs
        """
        try:
            # Convert dicts to KnowledgeItem objects
            knowledge_items = []
            for item_dict in items:
                # Generate ID if not provided
                item_id = item_dict.get('id', f"kb_{hash(item_dict['content']):x}")

                knowledge_items.append(KnowledgeItem(
                    id=item_id,
                    content=item_dict['content'],
                    metadata=item_dict.get('metadata', {})
                ))

            stored_ids = await self.backend.store(knowledge_items)

            return {
                "success": True,
                "stored_count": len(stored_ids),
                "stored_ids": stored_ids
            }

        except Exception as e:
            logger.error(f"Knowledge base storage failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "attempted_count": len(items)
            }

    @tool()
    async def retrieve_knowledge(
        self,
        item_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Retrieve specific knowledge items by ID.

        Args:
            item_ids: List of knowledge item IDs to retrieve

        Returns:
            Dict containing retrieved items
        """
        try:
            items = await self.backend.retrieve(item_ids)

            return {
                "success": True,
                "requested_count": len(item_ids),
                "retrieved_count": len(items),
                "items": [
                    {
                        "id": item.id,
                        "content": item.content,
                        "metadata": item.metadata
                    }
                    for item in items
                ]
            }

        except Exception as e:
            logger.error(f"Knowledge base retrieval failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "requested_ids": item_ids
            }

    @tool()
    async def delete_knowledge(
        self,
        item_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Delete knowledge items by ID.

        Args:
            item_ids: List of knowledge item IDs to delete

        Returns:
            Dict containing deletion results
        """
        try:
            deleted_ids = await self.backend.delete(item_ids)

            return {
                "success": True,
                "requested_count": len(item_ids),
                "deleted_count": len(deleted_ids),
                "deleted_ids": deleted_ids
            }

        except Exception as e:
            logger.error(f"Knowledge base deletion failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "requested_ids": item_ids
            }

    @tool()
    async def get_knowledge_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the knowledge base.

        Returns:
            Dict containing knowledge base statistics
        """
        try:
            total_count = await self.backend.count()

            return {
                "success": True,
                "total_items": total_count,
                "backend_type": self.backend.__class__.__name__
            }

        except Exception as e:
            logger.error(f"Knowledge base stats retrieval failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Registry for knowledge base backends
class KnowledgeBaseRegistry:
    """Registry for knowledge base backend implementations."""

    _backends: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, backend_class: type) -> None:
        """Register a knowledge base backend implementation."""
        cls._backends[name] = backend_class

    @classmethod
    def create_backend(cls, name: str, **kwargs) -> KnowledgeBaseInterface:
        """Create a knowledge base backend instance."""
        if name not in cls._backends:
            raise ValueError(f"Unknown knowledge base backend: {name}")
        return cls._backends[name](**kwargs)

    @classmethod
    def list_backends(cls) -> List[str]:
        """List available knowledge base backends."""
        return list(cls._backends.keys())


# Example backend implementations can be added here
# from .backends.vector_db import VectorKnowledgeBase
# from .backends.file_system import FileSystemKnowledgeBase
# from .backends.external_api import ExternalAPIKnowledgeBase

# KnowledgeBaseRegistry.register("vector_db", VectorKnowledgeBase)
# KnowledgeBaseRegistry.register("file_system", FileSystemKnowledgeBase)
# KnowledgeBaseRegistry.register("external_api", ExternalAPIKnowledgeBase)</content>
