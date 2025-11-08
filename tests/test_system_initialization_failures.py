import asyncio
import pytest
import tempfile
import os
from unittest.mock import patch, AsyncMock

from claude_agent_toolkit.system.initialize import initialize_system, get_agent_runtime
from claude_agent_toolkit.system.config import load_unified_config
from claude_agent_toolkit.system.model_provider import OpenRouterProvider
from claude_agent_toolkit.system.observability import event_bus, BaseEvent


class TestSystemInitializationFailures:
    """测试系统初始化各种失败情况"""

    @pytest.mark.asyncio
    async def test_initialize_with_invalid_config_path(self):
        """测试使用无效配置文件路径初始化"""
        with pytest.raises(FileNotFoundError):
            await initialize_system("/nonexistent/config.yaml")

    @pytest.mark.asyncio
    async def test_initialize_with_invalid_config_content(self):
        """测试使用无效配置文件内容初始化"""
        config_content = """
invalid: yaml: content:
  - with
    syntax: errors
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            with pytest.raises(Exception):  # YAML解析错误
                await initialize_system(config_path)
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_with_missing_model_provider(self):
        """测试初始化时缺少模型提供者的情况"""
        config_content = """
meta:
  environment: dev
  version: 1
model_providers: {}  # 空的提供者配置
agents:
  test_agent:
    model_provider: nonexistent_provider  # 引用不存在的提供者
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该抛出异常，因为agent引用了不存在的提供者
            with pytest.raises(ValueError, match="unknown model_provider"):
                await initialize_system(config_path)
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_with_invalid_provider_config(self):
        """测试初始化时提供者配置无效的情况"""
        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: invalid_provider_type
        api_key: test_key
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该能够初始化，但提供者创建可能会失败
            await initialize_system(config_path)
            # 检查提供者是否创建失败
            from claude_agent_toolkit.system.initialize import _state
            assert len(_state["providers"]) == 0  # 没有有效的提供者
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_mcp_service_failure(self):
        """测试MCP服务初始化失败的情况"""
        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: openrouter
        api_key: test_key
    mcp_services:
      failing_service:
        type: invalid_type
    agents: {}
    dependency_pools: {}
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该能够初始化，MCP服务注册总是成功的
            await initialize_system(config_path)
            from claude_agent_toolkit.system.initialize import _state
            assert "failing_service" in _state["mcp_registry"]._services
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_dependency_pool_failure(self):
        """测试依赖池初始化失败的情况"""
        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: openrouter
        api_key: test_key
    mcp_services: {}
    agents: {}
    dependency_pools:
      failing_pool:
        type: invalid_type
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该能够初始化，但无效的池类型会被跳过
            await initialize_system(config_path)
            from claude_agent_toolkit.system.initialize import _state
            # 检查池是否被跳过
            assert len(_state["dependency_manager"]._pools) == 0
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_get_agent_runtime_before_initialization(self):
        """测试在初始化之前获取agent运行时配置"""
        # 确保系统状态被重置
        from claude_agent_toolkit.system.initialize import _state
        _state.clear()
        
        with pytest.raises(RuntimeError, match="System not initialized"):
            get_agent_runtime("test_agent")

    @pytest.mark.asyncio
    async def test_get_agent_runtime_unknown_agent(self):
        """测试获取未知agent的运行时配置"""
        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: openrouter
        api_key: test_key
    mcp_services: {}
    agents:
      existing_agent:
        model_provider: test_provider
    dependency_pools: {}
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            await initialize_system(config_path)

            # 尝试获取不存在的agent
            with pytest.raises(ValueError, match="Unknown agent"):  # build_agent_runtime抛出ValueError
                get_agent_runtime("nonexistent_agent")
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_event_emission(self):
        """测试初始化时的事件发射"""
        events = []
        def event_handler(event):
            events.append(event)

        event_bus.subscribe("system.init", event_handler)

        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: openrouter
        api_key: test_key
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            await initialize_system(config_path)

            # 检查初始化事件
            init_events = [e for e in events if isinstance(e, BaseEvent) and e.event_type == "system.init"]
            assert len(init_events) == 1
            event = init_events[0]
            assert event.component == "bootstrap"
            assert "providers" in event.data
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_with_environment_variables(self):
        """测试使用环境变量初始化的情况"""
        # 设置环境变量
        os.environ["TEST_API_KEY"] = "test_key_from_env"

        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: openrouter
        api_key: ${TEST_API_KEY}
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            await initialize_system(config_path)

            # 检查环境变量是否被正确解析
            from claude_agent_toolkit.system.initialize import _state
            assert len(_state["providers"]) == 1
            provider = list(_state["providers"].values())[0]
            assert provider.api_key == "test_key_from_env"
        finally:
            os.unlink(config_path)
            # 清理环境变量
            del os.environ["TEST_API_KEY"]

    @pytest.mark.asyncio
    async def test_initialize_with_missing_environment_variable(self):
        """测试缺少环境变量的情况"""
        # 确保环境变量不存在
        if "MISSING_ENV_VAR" in os.environ:
            del os.environ["MISSING_ENV_VAR"]

        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: openrouter
        api_key: ${MISSING_ENV_VAR}
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            await initialize_system(config_path)

            # 检查未解析的环境变量
            from claude_agent_toolkit.system.initialize import _state
            assert len(_state["providers"]) == 0  # 提供者创建失败
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_multiple_times(self):
        """测试多次初始化的情况"""
        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      test_provider:
        type: openrouter
        api_key: test_key
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 第一次初始化
            await initialize_system(config_path)

            # 第二次初始化应该覆盖之前的
            await initialize_system(config_path)

            # 检查状态是否正确
            from claude_agent_toolkit.system.initialize import _state
            assert _state["config"] is not None
            assert len(_state["providers"]) == 1
        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_initialize_with_complex_dependencies(self):
        """测试具有复杂依赖关系的初始化"""
        config_content = """
    meta:
      environment: dev
      version: 1
    logging:
      level: INFO
      format: json
    observability:
      enabled: false
    sandbox:
      default_strategy: subprocess
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers:
      provider1:
        type: openrouter
        api_key: key1
      provider2:
        type: openrouter
        api_key: key2
    mcp_services:
      service1:
        type: filesystem
      service2:
        type: git
    agents:
      agent1:
        model_provider: provider1
        dependency_pools: [pool1]
      agent2:
        model_provider: provider2
        dependency_pools: [pool2]
    dependency_pools:
      pool1:
        type: filesystem
        paths: [/tmp]
      pool2:
        type: filesystem
        paths: [/var/tmp]
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            await initialize_system(config_path)

            # 检查所有组件是否正确初始化
            from claude_agent_toolkit.system.initialize import _state
            assert len(_state["providers"]) == 2
            assert len(_state["mcp_registry"]._services) == 2
            assert len(_state["dependency_manager"]._pools) == 2
        finally:
            os.unlink(config_path)