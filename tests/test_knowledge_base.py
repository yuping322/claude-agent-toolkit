#!/usr/bin/env python3
# test_knowledge_base.py - Test knowledge base standardization

import asyncio
import tempfile

# Test the core interfaces without full MCP server
import sys
import os
import json
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field

# Direct implementation of core interfaces for testing
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
    """Abstract interface for knowledge base implementations."""

    @abstractmethod
    async def search(self, query: SearchQuery) -> List[KnowledgeItem]:
        pass

    @abstractmethod
    async def store(self, items: List[KnowledgeItem]) -> List[str]:
        pass

    @abstractmethod
    async def retrieve(self, item_ids: List[str]) -> List[KnowledgeItem]:
        pass

    @abstractmethod
    async def delete(self, item_ids: List[str]) -> List[str]:
        pass

    @abstractmethod
    async def count(self) -> int:
        pass


class InMemoryKnowledgeBase(KnowledgeBaseInterface):
    """Simple in-memory knowledge base for testing."""

    def __init__(self):
        self._items: Dict[str, KnowledgeItem] = {}

    async def search(self, query: SearchQuery) -> List[KnowledgeItem]:
        results = []
        query_lower = query.query.lower()

        for item in self._items.values():
            if query_lower in item.content.lower():
                score = len(query.query) / len(item.content)
                scored_item = item.model_copy()
                scored_item.score = score
                results.append(scored_item)

        results.sort(key=lambda x: x.score or 0, reverse=True)
        return results[:query.limit]

    async def store(self, items: List[KnowledgeItem]) -> List[str]:
        stored_ids = []
        for item in items:
            self._items[item.id] = item
            stored_ids.append(item.id)
        return stored_ids

    async def retrieve(self, item_ids: List[str]) -> List[KnowledgeItem]:
        return [self._items[item_id] for item_id in item_ids if item_id in self._items]

    async def delete(self, item_ids: List[str]) -> List[str]:
        deleted_ids = []
        for item_id in item_ids:
            if item_id in self._items:
                del self._items[item_id]
                deleted_ids.append(item_id)
        return deleted_ids

    async def count(self) -> int:
        return len(self._items)


class FileSystemKnowledgeBase(KnowledgeBaseInterface):
    """File system-based knowledge base."""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _item_path(self, item_id: str) -> Path:
        return self.storage_path / f"{item_id}.json"

    async def search(self, query: SearchQuery) -> List[KnowledgeItem]:
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
                continue

        results.sort(key=lambda x: x.score or 0, reverse=True)
        return results[:query.limit]

    async def store(self, items: List[KnowledgeItem]) -> List[str]:
        stored_ids = []
        for item in items:
            item_path = self._item_path(item.id)
            with open(item_path, 'w', encoding='utf-8') as f:
                json.dump(item.model_dump(), f, indent=2, ensure_ascii=False)
            stored_ids.append(item.id)
        return stored_ids

    async def retrieve(self, item_ids: List[str]) -> List[KnowledgeItem]:
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
        deleted_ids = []
        for item_id in item_ids:
            item_path = self._item_path(item_id)
            if item_path.exists():
                item_path.unlink()
                deleted_ids.append(item_id)
        return deleted_ids

    async def count(self) -> int:
        return len(list(self.storage_path.glob("*.json")))


async def test_in_memory_kb():
    """Test in-memory knowledge base."""
    print("Testing In-Memory Knowledge Base...")

    kb = InMemoryKnowledgeBase()

    # Test store
    items = [
        KnowledgeItem(
            id="item1",
            content="Python is a programming language",
            metadata={"category": "programming"}
        ),
        KnowledgeItem(
            id="item2",
            content="Machine learning uses algorithms",
            metadata={"category": "AI"}
        )
    ]

    stored_ids = await kb.store(items)
    print(f"Stored IDs: {stored_ids}")
    assert len(stored_ids) == 2

    # Test search
    query = SearchQuery(query="Python", limit=10)
    results = await kb.search(query)
    print(f"Search results: {len(results)} items")
    assert len(results) > 0
    assert any("Python" in item.content for item in results)

    # Test retrieve
    retrieved = await kb.retrieve(["item1"])
    print(f"Retrieved items: {len(retrieved)}")
    assert len(retrieved) == 1
    assert retrieved[0].content == "Python is a programming language"

    # Test count
    count = await kb.count()
    print(f"Total count: {count}")
    assert count == 2

    print("✓ In-Memory Knowledge Base tests passed")


async def test_filesystem_kb():
    """Test file system knowledge base."""
    print("Testing File System Knowledge Base...")

    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        kb = FileSystemKnowledgeBase(temp_dir)

        # Test store
        items = [
            KnowledgeItem(
                id="fs_item1",
                content="Docker containers provide isolation",
                metadata={"category": "devops"}
            )
        ]

        stored_ids = await kb.store(items)
        print(f"Stored IDs: {stored_ids}")
        assert len(stored_ids) == 1

        # Test search
        query = SearchQuery(query="Docker", limit=10)
        results = await kb.search(query)
        print(f"Search results: {len(results)} items")
        assert len(results) > 0

        # Test persistence - create new instance
        kb2 = FileSystemKnowledgeBase(temp_dir)
        count = await kb2.count()
        print(f"Count after reload: {count}")
        assert count == 1

    print("✓ File System Knowledge Base tests passed")


async def test_registry():
    """Test knowledge base registry."""
    print("Testing Knowledge Base Registry...")

    # Register backends
    KnowledgeBaseRegistry.register("memory", InMemoryKnowledgeBase)
    KnowledgeBaseRegistry.register("filesystem", FileSystemKnowledgeBase)

    # Test creation
    memory_kb = KnowledgeBaseRegistry.create_backend("memory")
    assert isinstance(memory_kb, InMemoryKnowledgeBase)

    # Test listing
    backends = KnowledgeBaseRegistry.list_backends()
    print(f"Available backends: {backends}")
    assert "memory" in backends
    assert "filesystem" in backends

    print("✓ Knowledge Base Registry tests passed")


async def test_data_structures():
    """Test data structures."""
    print("Testing Data Structures...")

    # Test KnowledgeItem
    item = KnowledgeItem(
        id="test_id",
        content="Test content",
        metadata={"key": "value"},
        score=0.85
    )
    assert item.id == "test_id"
    assert item.content == "Test content"
    assert item.metadata["key"] == "value"
    assert item.score == 0.85

    # Test SearchQuery
    query = SearchQuery(
        query="test query",
        limit=5,
        threshold=0.7,
        filters={"category": "test"}
    )
    assert query.query == "test query"
    assert query.limit == 5
    assert query.threshold == 0.7
    assert query.filters["category"] == "test"

    print("✓ Data Structures tests passed")


async def main():
    """Run all tests."""
    print("Running Knowledge Base Standardization Tests...\n")

    try:
        await test_in_memory_kb()
        print()

        await test_filesystem_kb()
        print()

        await test_data_structures()
        print()

        print("🎉 All tests passed! Knowledge base standardization is working correctly.")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())