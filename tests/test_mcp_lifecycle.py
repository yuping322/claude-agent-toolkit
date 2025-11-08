import asyncio
import pytest

from claude_agent_toolkit.system.mcp_services import McpServiceRegistry
from claude_agent_toolkit.system.config import McpServiceConfig
from claude_agent_toolkit.system.observability import event_bus, BaseEvent

@pytest.mark.asyncio
async def test_mcp_service_lifecycle_events():
    """Test MCP service registry lifecycle events."""
    events = []
    def handler(ev):
        events.append(ev)
    
    event_bus.subscribe("mcp.lifecycle", handler)
    
    registry = McpServiceRegistry()
    
    # Register a service
    config = McpServiceConfig(type="filesystem", root="/tmp")
    handle = await registry.register("test_fs", config)
    
    # Start services
    await registry.start_all()
    
    # Stop services
    await registry.stop_all()
    
    # Check lifecycle events
    lifecycle_events = [e for e in events if isinstance(e, BaseEvent) and e.event_type == "mcp.lifecycle"]
    assert len(lifecycle_events) >= 3, f"Expected at least 3 lifecycle events, got {len(lifecycle_events)}"
    
    phases = [e.data.get("phase") for e in lifecycle_events]
    assert "starting" in phases
    assert "started" in phases
    assert "stopping" in phases
    assert "stopped" in phases