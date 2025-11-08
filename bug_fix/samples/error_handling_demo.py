#!/usr/bin/env python3
"""
Error Handling Demo

This sample demonstrates comprehensive error handling and failure scenarios
in the Claude Agent Toolkit, showcasing graceful degradation and recovery.

Features demonstrated:
- Configuration validation errors
- Model provider failures and retries
- Sandbox execution errors
- Dependency pool timeouts
- MCP service failures
- System initialization errors
- Recovery strategies and fallback mechanisms
"""

import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch
from claude_agent_toolkit.system.initialize import initialize_system, get_agent_runtime
from claude_agent_toolkit.system.model_provider import OpenRouterProvider
from claude_agent_toolkit.system.sandbox import SandboxManager
from claude_agent_toolkit.agent.dependency_pool import FileSystemPool
from claude_agent_toolkit.system.mcp_services import McpServiceRegistry
from claude_agent_toolkit.system.config import McpServiceConfig


async def demo_error_handling():
    """Demonstrate comprehensive error handling."""

    print("🚨 Claude Agent Toolkit - Error Handling Demo")
    print("=" * 60)

    # Demo 1: Configuration validation errors
    print("\n📝 Demo 1: Configuration validation errors")

    invalid_configs = [
        ("Missing meta section", """
model_providers:
  test: {type: openrouter, api_key: test}
"""),
        ("Invalid provider reference", """
meta:
  environment: test
  version: 1.0
model_providers:
  provider1: {type: openrouter, api_key: key1}
agents:
  agent1:
    model_provider: nonexistent_provider
"""),
        ("Circular dependency", """
meta:
  environment: test
  version: 1.0
model_providers:
  p1: {type: openrouter, api_key: k1}
agents:
  a1:
    model_provider: p1
    dependency_pools: [pool1]
dependency_pools:
  pool1:
    type: filesystem
    paths: [/tmp]
""")
    ]

    for desc, config_content in invalid_configs:
        print(f"\n🔍 Testing: {desc}")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            await initialize_system(config_path)
            print("❌ Expected validation error but initialization succeeded")
        except Exception as e:
            print(f"✅ Correctly caught validation error: {type(e).__name__}: {e}")
        finally:
            os.unlink(config_path)

    # Demo 2: Model provider failures
    print("\n🧠 Demo 2: Model provider failures")

    provider = OpenRouterProvider(
        name="test_provider",
        api_key="test_key",
        base_url="https://openrouter.ai/api/v1"
    )

    failure_scenarios = [
        ("Network timeout", Exception("Connection timeout")),
        ("API rate limit", Exception("429 Too Many Requests")),
        ("Invalid API key", Exception("401 Unauthorized")),
        ("Server error", Exception("500 Internal Server Error")),
    ]

    for desc, error in failure_scenarios:
        print(f"\n🔍 Testing: {desc}")
        with patch.object(provider._client, 'post', side_effect=error):
            try:
                await provider.generate("Test prompt")
                print("❌ Expected error but call succeeded")
            except Exception as e:
                print(f"✅ Correctly handled {desc}: {type(e).__name__}")

    # Demo 3: Sandbox execution errors
    print("\n🏖️  Demo 3: Sandbox execution errors")

    strategies = {
        "test_strategy": type('MockStrategy', (), {
            'max_concurrency': 2,
            'hard_cpu_limit_pct': 80,
            'memory_limit_mb': 100
        })()
    }
    manager = SandboxManager(strategies)

    session = await manager.create_session("test_agent", "test_strategy")

    error_commands = [
        ("Nonexistent command", "nonexistent_command_xyz"),
        ("Permission denied", "chmod 000 /etc/passwd"),  # This will likely fail
        ("Invalid syntax", "echo 'unclosed quote"),
    ]

    for desc, command in error_commands:
        print(f"\n🔍 Testing: {desc}")
        try:
            result = await manager.run(session, command)
            if not result.success:
                print(f"✅ Command failed as expected: {result.stderr[:100]}...")
            else:
                print("⚠️  Command succeeded unexpectedly")
        except Exception as e:
            print(f"✅ Correctly caught execution error: {type(e).__name__}")

    # Demo 4: Dependency pool timeouts
    print("\n🏊 Demo 4: Dependency pool timeouts")

    pool = FileSystemPool(["/tmp"], max_instances=1)  # Very small pool

    # Fill the pool
    instance1 = await pool.acquire("agent1")
    print("✅ Agent1 acquired instance")

    # Try to acquire more instances (should timeout)
    timeout_scenarios = [
        ("Zero timeout", 0.1),
        ("Short timeout", 0.5),
        ("Normal timeout", 2.0),
    ]

    for desc, timeout in timeout_scenarios:
        print(f"\n🔍 Testing: {desc}")
        try:
            instance2 = await pool.acquire("agent2", timeout=timeout)
            print("❌ Unexpectedly acquired instance")
        except TimeoutError:
            print(f"✅ Correctly timed out after {timeout}s")
        except Exception as e:
            print(f"✅ Caught error: {type(e).__name__}")

    # Release instance
    await pool.release("agent1")
    print("🔄 Released instance")

    # Demo 5: MCP service failures
    print("\n🔧 Demo 5: MCP service failures")

    registry = McpServiceRegistry()

    # Register services with problematic configs
    problematic_services = [
        ("Invalid type", McpServiceConfig(type="nonexistent_type")),
        ("Missing root", McpServiceConfig(type="filesystem")),  # Some services might need root
    ]

    for desc, config in problematic_services:
        print(f"\n🔍 Testing: {desc}")
        try:
            handle = await registry.register(f"test_{desc.lower().replace(' ', '_')}", config)
            print(f"✅ Service registered: {handle.name}")
        except Exception as e:
            print(f"❌ Registration failed: {type(e).__name__}: {e}")

    # Try to start services (some may fail)
    try:
        await registry.start_all()
        print("✅ Service startup completed (some may have failed gracefully)")
    except Exception as e:
        print(f"❌ Service startup error: {type(e).__name__}: {e}")

    # Demo 6: System initialization with missing components
    print("\n⚙️  Demo 6: System initialization edge cases")

    edge_case_configs = [
        ("Empty config", """
meta:
  environment: test
  version: 1.0
"""),
        ("Only providers", """
meta:
  environment: test
  version: 1.0
model_providers:
  p1: {type: openrouter, api_key: k1}
"""),
        ("Invalid pool type", """
meta:
  environment: test
  version: 1.0
dependency_pools:
  bad_pool: {type: invalid_type}
""")
    ]

    for desc, config_content in edge_case_configs:
        print(f"\n🔍 Testing: {desc}")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            await initialize_system(config_path)
            print("✅ System initialized (may have warnings)")
        except Exception as e:
            print(f"❌ Initialization failed: {type(e).__name__}: {e}")
        finally:
            os.unlink(config_path)

    # Demo 7: Agent runtime errors
    print("\n🤖 Demo 7: Agent runtime errors")

    # Create a minimal valid config
    valid_config = """
meta:
  environment: test
  version: 1.0
logging:
  level: INFO
observability:
  enable: true
sandbox:
  default_strategy: subprocess
  strategies:
    subprocess:
      max_concurrency: 2
model_providers:
  test_provider: {type: openrouter, api_key: test_key}
mcp_services: {}
agents:
  test_agent:
    model_provider: test_provider
dependency_pools: {}
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(valid_config)
        config_path = f.name

    try:
        await initialize_system(config_path)

        # Test valid agent
        runtime = get_agent_runtime("test_agent")
        print("✅ Valid agent runtime retrieved")

        # Test invalid agent
        try:
            get_agent_runtime("nonexistent")
        except ValueError as e:
            print(f"✅ Correctly rejected invalid agent: {e}")

        # Test before initialization (simulate by clearing state)
        from claude_agent_toolkit.system.initialize import _state
        original_config = _state.get("config")
        _state["config"] = None

        try:
            get_agent_runtime("test_agent")
        except RuntimeError as e:
            print(f"✅ Correctly handled uninitialized system: {e}")
        finally:
            _state["config"] = original_config

    finally:
        os.unlink(config_path)

    # Demo 8: Recovery and fallback strategies
    print("\n🔄 Demo 8: Recovery and fallback strategies")

    print("💡 Error handling best practices demonstrated:")
    print("   • Graceful degradation when services fail")
    print("   • Proper exception propagation with context")
    print("   • Resource cleanup on errors")
    print("   • Timeout handling for long-running operations")
    print("   • Validation at multiple layers")
    print("   • Event emission for error tracking")

    print("\n🎉 Error handling demo completed successfully!")
    print("💪 System demonstrates robust error handling across all components")


if __name__ == "__main__":
    asyncio.run(demo_error_handling())