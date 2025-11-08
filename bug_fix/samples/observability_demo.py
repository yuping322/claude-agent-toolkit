#!/usr/bin/env python3
"""
Observability Demo

This sample demonstrates how to use the Claude Agent Toolkit's observability
system for event emission, logging, and system monitoring.

Features demonstrated:
- Event bus subscription and publishing
- Different event types (model, dependency, sandbox, state)
- Event buffering and retrieval
- Custom event handlers
- System monitoring and metrics
"""

import asyncio
import time
from claude_agent_toolkit.system.observability import (
    event_bus, BaseEvent, ModelInvocationEvent, DependencyPoolEvent,
    SandboxExecutionEvent, StateSnapshot, LogEvent
)


async def demo_observability():
    """Demonstrate observability functionality."""

    print("📊 Claude Agent Toolkit - Observability Demo")
    print("=" * 60)

    # Set up comprehensive event listener
    all_events = []
    event_counts = {}

    def comprehensive_handler(event):
        all_events.append(event)
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
        print(f"📢 Event: {event.event_type} | Component: {event.component or 'N/A'} | TS: {event.ts:.3f}")

    # Subscribe to all event types
    event_types = [
        "model.invocation", "dependency.pool", "sandbox.exec",
        "agent.state", "log", "system.init", "mcp.register", "mcp.lifecycle"
    ]

    for event_type in event_types:
        event_bus.subscribe(event_type, comprehensive_handler)

    print("✅ Subscribed to all event types")

    # Demo 1: Model invocation events
    print("\n🧠 Demo 1: Model invocation events")

    model_events = [
        ModelInvocationEvent(
            event_type="model.invocation",
            component="model_provider",
            provider="openrouter",
            tokens_input=150,
            tokens_output=75,
            latency_ms=1250.5,
            cost_usd=0.0025,
            data={"model": "gpt-4", "temperature": 0.7}
        ),
        ModelInvocationEvent(
            event_type="model.invocation",
            component="model_provider",
            provider="openrouter",
            tokens_input=200,
            tokens_output=50,
            latency_ms=980.0,
            cost_usd=0.0018,
            data={"error": "rate_limit_exceeded"}
        )
    ]

    for event in model_events:
        event_bus.publish(event)
        await asyncio.sleep(0.1)  # Simulate time between events

    # Demo 2: Dependency pool events
    print("\n🏊 Demo 2: Dependency pool events")

    pool_events = [
        DependencyPoolEvent(
            event_type="dependency.pool",
            component="dependency_pool",
            action="acquire",
            dependency_type="filesystem",
            agent_id="web_agent",
            in_use=1,
            available=2
        ),
        DependencyPoolEvent(
            event_type="dependency.pool",
            component="dependency_pool",
            action="release",
            dependency_type="filesystem",
            agent_id="web_agent",
            in_use=0,
            available=3
        ),
        DependencyPoolEvent(
            event_type="dependency.pool",
            component="dependency_pool",
            action="cleanup",
            dependency_type="filesystem",
            agent_id=None,
            in_use=0,
            available=3,
            data={"expired_count": 2}
        )
    ]

    for event in pool_events:
        event_bus.publish(event)
        await asyncio.sleep(0.05)

    # Demo 3: Sandbox execution events
    print("\n🏖️  Demo 3: Sandbox execution events")

    sandbox_events = [
        SandboxExecutionEvent(
            event_type="sandbox.exec",
            component="sandbox",
            agent_id="test_agent",
            sandbox_strategy="subprocess",
            phase="start",
            command="echo 'Hello World'",
            data={"cpu_limit_pct": 80, "memory_limit_mb": 512}
        ),
        SandboxExecutionEvent(
            event_type="sandbox.exec",
            component="sandbox",
            agent_id="test_agent",
            sandbox_strategy="subprocess",
            phase="finish",
            command="echo 'Hello World'",
            success=True,
            latency_ms=45.2,
            data={"exit_code": 0, "actual_cpu_used": 5.2, "actual_memory_mb": 25.1}
        )
    ]

    for event in sandbox_events:
        event_bus.publish(event)
        await asyncio.sleep(0.05)

    # Demo 4: Agent state snapshots
    print("\n🤖 Demo 4: Agent state snapshots")

    state_events = [
        StateSnapshot(
            event_type="agent.state",
            component="agent_core",
            agent_id="bug_fix_agent",
            stage="analyzing",
            pending_tasks=3,
            recent_message="Found syntax error in line 42"
        ),
        StateSnapshot(
            event_type="agent.state",
            component="agent_core",
            agent_id="bug_fix_agent",
            stage="executing",
            pending_tasks=1,
            recent_message="Applying fix for syntax error"
        ),
        StateSnapshot(
            event_type="agent.state",
            component="agent_core",
            agent_id="bug_fix_agent",
            stage="completed",
            pending_tasks=0,
            recent_message="Fix applied successfully"
        )
    ]

    for event in state_events:
        event_bus.publish(event)
        await asyncio.sleep(0.05)

    # Demo 5: Log events
    print("\n📝 Demo 5: Log events")

    log_events = [
        LogEvent(
            event_type="log",
            component="system",
            level="INFO",
            message="System initialization completed",
            data={"uptime": 120.5}
        ),
        LogEvent(
            event_type="log",
            component="agent",
            level="WARNING",
            message="High memory usage detected",
            data={"memory_mb": 850, "threshold_mb": 800}
        ),
        LogEvent(
            event_type="log",
            component="model_provider",
            level="ERROR",
            message="API rate limit exceeded",
            data={"retry_after": 60, "provider": "openrouter"}
        )
    ]

    for event in log_events:
        event_bus.publish(event)
        await asyncio.sleep(0.05)

    # Demo 6: System events
    print("\n⚙️  Demo 6: System events")

    system_events = [
        BaseEvent(
            event_type="system.init",
            component="bootstrap",
            data={"providers": ["openrouter"], "pools": ["filesystem", "claude_code"]}
        ),
        BaseEvent(
            event_type="mcp.register",
            component="mcp_registry",
            data={"service": "filesystem", "type": "filesystem"}
        ),
        BaseEvent(
            event_type="mcp.lifecycle",
            component="mcp_registry",
            data={"service": "filesystem", "phase": "started", "tools_count": 5}
        )
    ]

    for event in system_events:
        event_bus.publish(event)
        await asyncio.sleep(0.05)

    # Demo 7: Event buffer analysis
    print("\n📈 Demo 7: Event buffer analysis")

    recent_events = event_bus.recent(20)
    print(f"📊 Recent events in buffer: {len(recent_events)}")

    print("📈 Event type distribution:")
    for event_type, count in sorted(event_counts.items()):
        print(f"   {event_type}: {count} events")

    # Demo 8: Event filtering and analysis
    print("\n🔍 Demo 8: Event filtering and analysis")

    # Filter events by component
    component_events = {}
    for event in all_events:
        comp = event.component or "unknown"
        component_events[comp] = component_events.get(comp, 0) + 1

    print("🏷️  Events by component:")
    for component, count in sorted(component_events.items()):
        print(f"   {component}: {count} events")

    # Analyze model performance
    model_events_filtered = [e for e in all_events if isinstance(e, ModelInvocationEvent)]
    if model_events_filtered:
        total_latency = sum(e.latency_ms for e in model_events_filtered)
        total_cost = sum(e.cost_usd for e in model_events_filtered)
        avg_latency = total_latency / len(model_events_filtered)
        print("
🧠 Model performance summary:"        print(".2f"        print(".6f"        print(f"   Total requests: {len(model_events_filtered)}")

    # Analyze error events
    error_events = [e for e in all_events if 'error' in str(e.data).lower()]
    print(f"\n❌ Error events detected: {len(error_events)}")
    for event in error_events:
        error_info = event.data.get('error', 'Unknown error')
        print(f"   {event.event_type}: {error_info}")

    print(f"\n🎉 Observability demo completed! Total events captured: {len(all_events)}")


if __name__ == "__main__":
    asyncio.run(demo_observability())