#!/usr/bin/env python3
# initialize.py - System bootstrap

import asyncio
from typing import Dict, Any

from .config import load_unified_config, UnifiedConfig, build_agent_runtime, AgentRuntimeConfig
from .model_provider import OpenRouterProvider, ModelProvider
from .usage import UsageTracker
from .mcp_services import McpServiceRegistry
from .sandbox import SandboxManager
from .observability import event_bus, BaseEvent
from ..agent.dependency_pool import initialize_shared_dependencies

_state: Dict[str, Any] = {
    "config": None,
    "providers": {},
    "usage_tracker": None,
    "mcp_registry": None,
    "sandbox_manager": None,
    "dependency_manager": None
}

async def initialize_system(config_path: str) -> None:
    cfg = load_unified_config(config_path)
    _state["config"] = cfg

    # Providers
    providers: Dict[str, ModelProvider] = {}
    for name, pcfg in cfg.model_providers.items():
        if pcfg.type == "openrouter" and pcfg.api_key and not pcfg.api_key.startswith("${"):
            # Use provided base_url or default to OpenRouter's standard endpoint
            base_url = pcfg.base_url or "https://openrouter.ai/api/v1"
            providers[name] = OpenRouterProvider(
                name=name,
                api_key=pcfg.api_key,
                base_url=base_url,
                model="gpt-4",
                pricing={
                    "input_token_usd": pcfg.pricing.input_token_usd if pcfg.pricing else 0.0,
                    "output_token_usd": pcfg.pricing.output_token_usd if pcfg.pricing else 0.0,
                }
            )
        else:
            # Placeholder generic provider could be added
            pass
    _state["providers"] = providers

    # Usage tracker
    usage = UsageTracker(interval_s=60)
    for p in providers.values():
        usage.register(p)
    usage.start()
    _state["usage_tracker"] = usage

    # MCP services
    mcp = McpServiceRegistry()
    for name, scfg in cfg.mcp_services.items():
        await mcp.register(name, scfg)
    # Defer start (lazy) or start immediately if desired
    _state["mcp_registry"] = mcp

    # Sandbox manager
    sandbox_mgr = SandboxManager(cfg.sandbox.strategies)
    _state["sandbox_manager"] = sandbox_mgr

    # Dependency pools
    dep_config = {
        "pools": {name: {"type": pcfg.type, "allowed_paths": pcfg.paths or [], "max_instances": pcfg.max_instances or 5}
                 for name, pcfg in cfg.dependency_pools.items()},
        "agents": {name: {"dependencies": acfg.dependency_pools}
                  for name, acfg in cfg.agents.items()}
    }
    dep_mgr = await initialize_shared_dependencies(dep_config)
    _state["dependency_manager"] = dep_mgr

    event_bus.publish(BaseEvent(event_type="system.init", component="bootstrap", data={"providers": list(providers.keys())}))

def get_agent_runtime(agent_name: str) -> AgentRuntimeConfig:
    cfg: UnifiedConfig = _state.get("config")
    if not cfg:
        raise RuntimeError("System not initialized")
    return build_agent_runtime(cfg, agent_name)

__all__ = ["initialize_system","get_agent_runtime"]
