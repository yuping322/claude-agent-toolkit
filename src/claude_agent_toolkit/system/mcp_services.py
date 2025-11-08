#!/usr/bin/env python3
# mcp_services.py - MCP service registry abstraction

import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .observability import event_bus, BaseEvent
from .config import McpServiceConfig

@dataclass
class McpServiceHandle:
    name: str
    config: McpServiceConfig
    started: bool = False
    # In real implementation: process handle / server object

class McpServiceRegistry:
    def __init__(self):
        self._services: Dict[str, McpServiceHandle] = {}

    async def register(self, name: str, config: McpServiceConfig) -> McpServiceHandle:
        handle = McpServiceHandle(name=name, config=config)
        self._services[name] = handle
        event_bus.publish(BaseEvent(event_type="mcp.register", component="mcp_registry", data={"service": name}))
        return handle

    async def start_all(self) -> None:
        """Start all registered MCP services with lifecycle events."""
        for h in self._services.values():
            if not h.started:
                try:
                    # Emit pre-start event
                    event_bus.publish(BaseEvent(
                        event_type="mcp.lifecycle",
                        component="mcp_registry",
                        data={
                            "service": h.name,
                            "phase": "starting",
                            "type": h.config.type
                        }
                    ))
                    
                    # For now, simulate successful startup (in real implementation: start MCP server process)
                    # TODO: Implement actual MCP server process management
                    await asyncio.sleep(0.05)  # Simulate startup time
                    
                    h.started = True
                    event_bus.publish(BaseEvent(
                        event_type="mcp.lifecycle",
                        component="mcp_registry",
                        data={
                            "service": h.name,
                            "phase": "started",
                            "type": h.config.type,
                            "tools_count": 3  # Placeholder for actual tool count
                        }
                    ))
                        
                except Exception as e:
                    event_bus.publish(BaseEvent(
                        event_type="mcp.lifecycle",
                        component="mcp_registry",
                        data={
                            "service": h.name,
                            "phase": "error",
                            "type": h.config.type,
                            "error": str(e)
                        }
                    ))

    async def stop_all(self) -> None:
        """Stop all running MCP services with lifecycle events."""
        for h in self._services.values():
            if h.started:
                try:
                    # Emit pre-stop event
                    event_bus.publish(BaseEvent(
                        event_type="mcp.lifecycle",
                        component="mcp_registry",
                        data={
                            "service": h.name,
                            "phase": "stopping",
                            "type": h.config.type
                        }
                    ))
                    
                    # Simulate service shutdown
                    await asyncio.sleep(0.02)  # Simulate shutdown time
                    
                    h.started = False
                    event_bus.publish(BaseEvent(
                        event_type="mcp.lifecycle",
                        component="mcp_registry",
                        data={
                            "service": h.name,
                            "phase": "stopped",
                            "type": h.config.type
                        }
                    ))
                    
                except Exception as e:
                    event_bus.publish(BaseEvent(
                        event_type="mcp.lifecycle",
                        component="mcp_registry",
                        data={
                            "service": h.name,
                            "phase": "error",
                            "type": h.config.type,
                            "error": str(e)
                        }
                    ))

    def list_tools(self) -> List[Dict[str, Any]]:
        # Placeholder: transform services to tools meta
        tools = []
        for h in self._services.values():
            tools.append({
                "name": h.name,
                "type": h.config.type,
                "ready": h.started
            })
        return tools

__all__ = ["McpServiceRegistry","McpServiceHandle"]
