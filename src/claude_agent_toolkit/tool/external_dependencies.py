#!/usr/bin/env python3
# external_dependencies.py - 通用外部依赖标准化框架

"""
通用外部依赖标准化框架

受MCP启发，为不同类型的外部依赖创建统一的抽象层：
- 数据库连接
- API客户端
- 文件系统操作
- 消息队列
- 缓存服务
- 外部工具

核心思想：通过标准化的接口适配器，将各种外部依赖统一管理
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar, Generic, Union
from pydantic import BaseModel, Field
import asyncio
import json
from datetime import datetime

# 泛型类型变量
T = TypeVar('T')
ConfigT = TypeVar('ConfigT', bound=BaseModel)


class DependencyConfig(BaseModel):
    """外部依赖配置基类"""
    name: str = Field(..., description="依赖名称")
    type: str = Field(..., description="依赖类型")
    enabled: bool = Field(default=True, description="是否启用")
    timeout: int = Field(default=30, description="超时时间(秒)")
    retry_count: int = Field(default=3, description="重试次数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class OperationResult(BaseModel):
    """操作结果标准化结构"""
    success: bool = Field(..., description="操作是否成功")
    data: Any = Field(None, description="返回数据")
    error: Optional[str] = Field(None, description="错误信息")
    duration: float = Field(default=0.0, description="操作耗时(秒)")
    timestamp: datetime = Field(default_factory=datetime.now, description="操作时间")


class ExternalDependencyInterface(ABC, Generic[ConfigT]):
    """
    外部依赖接口抽象基类

    受MCP启发，为所有外部依赖定义统一的生命周期和操作接口
    """

    def __init__(self, config: ConfigT):
        self.config = config
        self._connected = False
        self._last_health_check = None

    @abstractmethod
    async def connect(self) -> OperationResult:
        """连接到外部依赖"""
        pass

    @abstractmethod
    async def disconnect(self) -> OperationResult:
        """断开连接"""
        pass

    @abstractmethod
    async def health_check(self) -> OperationResult:
        """健康检查"""
        pass

    @abstractmethod
    async def execute_operation(self, operation: str, **kwargs) -> OperationResult:
        """
        执行具体操作

        Args:
            operation: 操作名称
            **kwargs: 操作参数

        Returns:
            操作结果
        """
        pass

    @property
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    @property
    def name(self) -> str:
        """获取依赖名称"""
        return self.config.name

    @property
    def dependency_type(self) -> str:
        """获取依赖类型"""
        return self.config.type


class DatabaseConfig(DependencyConfig):
    """数据库配置"""
    connection_string: str = Field(..., description="数据库连接字符串")
    pool_size: int = Field(default=10, description="连接池大小")
    ssl_enabled: bool = Field(default=False, description="是否启用SSL")


class DatabaseDependency(ExternalDependencyInterface[DatabaseConfig]):
    """数据库依赖适配器"""

    async def connect(self) -> OperationResult:
        start_time = datetime.now()
        try:
            # 这里实现实际的数据库连接逻辑
            # 例如：使用asyncpg、aiomysql等
            self._connected = True
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=True,
                data={"connection_pool_size": self.config.pool_size},
                duration=duration
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )

    async def disconnect(self) -> OperationResult:
        start_time = datetime.now()
        try:
            # 关闭连接池
            self._connected = False
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=True, duration=duration)
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )

    async def health_check(self) -> OperationResult:
        if not self._connected:
            return OperationResult(
                success=False,
                error="Not connected to database"
            )

        start_time = datetime.now()
        try:
            # 执行简单的健康检查查询
            # result = await self._connection.execute("SELECT 1")
            duration = (datetime.now() - start_time).total_seconds()
            self._last_health_check = datetime.now()
            return OperationResult(
                success=True,
                data={"status": "healthy"},
                duration=duration
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )

    async def execute_operation(self, operation: str, **kwargs) -> OperationResult:
        if not self._connected:
            return OperationResult(
                success=False,
                error="Not connected to database"
            )

        start_time = datetime.now()
        try:
            if operation == "query":
                # 执行查询
                query = kwargs.get("query")
                params = kwargs.get("params", [])
                # result = await self._connection.fetch(query, *params)
                duration = (datetime.now() - start_time).total_seconds()
                return OperationResult(
                    success=True,
                    data={"rows": [], "count": 0},  # 模拟结果
                    duration=duration
                )

            elif operation == "execute":
                # 执行命令
                command = kwargs.get("command")
                params = kwargs.get("params", [])
                # result = await self._connection.execute(command, *params)
                duration = (datetime.now() - start_time).total_seconds()
                return OperationResult(
                    success=True,
                    data={"affected_rows": 0},  # 模拟结果
                    duration=duration
                )

            else:
                return OperationResult(
                    success=False,
                    error=f"Unsupported operation: {operation}"
                )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )


class APIConfig(DependencyConfig):
    """API配置"""
    base_url: str = Field(..., description="API基础URL")
    api_key: Optional[str] = Field(None, description="API密钥")
    headers: Dict[str, str] = Field(default_factory=dict, description="默认请求头")


class APIDependency(ExternalDependencyInterface[APIConfig]):
    """API依赖适配器"""

    async def connect(self) -> OperationResult:
        start_time = datetime.now()
        try:
            # 这里可以初始化HTTP客户端
            # 例如：aiohttp.ClientSession
            self._connected = True
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=True,
                data={"base_url": self.config.base_url},
                duration=duration
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )

    async def disconnect(self) -> OperationResult:
        start_time = datetime.now()
        try:
            # 关闭HTTP客户端
            self._connected = False
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(success=True, duration=duration)
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )

    async def health_check(self) -> OperationResult:
        if not self._connected:
            return OperationResult(
                success=False,
                error="Not connected to API"
            )

        start_time = datetime.now()
        try:
            # 调用健康检查端点
            # async with self._session.get(f"{self.config.base_url}/health") as resp:
            #     if resp.status == 200:
            duration = (datetime.now() - start_time).total_seconds()
            self._last_health_check = datetime.now()
            return OperationResult(
                success=True,
                data={"status": "healthy"},
                duration=duration
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )

    async def execute_operation(self, operation: str, **kwargs) -> OperationResult:
        if not self._connected:
            return OperationResult(
                success=False,
                error="Not connected to API"
            )

        start_time = datetime.now()
        try:
            if operation == "get":
                endpoint = kwargs.get("endpoint")
                params = kwargs.get("params", {})
                # async with self._session.get(f"{self.config.base_url}{endpoint}", params=params) as resp:
                #     result = await resp.json()
                duration = (datetime.now() - start_time).total_seconds()
                return OperationResult(
                    success=True,
                    data={"result": "mock_data"},  # 模拟结果
                    duration=duration
                )

            elif operation == "post":
                endpoint = kwargs.get("endpoint")
                data = kwargs.get("data", {})
                # async with self._session.post(f"{self.config.base_url}{endpoint}", json=data) as resp:
                #     result = await resp.json()
                duration = (datetime.now() - start_time).total_seconds()
                return OperationResult(
                    success=True,
                    data={"result": "created"},  # 模拟结果
                    duration=duration
                )

            else:
                return OperationResult(
                    success=False,
                    error=f"Unsupported operation: {operation}"
                )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return OperationResult(
                success=False,
                error=str(e),
                duration=duration
            )


class DependencyRegistry:
    """外部依赖注册中心"""

    _factories: Dict[str, callable] = {}

    @classmethod
    def register(cls, dependency_type: str, factory: callable):
        """注册依赖工厂"""
        cls._factories[dependency_type] = factory

    @classmethod
    def create_dependency(cls, config: DependencyConfig) -> ExternalDependencyInterface:
        """创建依赖实例"""
        factory = cls._factories.get(config.type)
        if not factory:
            raise ValueError(f"Unknown dependency type: {config.type}")
        return factory(config)

    @classmethod
    def list_supported_types(cls) -> List[str]:
        """列出支持的依赖类型"""
        return list(cls._factories.keys())


class DependencyManager:
    """外部依赖管理器"""

    def __init__(self):
        self._dependencies: Dict[str, ExternalDependencyInterface] = {}
        self._health_monitor_task: Optional[asyncio.Task] = None

    async def add_dependency(self, config: DependencyConfig) -> OperationResult:
        """添加外部依赖"""
        try:
            dependency = DependencyRegistry.create_dependency(config)
            connect_result = await dependency.connect()

            if connect_result.success:
                self._dependencies[config.name] = dependency
                return OperationResult(
                    success=True,
                    data={"dependency_name": config.name}
                )
            else:
                return connect_result

        except Exception as e:
            return OperationResult(
                success=False,
                error=str(e)
            )

    async def remove_dependency(self, name: str) -> OperationResult:
        """移除外部依赖"""
        if name not in self._dependencies:
            return OperationResult(
                success=False,
                error=f"Dependency not found: {name}"
            )

        dependency = self._dependencies[name]
        disconnect_result = await dependency.disconnect()
        del self._dependencies[name]

        return disconnect_result

    async def execute_on_dependency(
        self,
        dependency_name: str,
        operation: str,
        **kwargs
    ) -> OperationResult:
        """在指定依赖上执行操作"""
        if dependency_name not in self._dependencies:
            return OperationResult(
                success=False,
                error=f"Dependency not found: {name}"
            )

        dependency = self._dependencies[dependency_name]
        return await dependency.execute_operation(operation, **kwargs)

    async def health_check_all(self) -> Dict[str, OperationResult]:
        """检查所有依赖的健康状态"""
        results = {}
        for name, dependency in self._dependencies.items():
            results[name] = await dependency.health_check()
        return results

    def list_dependencies(self) -> List[Dict[str, Any]]:
        """列出所有依赖"""
        return [
            {
                "name": name,
                "type": dep.dependency_type,
                "connected": dep.is_connected
            }
            for name, dep in self._dependencies.items()
        ]

    async def start_health_monitoring(self, interval: int = 60):
        """启动健康监控"""
        async def monitor():
            while True:
                await asyncio.sleep(interval)
                unhealthy = []
                for name, result in (await self.health_check_all()).items():
                    if not result.success:
                        unhealthy.append(name)

                if unhealthy:
                    print(f"Unhealthy dependencies: {unhealthy}")

        self._health_monitor_task = asyncio.create_task(monitor())

    async def stop_health_monitoring(self):
        """停止健康监控"""
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass


# 注册内置依赖类型
DependencyRegistry.register("database", lambda config: DatabaseDependency(config))
DependencyRegistry.register("api", lambda config: APIDependency(config))


# 使用示例
async def example_usage():
    """使用示例"""

    # 创建依赖管理器
    manager = DependencyManager()

    # 添加数据库依赖
    db_config = DatabaseConfig(
        name="main_db",
        type="database",
        connection_string="postgresql://localhost:5432/mydb"
    )
    db_result = await manager.add_dependency(db_config)
    print(f"Database setup: {db_result}")

    # 添加API依赖
    api_config = APIConfig(
        name="weather_api",
        type="api",
        base_url="https://api.weather.com",
        api_key="your_api_key"
    )
    api_result = await manager.add_dependency(api_config)
    print(f"API setup: {api_result}")

    # 执行操作
    query_result = await manager.execute_on_dependency(
        "main_db",
        "query",
        query="SELECT * FROM users WHERE active = $1",
        params=[True]
    )
    print(f"Query result: {query_result}")

    weather_result = await manager.execute_on_dependency(
        "weather_api",
        "get",
        endpoint="/current",
        params={"location": "Beijing"}
    )
    print(f"Weather result: {weather_result}")

    # 健康检查
    health_results = await manager.health_check_all()
    print(f"Health check: {health_results}")

    # 列出依赖
    deps = manager.list_dependencies()
    print(f"Dependencies: {deps}")


if __name__ == "__main__":
    asyncio.run(example_usage())</content>
