import pytest
import tempfile
import os
from pathlib import Path

from claude_agent_toolkit.system.config import (
    load_unified_config, UnifiedConfig, build_agent_runtime,
    ModelProviderConfig, AgentConfig, DependencyPoolConfig
)


class TestConfigValidationFailures:
    """测试配置验证各种失败情况"""

    def test_missing_required_fields(self):
        """测试缺少必需字段的情况"""
        config_content = """
meta:
  environment: dev
# 缺少 version 字段
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            with pytest.raises(Exception):
                load_unified_config(config_path)
        finally:
            os.unlink(config_path)

    def test_invalid_environment_value(self):
        """测试无效的环境值"""
        config_content = """
    meta:
      environment: invalid_env  # 无效的环境值
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
    model_providers: {}
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该允许自定义环境值，不抛出异常
            config = load_unified_config(config_path)
            assert config.meta.environment == "invalid_env"
        finally:
            os.unlink(config_path)

    def test_invalid_model_provider_type(self):
        """测试无效的模型提供者类型"""
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
      invalid_provider:
        type: invalid_type  # 无效的提供者类型
        api_key: test_key
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该允许未知类型，不在配置加载时验证
            config = load_unified_config(config_path)
            assert config.model_providers["invalid_provider"].type == "invalid_type"
        finally:
            os.unlink(config_path)

    def test_missing_model_provider_for_agent(self):
        """测试agent引用不存在的模型提供者"""
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
      existing_provider:
        type: openrouter
        api_key: test_key
    mcp_services: {}
    agents:
      test_agent:
        model_provider: nonexistent_provider  # 引用不存在的提供者
    dependency_pools: {}
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            with pytest.raises(ValueError, match="unknown model_provider"):
                load_unified_config(config_path)
        finally:
            os.unlink(config_path)

    def test_invalid_dependency_pool_type(self):
        """测试无效的依赖池类型"""
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
    model_providers: {}
    mcp_services: {}
    agents: {}
    dependency_pools:
      invalid_pool:
        type: invalid_type  # 无效的池类型
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该允许未知类型，不在配置加载时验证
            config = load_unified_config(config_path)
            assert config.dependency_pools["invalid_pool"].type == "invalid_type"
        finally:
            os.unlink(config_path)

    def test_agent_references_unknown_dependency_pool(self):
        """测试agent引用不存在的依赖池"""
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
      openrouter:
        type: openrouter
        api_key: test_key
    mcp_services: {}
    agents:
      test_agent:
        model_provider: openrouter
        dependency_pools: [nonexistent_pool]  # 引用不存在的池
    dependency_pools:
      existing_pool:
        type: filesystem
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 这个验证在配置加载时不执行，在运行时执行
            config = load_unified_config(config_path)
            assert "nonexistent_pool" in config.agents["test_agent"].dependency_pools
        finally:
            os.unlink(config_path)

    def test_invalid_yaml_syntax(self):
        """测试无效的YAML语法"""
        config_content = """
meta:
  environment: dev
  version: 1
invalid_yaml: [unclosed bracket  # 无效的YAML语法
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            with pytest.raises(Exception):  # YAML解析错误
                load_unified_config(config_path)
        finally:
            os.unlink(config_path)

    def test_empty_config_file(self):
        """测试空配置文件"""
        config_content = ""  # 空文件

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            with pytest.raises(Exception):
                load_unified_config(config_path)
        finally:
            os.unlink(config_path)

    def test_nonexistent_config_file(self):
        """测试不存在的配置文件"""
        with pytest.raises(FileNotFoundError):
            load_unified_config("/nonexistent/config.yaml")

    def test_invalid_file_permissions(self):
        """测试无效的文件权限"""
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
    model_providers: {}
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 移除读权限
            os.chmod(config_path, 0o000)
            with pytest.raises(PermissionError):
                load_unified_config(config_path)
        finally:
            # 恢复权限后删除
            os.chmod(config_path, 0o644)
            os.unlink(config_path)

    def test_environment_variable_not_found(self):
        """测试未找到的环境变量"""
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
        api_key: ${NONEXISTENT_VAR}  # 不存在的环境变量
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """

        # 确保环境变量不存在
        if "NONEXISTENT_VAR" in os.environ:
            del os.environ["NONEXISTENT_VAR"]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该正常加载，但保留未解析的环境变量
            config = load_unified_config(config_path)
            assert config.model_providers["test_provider"].api_key == "${NONEXISTENT_VAR}"
        finally:
            os.unlink(config_path)

    def test_invalid_max_context_tokens(self):
        """测试无效的最大上下文token数"""
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
      test_agent:
        model_provider: test_provider
        max_context_tokens: -1  # 无效的负数
    dependency_pools: {}
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该允许负数，不在配置加载时验证
            config = load_unified_config(config_path)
            assert config.agents["test_agent"].max_context_tokens == -1
        finally:
            os.unlink(config_path)

    def test_duplicate_agent_names(self):
        """测试重复的agent名称"""
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
      duplicate_agent:
        model_provider: test_provider
      duplicate_agent:  # 重复的agent名称
        model_provider: test_provider
    dependency_pools: {}
    """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # YAML会用后面的值覆盖前面的值
            config = load_unified_config(config_path)
            assert len(config.agents) == 1  # 只会有一个agent
            assert "duplicate_agent" in config.agents
        finally:
            os.unlink(config_path)

    def test_build_agent_runtime_missing_config(self):
        """测试构建agent运行时时缺少配置"""
        with pytest.raises(AttributeError):
            build_agent_runtime(None, "test_agent")

    def test_invalid_sandbox_strategy(self):
        """测试无效的沙箱策略"""
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
      default_strategy: invalid_strategy  # 无效的策略
      strategies:
        subprocess:
          max_concurrency: 8
    model_providers: {}
    mcp_services: {}
    agents: {}
    dependency_pools: {}
    """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            # 应该允许不存在的默认策略，不在配置加载时验证
            config = load_unified_config(config_path)
            assert config.sandbox.default_strategy == "invalid_strategy"
        finally:
            os.unlink(config_path)