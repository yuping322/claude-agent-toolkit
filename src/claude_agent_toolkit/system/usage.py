#!/usr/bin/env python3
# usage.py - UsageTracker for model providers

import time
import asyncio
from typing import Dict, List, Callable, Optional
from .model_provider import ModelProvider
from .observability import event_bus, ModelUsageEvent

class UsageTracker:
    def __init__(self, interval_s: int = 60):
        self._providers: Dict[str, ModelProvider] = {}
        self._interval = interval_s
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def register(self, provider: ModelProvider) -> None:
        self._providers[provider.name] = provider

    async def _loop(self):
        self._running = True
        while self._running:
            await asyncio.sleep(self._interval)
            for p in self._providers.values():
                snap = p.usage_snapshot()
                event_bus.publish(ModelUsageEvent(
                    event_type="model.usage",
                    provider=snap["provider"],
                    requests_total=snap["requests_total"],
                    tokens_in_total=snap["tokens_in_total"],
                    tokens_out_total=snap["tokens_out_total"],
                    cost_total_usd=snap["cost_total_usd"],
                    component="usage_tracker"
                ))

    def start(self):
        if not self._task:
            self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            await self._task
            self._task = None

__all__ = ["UsageTracker"]
