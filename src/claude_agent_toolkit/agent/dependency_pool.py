#!/usr/bin/env python3
# dependency_pool.py - Agent外部依赖共享池化管理

"""
Agent外部依赖共享池化管理

解决每个agent独立管理外部依赖的问题，实现依赖复用和集中管理。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, TypeVar, Generic, Set
from dataclasses import dataclass
import asyncio
import logging
import time
from datetime import datetime
import weakref

# Observability event bus
from ..system.observability import event_bus, DependencyPoolEvent

from ..logging import get_logger

logger = get_logger('dependency_pool')

T = TypeVar('T')


@dataclass
class DependencyInstance:
    """依赖实例包装器"""
    instance: Any
    agent_id: str
    acquired_at: datetime
    last_used: datetime
    use_count: int = 0

    def touch(self):
        """更新最后使用时间"""
        self.last_used = datetime.now()
        self.use_count += 1


class DependencyPool(ABC, Generic[T]):
    """依赖池抽象基类"""

    def __init__(self, dependency_type: str, max_instances: int = 5):
        self.dependency_type = dependency_type
        self.max_instances = max_instances
        self._available: asyncio.Queue[T] = asyncio.Queue()
        self._in_use: Dict[str, T] = {}  # agent_id -> instance
        self._instance_refs: Dict[T, DependencyInstance] = {}  # instance -> metadata
        self._creation_times: Dict[T, datetime] = {}
        self._lock = asyncio.Lock()

    @abstractmethod
    async def create_instance(self) -> T:
        """创建新的依赖实例"""
        pass

    @abstractmethod
    async def destroy_instance(self, instance: T) -> None:
        """销毁依赖实例"""
        pass

    @abstractmethod
    async def validate_instance(self, instance: T) -> bool:
        """验证实例是否仍然有效"""
        pass

    async def acquire(self, agent_id: str, timeout: float = 30.0) -> T:
        """获取依赖实例"""
        async with self._lock:
            start_time = time.time()

            # 首先尝试获取可用实例
            if not self._available.empty():
                instance = await self._available.get()
                if await self.validate_instance(instance):
                    self._in_use[agent_id] = instance
                    self._instance_refs[instance].touch()
                    logger.debug(f"Reused {self.dependency_type} instance for agent {agent_id}")
                    # Emit acquire (reuse) event
                    event_bus.publish(DependencyPoolEvent(
                        event_type="dependency.pool",
                        action="acquire",
                        dependency_type=self.dependency_type,
                        agent_id=agent_id,
                        in_use=len(self._in_use),
                        available=self._available.qsize(),
                        component="dependency_pool"
                    ))
                    return instance
                else:
                    # 实例无效，销毁并创建新的
                    await self.destroy_instance(instance)
                    del self._instance_refs[instance]
                    del self._creation_times[instance]

            # 检查是否可以创建新实例
            if len(self._in_use) < self.max_instances:
                instance = await self.create_instance()
                dep_instance = DependencyInstance(
                    instance=instance,
                    agent_id=agent_id,
                    acquired_at=datetime.now(),
                    last_used=datetime.now()
                )
                self._in_use[agent_id] = instance
                self._instance_refs[instance] = dep_instance
                self._creation_times[instance] = datetime.now()
                logger.info(f"Created new {self.dependency_type} instance for agent {agent_id}")
                event_bus.publish(DependencyPoolEvent(
                    event_type="dependency.pool",
                    action="acquire",
                    dependency_type=self.dependency_type,
                    agent_id=agent_id,
                    in_use=len(self._in_use),
                    available=self._available.qsize(),
                    component="dependency_pool"
                ))
                return instance

            # 等待可用实例
            try:
                instance = await asyncio.wait_for(
                    self._available.get(),
                    timeout=timeout - (time.time() - start_time)
                )
                if await self.validate_instance(instance):
                    self._in_use[agent_id] = instance
                    self._instance_refs[instance].touch()
                    logger.debug(f"Waited for and got {self.dependency_type} instance for agent {agent_id}")
                    event_bus.publish(DependencyPoolEvent(
                        event_type="dependency.pool",
                        action="acquire",
                        dependency_type=self.dependency_type,
                        agent_id=agent_id,
                        in_use=len(self._in_use),
                        available=self._available.qsize(),
                        component="dependency_pool"
                    ))
                    return instance
                else:
                    await self.destroy_instance(instance)
                    del self._instance_refs[instance]
                    del self._creation_times[instance]
            except asyncio.TimeoutError:
                pass

            # Timeout: do not emit acquire event (no change in state) just raise
            raise TimeoutError(f"No available {self.dependency_type} instance within {timeout}s")

    async def release(self, agent_id: str) -> None:
        """释放依赖实例"""
        async with self._lock:
            if agent_id in self._in_use:
                instance = self._in_use[agent_id]
                del self._in_use[agent_id]

                # 检查实例是否仍然有效
                if await self.validate_instance(instance):
                    await self._available.put(instance)
                    logger.debug(f"Released {self.dependency_type} instance from agent {agent_id}")
                    event_bus.publish(DependencyPoolEvent(
                        event_type="dependency.pool",
                        action="release",
                        dependency_type=self.dependency_type,
                        agent_id=agent_id,
                        in_use=len(self._in_use),
                        available=self._available.qsize(),
                        component="dependency_pool"
                    ))
                else:
                    await self.destroy_instance(instance)
                    del self._instance_refs[instance]
                    del self._creation_times[instance]
                    logger.warning(f"Destroyed invalid {self.dependency_type} instance from agent {agent_id}")
                    event_bus.publish(DependencyPoolEvent(
                        event_type="dependency.pool",
                        action="release",
                        dependency_type=self.dependency_type,
                        agent_id=agent_id,
                        in_use=len(self._in_use),
                        available=self._available.qsize(),
                        component="dependency_pool"
                    ))

    async def cleanup_expired(self, max_age_seconds: int = 3600) -> int:
        """清理过期的实例"""
        async with self._lock:
            now = datetime.now()
            expired_count = 0

            instances_to_remove = []
            for instance, created_at in self._creation_times.items():
                if (now - created_at).total_seconds() > max_age_seconds:
                    instances_to_remove.append(instance)

            for instance in instances_to_remove:
                if instance not in self._in_use.values():  # 不清理正在使用的实例
                    await self.destroy_instance(instance)
                    del self._instance_refs[instance]
                    del self._creation_times[instance]
                    expired_count += 1

            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired {self.dependency_type} instances")
                event_bus.publish(DependencyPoolEvent(
                    event_type="dependency.pool",
                    action="cleanup",
                    dependency_type=self.dependency_type,
                    agent_id=None,
                    in_use=len(self._in_use),
                    available=self._available.qsize(),
                    component="dependency_pool",
                    data={"expired_count": expired_count}
                ))

            return expired_count

    def get_stats(self) -> Dict[str, Any]:
        """获取池统计信息"""
        return {
            "dependency_type": self.dependency_type,
            "max_instances": self.max_instances,
            "in_use": len(self._in_use),
            "available": self._available.qsize(),
            "total_created": len(self._instance_refs),
            "agent_usage": {agent_id: self._instance_refs[inst].use_count
                          for agent_id, inst in self._in_use.items()
                          if inst in self._instance_refs}
        }


class ClaudeCodePool(DependencyPool):
    """Claude Code连接池"""

    def __init__(self, oauth_token: str, model: str = "sonnet", max_instances: int = 3):
        super().__init__("claude_code", max_instances)
        self.oauth_token = oauth_token
        self.model = model

    async def create_instance(self):
        """创建Claude Code实例"""
        try:
            from ..agent.core import Agent
            instance = Agent(
                oauth_token=self.oauth_token,
                model=self.model,
                executor=None  # 使用默认executor
            )
            logger.info("Created Claude Code instance")
            return instance
        except Exception as e:
            logger.error(f"Failed to create Claude Code instance: {e}")
            raise

    async def destroy_instance(self, instance):
        """销毁Claude Code实例"""
        try:
            # Agent实例通常不需要显式清理
            logger.info("Destroyed Claude Code instance")
        except Exception as e:
            logger.warning(f"Error destroying Claude Code instance: {e}")

    async def validate_instance(self, instance) -> bool:
        """验证Claude Code实例是否有效"""
        try:
            # 简单的健康检查
            return hasattr(instance, 'run') and callable(instance.run)
        except Exception:
            return False


class FileSystemPool(DependencyPool):
    """文件系统访问池"""

    def __init__(self, allowed_paths: List[str], max_instances: int = 10):
        super().__init__("filesystem", max_instances)
        self.allowed_paths = [path.rstrip('/') for path in allowed_paths]

    async def create_instance(self):
        """创建文件系统访问实例"""
        # 创建一个简单的文件系统访问器，不启动MCP服务器
        from ..tools.filesystem import FileSystemAccessor
        instance = FileSystemAccessor(allowed_paths=self.allowed_paths)
        logger.info(f"Created FileSystem instance with permissions for paths: {self.allowed_paths}")
        return instance

    async def destroy_instance(self, instance):
        """销毁文件系统实例"""
        try:
            # FileSystemAccessor通常不需要特殊清理
            logger.info("Destroyed FileSystem instance")
        except Exception as e:
            logger.warning(f"Error destroying FileSystem instance: {e}")

    async def validate_instance(self, instance) -> bool:
        """验证文件系统实例是否有效"""
        try:
            return hasattr(instance, 'list_directory') and callable(instance.list_directory)
        except Exception:
            return False


class CursorPool(DependencyPool):
    """Cursor CLI连接池"""

    def __init__(self, binary_path: str = "cursor", max_instances: int = 2):
        super().__init__("cursor", max_instances)
        self.binary_path = binary_path

    async def create_instance(self):
        """创建Cursor实例"""
        from ..executors.cursor import CursorExecutor
        instance = CursorExecutor(binary_path=self.binary_path)
        logger.info(f"Created Cursor instance with binary: {self.binary_path}")
        return instance

    async def destroy_instance(self, instance):
        """销毁Cursor实例"""
        try:
            logger.info("Destroyed Cursor instance")
        except Exception as e:
            logger.warning(f"Error destroying Cursor instance: {e}")

    async def validate_instance(self, instance) -> bool:
        """验证Cursor实例是否有效"""
        try:
            return instance.is_available()
        except Exception:
            return False


class SharedDependencyManager:
    """共享依赖管理器"""

    def __init__(self):
        self._pools: Dict[str, DependencyPool] = {}
        self._agent_dependencies: Dict[str, Set[str]] = {}  # agent_id -> set of dependency_types
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def register_pool(self, dependency_type: str, pool: DependencyPool) -> None:
        """注册依赖池"""
        async with self._lock:
            self._pools[dependency_type] = pool
            logger.info(f"Registered dependency pool: {dependency_type}")

    async def register_agent(self, agent_id: str, dependency_types: List[str]) -> None:
        """为agent注册依赖类型"""
        async with self._lock:
            # 验证依赖类型存在
            for dep_type in dependency_types:
                if dep_type not in self._pools:
                    raise ValueError(f"Unknown dependency type: {dep_type}")

            self._agent_dependencies[agent_id] = set(dependency_types)
            logger.info(f"Registered agent {agent_id} with dependencies: {dependency_types}")

    async def get_dependency(self, agent_id: str, dependency_type: str, timeout: float = 30.0):
        """获取agent的依赖实例"""
        if agent_id not in self._agent_dependencies:
            raise ValueError(f"Agent {agent_id} not registered")

        if dependency_type not in self._agent_dependencies[agent_id]:
            raise ValueError(f"Agent {agent_id} not authorized for dependency {dependency_type}")

        pool = self._pools.get(dependency_type)
        if not pool:
            raise ValueError(f"Dependency pool not found: {dependency_type}")

        return await pool.acquire(agent_id, timeout)

    async def release_dependency(self, agent_id: str, dependency_type: str) -> None:
        """释放agent的依赖实例"""
        pool = self._pools.get(dependency_type)
        if pool:
            await pool.release(agent_id)

    async def release_agent_dependencies(self, agent_id: str) -> None:
        """释放agent的所有依赖"""
        if agent_id in self._agent_dependencies:
            for dep_type in self._agent_dependencies[agent_id]:
                await self.release_dependency(agent_id, dep_type)
            del self._agent_dependencies[agent_id]
            logger.info(f"Released all dependencies for agent {agent_id}")

    async def cleanup_expired_instances(self, max_age_seconds: int = 3600) -> Dict[str, int]:
        """清理所有池中的过期实例"""
        results = {}
        for dep_type, pool in self._pools.items():
            results[dep_type] = await pool.cleanup_expired(max_age_seconds)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取所有池的统计信息"""
        return {
            "pools": {dep_type: pool.get_stats() for dep_type, pool in self._pools.items()},
            "agents": {agent_id: list(dep_types) for agent_id, dep_types in self._agent_dependencies.items()},
            "total_agents": len(self._agent_dependencies),
            "total_pools": len(self._pools)
        }

    async def start_cleanup_task(self, interval: int = 300) -> None:
        """启动定期清理任务"""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.cleanup_expired_instances()
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(f"Started cleanup task with {interval}s interval")

    async def stop_cleanup_task(self) -> None:
        """停止清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped cleanup task")


# 全局共享依赖管理器实例
_shared_manager = None

def get_shared_dependency_manager() -> SharedDependencyManager:
    """获取全局共享依赖管理器"""
    global _shared_manager
    if _shared_manager is None:
        _shared_manager = SharedDependencyManager()
    return _shared_manager


async def initialize_shared_dependencies(config: Dict[str, Any]) -> SharedDependencyManager:
    """
    初始化共享依赖管理器

    Args:
        config: 配置字典，包含池配置和agent配置
    """
    manager = get_shared_dependency_manager()

    # 初始化依赖池
    pool_configs = config.get("pools", {})
    for pool_name, pool_config in pool_configs.items():
        pool_type = pool_config["type"]

        if pool_type == "claude_code":
            pool = ClaudeCodePool(
                oauth_token=pool_config["oauth_token"],
                model=pool_config.get("model", "sonnet"),
                max_instances=pool_config.get("max_instances", 3)
            )
        elif pool_type == "filesystem":
            pool = FileSystemPool(
                allowed_paths=pool_config["allowed_paths"],
                max_instances=pool_config.get("max_instances", 10)
            )
        elif pool_type == "cursor":
            pool = CursorPool(
                binary_path=pool_config.get("binary_path", "cursor"),
                max_instances=pool_config.get("max_instances", 2)
            )
        else:
            logger.warning(f"Unknown pool type: {pool_type}")
            continue

        await manager.register_pool(pool_name, pool)

    # 注册agents
    agent_configs = config.get("agents", {})
    for agent_id, agent_config in agent_configs.items():
        dependencies = agent_config.get("dependencies", [])
        await manager.register_agent(agent_id, dependencies)

    # 启动清理任务
    await manager.start_cleanup_task()

    logger.info("Shared dependency manager initialized")
    return manager


# 使用示例
async def example_usage():
    """使用示例"""

    # 配置
    config = {
        "pools": {
            "claude_code": {
                "type": "claude_code",
                "oauth_token": "your_token_here",
                "model": "sonnet",
                "max_instances": 2
            },
            "filesystem": {
                "type": "filesystem",
                "allowed_paths": ["/workspace", "/tmp"],
                "max_instances": 5
            }
        },
        "agents": {
            "bug_fix_agent": {
                "dependencies": ["claude_code", "filesystem"]
            },
            "analysis_agent": {
                "dependencies": ["filesystem"]
            }
        }
    }

    # 初始化
    manager = await initialize_shared_dependencies(config)

    # Agent使用依赖
    try:
        # Bug fix agent获取Claude Code实例
        claude_instance = await manager.get_dependency("bug_fix_agent", "claude_code")
        print("Bug fix agent got Claude Code instance")

        # Analysis agent获取文件系统实例
        fs_instance = await manager.get_dependency("analysis_agent", "filesystem")
        print("Analysis agent got filesystem instance")

        # 使用实例...
        # result = await claude_instance.run("Analyze this code...")

    finally:
        # 释放依赖
        await manager.release_agent_dependencies("bug_fix_agent")
        await manager.release_agent_dependencies("analysis_agent")

    # 查看统计
    stats = manager.get_stats()
    print(f"Final stats: {stats}")


if __name__ == "__main__":
    asyncio.run(example_usage())
