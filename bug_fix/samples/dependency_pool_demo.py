#!/usr/bin/env python3
"""
Dependency Pool Demo

This sample demonstrates how to use the Claude Agent Toolkit's dependency
pool system for managing shared resources across multiple agents.

Features demonstrated:
- FileSystem pool creation and management
- Concurrent access to shared resources
- Resource acquisition and release
- Pool statistics and monitoring
- Event emission for pool operations
- Cleanup of expired instances
"""

import asyncio
import tempfile
import os
from pathlib import Path
from claude_agent_toolkit.agent.dependency_pool import FileSystemPool, SharedDependencyManager
from claude_agent_toolkit.system.observability import event_bus, DependencyPoolEvent


async def demo_dependency_pool():
    """Demonstrate dependency pool functionality."""

    print("🏊 Claude Agent Toolkit - Dependency Pool Demo")
    print("=" * 60)

    # Create temporary directories for testing
    temp_dir1 = Path(tempfile.mkdtemp(prefix="pool_test_"))
    temp_dir2 = Path(tempfile.mkdtemp(prefix="pool_test_"))

    try:
        # Demo 1: Basic FileSystem pool operations
        print("\n📁 Demo 1: FileSystem pool operations")

        pool = FileSystemPool([str(temp_dir1), str(temp_dir2)], max_instances=3)
        print("✅ Created FileSystem pool"        print(f"   Allowed paths: {pool.allowed_paths}")
        print(f"   Max instances: {pool.max_instances}")

        # Set up event listener
        pool_events = []
        def event_handler(event):
            if isinstance(event, DependencyPoolEvent):
                pool_events.append(event)
                print(f"📢 Pool Event: {event.action} - Agent: {event.agent_id}, In use: {event.in_use}")

        event_bus.subscribe("dependency.pool", event_handler)

        # Acquire instance
        instance1 = await pool.acquire("agent_1")
        print("✅ Agent 1 acquired filesystem instance"        print(f"   Instance type: {type(instance1).__name__}")

        # Get pool stats
        stats = pool.get_stats()
        print("📊 Pool statistics:"        print(f"   In use: {stats['in_use']}")
        print(f"   Available: {stats['available']}")
        print(f"   Total created: {stats['total_created']}")

        # Demo 2: Concurrent access
        print("\n🔄 Demo 2: Concurrent access simulation")

        async def agent_workload(agent_id: str):
            """Simulate agent workload with dependency usage"""
            try:
                instance = await pool.acquire(agent_id, timeout=5.0)
                print(f"✅ {agent_id} acquired instance")

                # Simulate work
                await asyncio.sleep(0.1)

                await pool.release(agent_id)
                print(f"🔄 {agent_id} released instance")

                return f"{agent_id} completed successfully"
            except Exception as e:
                return f"{agent_id} failed: {e}"

        # Run multiple agents concurrently
        agents = [f"agent_{i}" for i in range(2, 5)]  # agent_2, agent_3, agent_4
        tasks = [agent_workload(agent) for agent in agents]
        results = await asyncio.gather(*tasks)

        print("📋 Concurrent access results:")
        for result in results:
            print(f"   {result}")

        # Demo 3: Pool limits and timeouts
        print("\n⏰ Demo 3: Pool limits and timeout handling")

        # Fill the pool
        instances = []
        for i in range(3):  # Max instances
            try:
                inst = await pool.acquire(f"limit_agent_{i}", timeout=1.0)
                instances.append((f"limit_agent_{i}", inst))
                print(f"✅ Acquired instance for limit_agent_{i}")
            except TimeoutError:
                print(f"❌ Failed to acquire for limit_agent_{i} (pool full)")

        # Try to acquire one more (should timeout)
        try:
            extra_inst = await pool.acquire("extra_agent", timeout=1.0)
            print("❌ Unexpectedly acquired extra instance")
        except TimeoutError:
            print("✅ Correctly timed out when pool is full")

        # Release instances
        for agent_id, _ in instances:
            await pool.release(agent_id)
            print(f"🔄 Released instance for {agent_id}")

        # Demo 4: Cleanup operations
        print("\n🧹 Demo 4: Cleanup operations")

        # Manually expire some instances by setting old creation time
        import time
        from datetime import datetime

        # Get current instances
        current_instances = list(pool._creation_times.keys())
        if current_instances:
            # Make one instance "old"
            old_instance = current_instances[0]
            old_time = datetime.now().timestamp() - 7200  # 2 hours ago
            pool._creation_times[old_instance] = datetime.fromtimestamp(old_time)
            print(f"⏰ Marked instance as expired (2 hours old)")

            # Run cleanup (1 hour expiry)
            cleaned_count = await pool.cleanup_expired(3600)
            print(f"🗑️  Cleaned up {cleaned_count} expired instances")

        # Demo 5: Shared dependency manager
        print("\n🤝 Demo 5: Shared dependency manager")

        manager = SharedDependencyManager()

        # Register pools
        await manager.register_pool("filesystem", pool)
        print("✅ Registered filesystem pool with manager")

        # Register agents
        await manager.register_agent("web_agent", ["filesystem"])
        await manager.register_agent("api_agent", ["filesystem"])
        print("✅ Registered agents with manager")

        # Agents acquire dependencies through manager
        fs1 = await manager.get_dependency("web_agent", "filesystem")
        fs2 = await manager.get_dependency("api_agent", "filesystem")
        print("✅ Agents acquired dependencies through manager")

        # Get manager stats
        mgr_stats = manager.get_stats()
        print("📊 Manager statistics:"        print(f"   Total pools: {mgr_stats['total_pools']}")
        print(f"   Total agents: {mgr_stats['total_agents']}")
        print(f"   Pool details: {list(mgr_stats['pools'].keys())}")

        # Release through manager
        await manager.release_agent_dependencies("web_agent")
        await manager.release_agent_dependencies("api_agent")
        print("🔄 Released all agent dependencies")

        # Demo 6: Event summary
        print(f"\n📢 Demo 6: Event emission ({len(pool_events)} events captured)")
        event_counts = {}
        for event in pool_events:
            event_counts[event.action] = event_counts.get(event.action, 0) + 1

        print("📈 Event breakdown:")
        for action, count in event_counts.items():
            print(f"   {action}: {count} events")

        print("\n🎉 Dependency pool demo completed successfully!")

    finally:
        # Cleanup temporary directories
        import shutil
        shutil.rmtree(temp_dir1, ignore_errors=True)
        shutil.rmtree(temp_dir2, ignore_errors=True)
        print(f"\n🧹 Cleaned up temporary directories")


if __name__ == "__main__":
    asyncio.run(demo_dependency_pool())