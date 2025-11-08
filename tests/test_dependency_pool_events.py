import asyncio
import pytest

from claude_agent_toolkit.agent.dependency_pool import DependencyPool
from claude_agent_toolkit.system.observability import event_bus, DependencyPoolEvent

@pytest.mark.asyncio
async def test_dependency_pool_event_acquire_release():
    events = []
    def handler(ev):
        events.append(ev)
    event_bus.subscribe("dependency.pool", handler)

    class DummyPool(DependencyPool[object]):
        def __init__(self):
            super().__init__("dummy", max_instances=1)
        async def create_instance(self):
            return object()
        async def destroy_instance(self, instance):
            return None
        async def validate_instance(self, instance) -> bool:
            return True

    pool = DummyPool()
    inst = await pool.acquire(agent_id="agent1")
    await pool.release("agent1")

    acquire_events = [e for e in events if isinstance(e, DependencyPoolEvent) and e.action == "acquire"]
    release_events = [e for e in events if isinstance(e, DependencyPoolEvent) and e.action == "release"]
    assert acquire_events, "Should emit acquire event"
    assert release_events, "Should emit release event"
    # basic structure checks
    ae = acquire_events[-1]
    assert ae.dependency_type == "dummy"
    assert ae.in_use in (0,1)
    assert ae.available >= 0
