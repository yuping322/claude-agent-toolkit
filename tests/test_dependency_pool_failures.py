import asyncio
import pytest
import tempfile
import os
from unittest.mock import patch, AsyncMock

from claude_agent_toolkit.agent.dependency_pool import (
    DependencyPool, FileSystemPool, ClaudeCodePool, SharedDependencyManager,
    initialize_shared_dependencies
)
from claude_agent_toolkit.system.observability import event_bus, DependencyPoolEvent


class TestDependencyPoolFailures:
    """测试依赖池各种失败情况"""

    @pytest.mark.asyncio
    async def test_pool_timeout(self):
        """测试池获取超时的情况"""
        pool = FileSystemPool(["/tmp"], max_instances=1)

        # 先获取一个实例
        instance1 = await pool.acquire("agent1", timeout=1.0)
        assert instance1 is not None

        # 第二个获取应该超时
        with pytest.raises(TimeoutError):
            await pool.acquire("agent2", timeout=0.1)

    @pytest.mark.asyncio
    async def test_invalid_instance_creation(self):
        """测试实例创建失败的情况"""
        pool = FileSystemPool(["/nonexistent/path"], max_instances=5)

        # 应该能够创建实例（FileSystemPool总是成功）
        instance = await pool.acquire("agent1")
        assert instance is not None

    @pytest.mark.asyncio
    async def test_instance_validation_failure(self):
        """测试实例验证失败的情况"""
        pool = FileSystemPool(["/tmp"], max_instances=5)

        # Mock validate_instance to return False
        original_validate = pool.validate_instance
        async def failing_validate(instance):
            return False

        pool.validate_instance = failing_validate

        try:
            # 获取实例
            instance = await pool.acquire("agent1")
            assert instance is not None

            # 释放实例
            await pool.release("agent1")

            # 再次获取应该创建一个新实例（因为之前的实例验证失败）
            instance2 = await pool.acquire("agent1")
            assert instance2 is not None
        finally:
            pool.validate_instance = original_validate

    @pytest.mark.asyncio
    async def test_release_unknown_agent(self):
        """测试释放未知agent的情况"""
        pool = FileSystemPool(["/tmp"], max_instances=5)

        # 释放不存在的agent应该不抛出异常
        await pool.release("nonexistent_agent")

    @pytest.mark.asyncio
    async def test_cleanup_expired_instances(self):
        """测试清理过期实例的情况"""
        pool = FileSystemPool(["/tmp"], max_instances=5)

        # 获取实例
        instance = await pool.acquire("agent1")

        # 释放实例，使其可被清理
        await pool.release("agent1")

        # Mock creation time to be old
        import time
        from datetime import datetime
        old_time = datetime.now().timestamp() - 7200  # 2 hours ago
        pool._creation_times[instance] = datetime.fromtimestamp(old_time)

        # 清理过期实例
        removed_count = await pool.cleanup_expired(3600)  # 1 hour expiry
        assert removed_count == 1

        # 实例应该已经被清理
        assert instance not in pool._creation_times

    @pytest.mark.asyncio
    async def test_pool_stats_empty_pool(self):
        """测试空池的统计信息"""
        pool = FileSystemPool(["/tmp"], max_instances=5)

        stats = pool.get_stats()
        assert stats["dependency_type"] == "filesystem"
        assert stats["max_instances"] == 5
        assert stats["in_use"] == 0
        assert stats["available"] == 0
        assert stats["total_created"] == 0

    @pytest.mark.asyncio
    async def test_pool_concurrent_access(self):
        """测试池的并发访问"""
        pool = FileSystemPool(["/tmp"], max_instances=5)

        async def acquire_and_release(agent_id):
            instance = await pool.acquire(agent_id, timeout=10.0)
            await asyncio.sleep(0.01)  # 短暂等待
            await pool.release(agent_id)

        # 并发执行少量获取/释放操作
        tasks = [
            acquire_and_release(f"agent{i}")
            for i in range(3)  # 少量并发
        ]

        # 应该都能完成，不抛出异常
        await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_event_emission_on_acquire(self):
        """测试获取实例时的事件发射"""
        events = []
        def event_handler(event):
            events.append(event)

        event_bus.subscribe("dependency.pool", event_handler)

        pool = FileSystemPool(["/tmp"], max_instances=5)

        # 获取实例
        instance = await pool.acquire("test_agent")

        # 检查事件
        acquire_events = [e for e in events if e.action == "acquire"]
        assert len(acquire_events) == 1
        event = acquire_events[0]
        assert event.dependency_type == "filesystem"
        assert event.agent_id == "test_agent"
        assert event.in_use == 1

        # 清理
        await pool.release("test_agent")

    @pytest.mark.asyncio
    async def test_event_emission_on_release(self):
        """测试释放实例时的事件发射"""
        events = []
        def event_handler(event):
            events.append(event)

        event_bus.subscribe("dependency.pool", event_handler)

        pool = FileSystemPool(["/tmp"], max_instances=5)

        # 获取并释放实例
        instance = await pool.acquire("test_agent")
        await pool.release("test_agent")

        # 检查事件
        release_events = [e for e in events if e.action == "release"]
        assert len(release_events) == 1
        event = release_events[0]
        assert event.dependency_type == "filesystem"
        assert event.agent_id == "test_agent"
        assert event.in_use == 0

    @pytest.mark.asyncio
    async def test_event_emission_on_cleanup(self):
        """测试清理时的事件发射"""
        events = []
        def event_handler(event):
            events.append(event)

        event_bus.subscribe("dependency.pool", event_handler)

        pool = FileSystemPool(["/tmp"], max_instances=5)

        # 获取实例并释放，然后使其过期
        instance = await pool.acquire("test_agent")
        await pool.release("test_agent")  # 释放实例，使其可被清理
        
        import time
        from datetime import datetime
        old_time = datetime.now().timestamp() - 7200
        pool._creation_times[instance] = datetime.fromtimestamp(old_time)

        # 清理
        await pool.cleanup_expired(3600)

        # 检查事件
        cleanup_events = [e for e in events if e.action == "cleanup"]
        assert len(cleanup_events) == 1
        event = cleanup_events[0]
        assert event.dependency_type == "filesystem"
        assert event.data["expired_count"] == 1


class TestSharedDependencyManagerFailures:
    """测试共享依赖管理器各种失败情况"""

    @pytest.mark.asyncio
    async def test_register_unknown_pool_type(self):
        """测试注册未知池类型的情况"""
        manager = SharedDependencyManager()

        # 创建一个未知类型的池
        class UnknownPool(DependencyPool):
            def __init__(self):
                super().__init__("unknown", 5)

            async def create_instance(self):
                return "unknown_instance"

            async def destroy_instance(self, instance):
                pass

            async def validate_instance(self, instance):
                return True

        pool = UnknownPool()
        await manager.register_pool("unknown_pool", pool)

        # 验证池已注册
        assert "unknown_pool" in manager._pools

    @pytest.mark.asyncio
    async def test_register_duplicate_pool(self):
        """测试注册重复池的情况"""
        manager = SharedDependencyManager()

        pool1 = FileSystemPool(["/tmp"])
        pool2 = FileSystemPool(["/tmp"])

        await manager.register_pool("test_pool", pool1)

        # 注册同名池应该覆盖之前的
        await manager.register_pool("test_pool", pool2)

        assert manager._pools["test_pool"] is pool2

    @pytest.mark.asyncio
    async def test_register_agent_unknown_dependency(self):
        """测试为agent注册未知依赖的情况"""
        manager = SharedDependencyManager()

        # 先注册一个已知的池
        pool = FileSystemPool(["/tmp"])
        await manager.register_pool("filesystem", pool)

        # 注册agent时包含未知依赖
        with pytest.raises(ValueError, match="Unknown dependency type: unknown_dep"):
            await manager.register_agent("test_agent", ["filesystem", "unknown_dep"])

    @pytest.mark.asyncio
    async def test_get_dependency_unknown_agent(self):
        """测试获取未知agent的依赖"""
        manager = SharedDependencyManager()

        with pytest.raises(ValueError, match="Agent test_agent not registered"):
            await manager.get_dependency("test_agent", "filesystem")

    @pytest.mark.asyncio
    async def test_get_dependency_unauthorized_type(self):
        """测试获取agent未授权的依赖类型"""
        manager = SharedDependencyManager()

        # 先注册池
        pool = FileSystemPool(["/tmp"])
        await manager.register_pool("filesystem", pool)

        # 注册agent只有filesystem权限
        await manager.register_agent("test_agent", ["filesystem"])

        # 尝试获取claude_code权限
        with pytest.raises(ValueError, match="not authorized for dependency claude_code"):
            await manager.get_dependency("test_agent", "claude_code")

    @pytest.mark.asyncio
    async def test_get_dependency_unknown_pool(self):
        """测试获取不存在的池的依赖"""
        manager = SharedDependencyManager()

        # 先注册一个已知的池
        pool = FileSystemPool(["/tmp"])
        await manager.register_pool("filesystem", pool)

        # 注册agent包含已知和未知的池
        with pytest.raises(ValueError, match="Unknown dependency type: unknown_pool"):
            await manager.register_agent("test_agent", ["filesystem", "unknown_pool"])

    @pytest.mark.asyncio
    async def test_release_dependency_unknown_agent(self):
        """测试释放未知agent的依赖"""
        manager = SharedDependencyManager()

        # 不应该抛出异常
        await manager.release_dependency("unknown_agent", "filesystem")

    @pytest.mark.asyncio
    async def test_release_agent_unknown_agent(self):
        """测试释放未知agent的所有依赖"""
        manager = SharedDependencyManager()

        # 不应该抛出异常
        await manager.release_agent_dependencies("unknown_agent")

    @pytest.mark.asyncio
    async def test_initialize_with_invalid_config(self):
        """测试使用无效配置初始化"""
        invalid_config = {
            "pools": {
                "test_pool": {
                    "type": "invalid_type"  # 无效类型
                }
            }
        }

        # 应该记录警告但不失败
        manager = await initialize_shared_dependencies(invalid_config)
        assert isinstance(manager, SharedDependencyManager)

    @pytest.mark.asyncio
    async def test_manager_stats_empty(self):
        """测试空管理器的统计信息"""
        manager = SharedDependencyManager()

        stats = manager.get_stats()
        assert stats["total_agents"] == 0
        assert stats["total_pools"] == 0
        assert len(stats["pools"]) == 0
        assert len(stats["agents"]) == 0

    @pytest.mark.asyncio
    async def test_cleanup_task_operations(self):
        """测试清理任务的操作"""
        manager = SharedDependencyManager()

        # 启动清理任务
        await manager.start_cleanup_task(interval=1)  # 1秒间隔

        # 等待一段时间
        await asyncio.sleep(0.1)

        # 停止清理任务
        await manager.stop_cleanup_task()

        # 不应该抛出异常
        assert manager._cleanup_task is None