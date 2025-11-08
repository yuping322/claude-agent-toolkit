#!/usr/bin/env python3
# test_external_dependencies_simple.py - Simple test for external dependencies standardization

import asyncio
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from abc import ABC, abstractmethod

class OperationResult(BaseModel):
    success: bool = Field(..., description="操作是否成功")
    data: Any = Field(None, description="返回数据")
    error: Optional[str] = Field(None, description="错误信息")
    duration: float = Field(default=0.0, description="操作耗时(秒)")

class ExternalDependencyInterface(ABC):
    """外部依赖接口抽象基类"""

    def __init__(self, name: str, dep_type: str):
        self.name = name
        self.dep_type = dep_type
        self._connected = False

    @abstractmethod
    async def connect(self) -> OperationResult:
        pass

    @abstractmethod
    async def execute_operation(self, operation: str, **kwargs) -> OperationResult:
        pass

    @property
    def is_connected(self) -> bool:
        return self._connected

class DatabaseDependency(ExternalDependencyInterface):
    """数据库依赖适配器"""

    async def connect(self) -> OperationResult:
        start_time = datetime.now()
        try:
            await asyncio.sleep(0.01)  # 模拟连接
            self._connected = True
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=True, duration=duration)
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=False, error=str(e), duration=duration)

    async def execute_operation(self, operation: str, **kwargs) -> OperationResult:
        if not self._connected:
            return OperationResult(success=False, error="Not connected")

        start_time = datetime.now()
        try:
            if operation == "query":
                duration = (datetime.now() - start_time).total_seconds()
                return OperationResult(
                    success=True,
                    data={"operation": "query", "query": kwargs.get("query")},
                    duration=duration
                )
            else:
                return OperationResult(success=False, error=f"Unsupported: {operation}")
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=False, error=str(e), duration=duration)

class APIDependency(ExternalDependencyInterface):
    """API依赖适配器"""

    async def connect(self) -> OperationResult:
        start_time = datetime.now()
        try:
            await asyncio.sleep(0.01)  # 模拟连接
            self._connected = True
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=True, duration=duration)
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=False, error=str(e), duration=duration)

    async def execute_operation(self, operation: str, **kwargs) -> OperationResult:
        if not self._connected:
            return OperationResult(success=False, error="Not connected")

        start_time = datetime.now()
        try:
            if operation == "get":
                duration = (datetime.now() - start_time).total_seconds()
                return OperationResult(
                    success=True,
                    data={"operation": "get", "endpoint": kwargs.get("endpoint")},
                    duration=duration
                )
            else:
                return OperationResult(success=False, error=f"Unsupported: {operation}")
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=False, error=str(e), duration=duration)

class DependencyManager:
    """外部依赖管理器"""

    def __init__(self):
        self._dependencies: Dict[str, ExternalDependencyInterface] = {}

    async def add_dependency(self, dependency: ExternalDependencyInterface) -> OperationResult:
        try:
            connect_result = await dependency.connect()
            if connect_result.success:
                self._dependencies[dependency.name] = dependency
                return OperationResult(success=True, data={"name": dependency.name})
            else:
                return connect_result
        except Exception as e:
            return OperationResult(success=False, error=str(e))

    async def execute_on_dependency(self, name: str, operation: str, **kwargs) -> OperationResult:
        if name not in self._dependencies:
            return OperationResult(success=False, error=f"Dependency not found: {name}")

        dependency = self._dependencies[name]
        return await dependency.execute_operation(operation, **kwargs)

    def list_dependencies(self) -> list:
        return [{"name": name, "type": dep.dep_type, "connected": dep.is_connected}
                for name, dep in self._dependencies.items()]

async def test_unified_interface():
    """测试统一的外部依赖接口"""
    print("Testing Unified External Dependencies Interface...")

    manager = DependencyManager()

    # 添加数据库依赖
    db = DatabaseDependency("main_db", "database")
    db_result = await manager.add_dependency(db)
    print(f"Add database: {db_result.success}")
    assert db_result.success == True

    # 添加API依赖
    api = APIDependency("weather_api", "api")
    api_result = await manager.add_dependency(api)
    print(f"Add API: {api_result.success}")
    assert api_result.success == True

    # 在数据库上执行查询
    query_result = await manager.execute_on_dependency(
        "main_db", "query", query="SELECT * FROM users"
    )
    print(f"Database query: {query_result.success}")
    assert query_result.success == True

    # 在API上执行请求
    api_result = await manager.execute_on_dependency(
        "weather_api", "get", endpoint="/weather"
    )
    print(f"API request: {api_result.success}")
    assert api_result.success == True

    # 列出所有依赖
    deps = manager.list_dependencies()
    print(f"Total dependencies: {len(deps)}")
    assert len(deps) == 2

    print("✓ Unified interface works for different dependency types!")

async def main():
    """主测试函数"""
    print("🎯 证明：其他外部依赖也可以像MCP一样实现标准化\n")

    try:
        await test_unified_interface()
        print("\n🎉 成功！外部依赖标准化框架工作正常")
        print("✅ 统一的接口可以适配数据库、API等各种外部依赖")
        print("✅ 就像MCP协议一样，任何外部服务都可以通过适配器标准化")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())