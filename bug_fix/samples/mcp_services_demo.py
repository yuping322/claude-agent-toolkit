#!/usr/bin/env python3
"""
MCP Services Demo

This sample demonstrates how to use the Claude Agent Toolkit's MCP (Model
Context Protocol) service registry for managing external tool services.

Features demonstrated:
- MCP service registration
- Service lifecycle management (start/stop)
- Event emission during service operations
- Tool listing and metadata
- Error handling for service operations
"""

import asyncio
from claude_agent_toolkit.system.mcp_services import McpServiceRegistry
from claude_agent_toolkit.system.config import McpServiceConfig
from claude_agent_toolkit.system.observability import event_bus, BaseEvent


async def demo_mcp_services():
    """Demonstrate MCP services functionality."""

    print("🔧 Claude Agent Toolkit - MCP Services Demo")
    print("=" * 60)

    # Initialize registry
    registry = McpServiceRegistry()
    print("✅ Created MCP service registry")

    # Set up event listener
    mcp_events = []
    def event_handler(event):
        if isinstance(event, BaseEvent) and event.component == "mcp_registry":
            mcp_events.append(event)
            phase = event.data.get('phase', 'unknown')
            service = event.data.get('service', 'unknown')
            print(f"📢 MCP Event: {event.event_type} - {service}:{phase}")

    event_bus.subscribe("mcp.register", event_handler)
    event_bus.subscribe("mcp.lifecycle", event_handler)

    # Demo 1: Register MCP services
    print("\n📝 Demo 1: Registering MCP services")

    services_config = {
        "filesystem": McpServiceConfig(
            type="filesystem",
            root="/tmp"
        ),
        "git": McpServiceConfig(
            type="git"
        ),
        "database": McpServiceConfig(
            type="database",
            extras={"connection_string": "sqlite:///demo.db"}
        )
    }

    registered_services = []
    for name, config in services_config.items():
        handle = await registry.register(name, config)
        registered_services.append(handle)
        print(f"✅ Registered service: {name} (type: {config.type})")

    print(f"📊 Total registered services: {len(registry._services)}")

    # Demo 2: Start all services
    print("\n▶️  Demo 2: Starting all MCP services")

    await registry.start_all()
    print("✅ All services started")

    # Check service status
    started_count = sum(1 for h in registry._services.values() if h.started)
    print(f"📊 Services started: {started_count}/{len(registry._services)}")

    # Demo 3: List available tools
    print("\n🛠️  Demo 3: Listing available tools")

    tools = registry.list_tools()
    print("📋 Available tools:")
    for tool in tools:
        status = "✅ Ready" if tool['ready'] else "⏳ Starting"
        print(f"   {tool['name']} ({tool['type']}) - {status}")

    # Demo 4: Stop all services
    print("\n⏹️  Demo 4: Stopping all MCP services")

    await registry.stop_all()
    print("✅ All services stopped")

    # Check final status
    stopped_count = sum(1 for h in registry._services.values() if not h.started)
    print(f"📊 Services stopped: {stopped_count}/{len(registry._services)}")

    # Demo 5: Error handling
    print("\n❌ Demo 5: Error handling demonstration")

    # Try to register a service with invalid config
    try:
        invalid_config = McpServiceConfig(
            type="invalid_type",
            root="/nonexistent"
        )
        await registry.register("invalid_service", invalid_config)
        print("✅ Invalid service registered (registry accepts any type)")
    except Exception as e:
        print(f"❌ Failed to register invalid service: {e}")

    # Demo 6: Event emission summary
    print(f"\n📢 Demo 6: Event emission ({len(mcp_events)} events captured)")

    event_types = {}
    phases = {}

    for event in mcp_events:
        event_types[event.event_type] = event_types.get(event.event_type, 0) + 1
        if 'phase' in event.data:
            phase = event.data['phase']
            phases[phase] = phases.get(phase, 0) + 1

    print("📈 Event types:")
    for event_type, count in event_types.items():
        print(f"   {event_type}: {count} events")

    print("📈 Lifecycle phases:")
    for phase, count in phases.items():
        print(f"   {phase}: {count} events")

    # Demo 7: Service metadata inspection
    print("\n🔍 Demo 7: Service metadata inspection")

    for name, handle in registry._services.items():
        print(f"📄 Service: {name}")
        print(f"   Type: {handle.config.type}")
        print(f"   Started: {handle.started}")
        if handle.config.root:
            print(f"   Root: {handle.config.root}")
        if handle.config.extras:
            print(f"   Extras: {handle.config.extras}")

    print("\n🎉 MCP services demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(demo_mcp_services())