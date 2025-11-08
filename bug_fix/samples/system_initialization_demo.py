#!/usr/bin/env python3
"""
System Initialization Demo

This sample demonstrates how to initialize the Claude Agent Toolkit system
with configuration loading, component setup, and basic validation.

Features demonstrated:
- Loading unified configuration from YAML
- System initialization with all components
- Provider setup and validation
- MCP services registration
- Sandbox manager configuration
- Dependency pool initialization
- Event emission during initialization
"""

import asyncio
import tempfile
import os
from pathlib import Path
from claude_agent_toolkit.system.initialize import initialize_system, get_agent_runtime
from claude_agent_toolkit.system.observability import event_bus, BaseEvent


async def demo_system_initialization():
    """Demonstrate complete system initialization process."""

    print("🚀 Claude Agent Toolkit - System Initialization Demo")
    print("=" * 60)

    # Create a sample configuration
    config_content = """
meta:
  environment: demo
  version: 1.0
logging:
  level: INFO
  sinks:
    - type: stdout
observability:
  enable: true
  event_buffer_size: 1000
  exporters:
    - type: stdout
sandbox:
  default_strategy: subprocess
  strategies:
    subprocess:
      max_concurrency: 4
      hard_cpu_limit_pct: 80
      memory_limit_mb: 512
model_providers:
  demo_provider:
    type: openrouter
    api_key: demo_key_123
    base_url: https://openrouter.ai/api/v1
    pricing:
      input_token_usd: 0.000001
      output_token_usd: 0.000002
mcp_services:
  filesystem_demo:
    type: filesystem
    root: /tmp
  git_demo:
    type: git
agents:
  demo_agent:
    model_provider: demo_provider
    sandbox_strategy: subprocess
    tools: [filesystem_demo]
    dependency_pools: [demo_pool]
    max_context_tokens: 100000
dependency_pools:
  demo_pool:
    type: filesystem
    paths: [/tmp, /var/tmp]
    max_instances: 3
"""

    # Write config to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        config_path = f.name

    try:
        print("📝 Created sample configuration file")

        # Set up event listener to capture initialization events
        init_events = []
        def event_handler(event):
            if isinstance(event, BaseEvent):
                init_events.append(event)
                print(f"📢 Event: {event.event_type} - {event.component}")

        event_bus.subscribe("system.init", event_handler)

        print("\n🔧 Initializing system...")
        await initialize_system(config_path)

        print("✅ System initialization completed!")
        print(f"📊 Captured {len(init_events)} initialization events")

        # Demonstrate getting agent runtime
        print("\n🤖 Getting agent runtime configuration...")
        try:
            runtime_config = get_agent_runtime("demo_agent")
            print("✅ Agent runtime configuration retrieved")
            print(f"   Agent: {runtime_config.name}")
            print(f"   Provider: {runtime_config.provider.type}")
            print(f"   Tools: {list(runtime_config.tools.keys())}")
            print(f"   Dependency Pools: {list(runtime_config.dependency_pools.keys())}")
            print(f"   Max Context Tokens: {runtime_config.max_context_tokens}")

        except Exception as e:
            print(f"❌ Failed to get agent runtime: {e}")

        # Demonstrate error handling - try to get non-existent agent
        print("\n❌ Testing error handling - requesting non-existent agent...")
        try:
            get_agent_runtime("nonexistent_agent")
        except ValueError as e:
            print(f"✅ Correctly caught error: {e}")

        print("\n🎉 System initialization demo completed successfully!")

    finally:
        # Cleanup
        os.unlink(config_path)
        print(f"\n🧹 Cleaned up temporary config file: {config_path}")


if __name__ == "__main__":
    asyncio.run(demo_system_initialization())