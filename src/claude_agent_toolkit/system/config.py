#!/usr/bin/env python3
# config.py - Unified global configuration schema

import os
import yaml
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from pathlib import Path
import re

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

# --- Sub Schemas -------------------------------------------------

class MetaConfig(BaseModel):
    environment: str = Field(default="dev")
    version: int = Field(default=1)

class LoggingSinkConfig(BaseModel):
    type: str = Field(description="stdout | file | memory")
    path: Optional[str] = None

class LoggingConfig(BaseModel):
    level: str = Field(default="INFO")
    sinks: List[LoggingSinkConfig] = Field(default_factory=lambda: [LoggingSinkConfig(type="stdout")])

class ObservabilityExporterConfig(BaseModel):
    type: str = Field(description="stdout | file | memory")
    path: Optional[str] = None

class ObservabilityConfig(BaseModel):
    enable: bool = True
    event_buffer_size: int = 10000
    exporters: List[ObservabilityExporterConfig] = Field(default_factory=lambda: [ObservabilityExporterConfig(type="stdout")])

class SandboxStrategyConfig(BaseModel):
    max_concurrency: int = 8
    hard_cpu_limit_pct: int = 90
    memory_limit_mb: Optional[int] = None
    network_policy: Optional[str] = None  # allow-all | deny-all | restricted

class SandboxConfig(BaseModel):
    default_strategy: str = Field(default="subprocess")
    strategies: Dict[str, SandboxStrategyConfig] = Field(default_factory=lambda: {"subprocess": SandboxStrategyConfig()})

class PricingModel(BaseModel):
    input_token_usd: float = Field(default=0.0)
    output_token_usd: float = Field(default=0.0)

class ModelProviderConfig(BaseModel):
    type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    pricing: Optional[PricingModel] = None

class McpServiceConfig(BaseModel):
    type: str
    root: Optional[str] = None
    extras: Dict[str, Any] = Field(default_factory=dict)

class AgentConfig(BaseModel):
    model_provider: str
    sandbox_strategy: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    dependency_pools: List[str] = Field(default_factory=list)
    max_context_tokens: Optional[int] = 120000

class DependencyPoolConfig(BaseModel):
    type: str
    paths: Optional[List[str]] = None
    max_instances: Optional[int] = 5

# Per-agent runtime resolved config
class AgentRuntimeConfig(BaseModel):
    name: str
    provider: ModelProviderConfig
    sandbox: SandboxStrategyConfig
    tools: Dict[str, McpServiceConfig]
    dependency_pools: Dict[str, DependencyPoolConfig]
    max_context_tokens: int

# --- Unified Root -------------------------------------------------
class UnifiedConfig(BaseModel):
    meta: MetaConfig
    logging: LoggingConfig
    observability: ObservabilityConfig
    sandbox: SandboxConfig
    model_providers: Dict[str, ModelProviderConfig]
    mcp_services: Dict[str, McpServiceConfig]
    agents: Dict[str, AgentConfig]
    dependency_pools: Dict[str, DependencyPoolConfig]

    @validator("agents")
    def _validate_agents(cls, v, values):
        providers = set((values.get("model_providers") or {}).keys())
        for name, cfg in v.items():
            if cfg.model_provider not in providers:
                raise ValueError(f"Agent '{name}' references unknown model_provider '{cfg.model_provider}'")
        return v

# --- Loader / Resolver -------------------------------------------

def _replace_env(s: str) -> str:
    def repl(m):
        var = m.group(1)
        return os.getenv(var, f"${{{var}}}")
    return _ENV_PATTERN.sub(repl, s)


def _walk_replace(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _walk_replace(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ _walk_replace(x) for x in obj ]
    if isinstance(obj, str):
        return _replace_env(obj)
    return obj


def load_unified_config(path: str) -> UnifiedConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    raw = yaml.safe_load(p.read_text()) or {}
    replaced = _walk_replace(raw)
    return UnifiedConfig(**replaced)


def build_agent_runtime(unified: UnifiedConfig, agent_name: str) -> AgentRuntimeConfig:
    if agent_name not in unified.agents:
        raise ValueError(f"Unknown agent: {agent_name}")
    a_cfg = unified.agents[agent_name]
    provider = unified.model_providers[a_cfg.model_provider]
    strat_name = a_cfg.sandbox_strategy or unified.sandbox.default_strategy
    if strat_name not in unified.sandbox.strategies:
        raise ValueError(f"Sandbox strategy '{strat_name}' not defined")
    sandbox = unified.sandbox.strategies[strat_name]
    tools = {t: unified.mcp_services[t] for t in a_cfg.tools if t in unified.mcp_services}
    dep_pools = {d: unified.dependency_pools[d] for d in a_cfg.dependency_pools if d in unified.dependency_pools}
    return AgentRuntimeConfig(
        name=agent_name,
        provider=provider,
        sandbox=sandbox,
        tools=tools,
        dependency_pools=dep_pools,
        max_context_tokens=a_cfg.max_context_tokens or 120000
    )

__all__ = [
    "UnifiedConfig","load_unified_config","build_agent_runtime","AgentRuntimeConfig"
]
