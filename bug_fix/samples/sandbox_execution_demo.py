#!/usr/bin/env python3
"""
Sandbox Execution Demo

This sample demonstrates how to use the Claude Agent Toolkit's sandbox
execution system with different strategies and resource management.

Features demonstrated:
- Sandbox session creation
- Command execution with resource monitoring
- Resource limit enforcement
- Timeout handling
- Event emission during execution
- Multiple execution strategies
"""

import asyncio
import time
from claude_agent_toolkit.system.sandbox import SandboxManager, SandboxSession
from claude_agent_toolkit.system.config import SandboxStrategyConfig
from claude_agent_toolkit.system.observability import event_bus, SandboxExecutionEvent


async def demo_sandbox_execution():
    """Demonstrate sandbox execution functionality."""

    print("🏖️  Claude Agent Toolkit - Sandbox Execution Demo")
    print("=" * 60)

    # Initialize sandbox manager with different strategies
    strategies = {
        "subprocess_basic": SandboxStrategyConfig(
            max_concurrency=2,
            hard_cpu_limit_pct=50,
            memory_limit_mb=100
        ),
        "subprocess_heavy": SandboxStrategyConfig(
            max_concurrency=1,
            hard_cpu_limit_pct=80,
            memory_limit_mb=512
        )
    }

    manager = SandboxManager(strategies)
    print("✅ Sandbox manager initialized with strategies:"    for name, config in strategies.items():
        print(f"   {name}: CPU limit {config.hard_cpu_limit_pct}%, Memory limit {config.memory_limit_mb}MB")

    # Set up event listener
    execution_events = []
    def event_handler(event):
        if isinstance(event, SandboxExecutionEvent):
            execution_events.append(event)
            phase = "▶️ " if event.phase == "start" else "⏹️ "
            print(f"{phase} Sandbox Event: {event.phase} - Agent: {event.agent_id}")

    event_bus.subscribe("sandbox.exec", event_handler)

    # Demo 1: Successful command execution
    print("\n🔄 Demo 1: Successful command execution")

    session = await manager.create_session("demo_agent", "subprocess_basic")
    print(f"✅ Created sandbox session for agent: {session.agent_id}")

    result = await manager.run(session, "echo 'Hello from sandbox!' && sleep 1")
    print("📊 Execution result:"    print(f"   Success: {result.success}")
    print(f"   Stdout: {result.stdout.strip()}")
    print(f"   Stderr: {result.stderr}")
    print(".2f"
    # Demo 2: Command with resource usage
    print("\n📈 Demo 2: Resource-intensive command")

    session2 = await manager.create_session("demo_agent", "subprocess_heavy")
    result2 = await manager.run(session2, "dd if=/dev/zero of=/dev/null bs=1M count=10")
    print("📊 Resource usage result:"    print(f"   Success: {result2.success}")
    print(".2f"
    # Demo 3: Command timeout
    print("\n⏰ Demo 3: Command timeout handling")

    session3 = await manager.create_session("demo_agent", "subprocess_basic")
    result3 = await manager.run(session3, "sleep 35")  # Longer than timeout
    print("📊 Timeout result:"    print(f"   Success: {result3.success}")
    print(f"   Stdout: '{result3.stdout}'")
    print(f"   Stderr preview: {result3.stderr[:100]}...")
    print(".2f"
    # Demo 4: Failed command
    print("\n❌ Demo 4: Failed command execution")

    session4 = await manager.create_session("demo_agent", "subprocess_basic")
    result4 = await manager.run(session4, "false")  # Command that always fails
    print("📊 Failed command result:"    print(f"   Success: {result4.success}")
    print(f"   Stdout: '{result4.stdout}'")
    print(f"   Stderr: '{result4.stderr.strip()}'")
    print(".2f"
    # Demo 5: Event emission summary
    print(f"\n📢 Demo 5: Event emission ({len(execution_events)} events captured)")
    for i, event in enumerate(execution_events, 1):
        print(f"   Event {i}: {event.phase} phase")
        print(f"      Agent: {event.agent_id}")
        print(f"      Strategy: {event.sandbox_strategy}")
        print(f"      Command: {event.command[:50]}...")
        print(".2f"        if hasattr(event, 'data') and event.data:
            cpu_used = event.data.get('actual_cpu_used', 'N/A')
            mem_used = event.data.get('actual_memory_mb', 'N/A')
            print(f"      Resources: CPU {cpu_used}%, Memory {mem_used}MB")

    # Demo 6: Session cleanup
    print("\n🧹 Demo 6: Session cleanup")

    await manager.cleanup(session)
    await manager.cleanup(session2)
    await manager.cleanup(session3)
    await manager.cleanup(session4)
    print("✅ All sandbox sessions cleaned up")

    print("\n🎉 Sandbox execution demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(demo_sandbox_execution())