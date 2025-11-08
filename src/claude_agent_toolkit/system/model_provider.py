#!/usr/bin/env python3
# model_provider.py - Provider abstraction & OpenRouter stub

from __future__ import annotations
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel
import httpx

from .observability import event_bus, ModelInvocationEvent

class ModelResult(BaseModel):
    text: str
    raw: Dict[str, Any]
    tokens_input: int
    tokens_output: int
    latency_ms: float
    cost_usd: float

class ModelProvider(ABC):
    name: str
    pricing: Optional[Dict[str, float]] = None  # {'input_token_usd': x, 'output_token_usd': y}

    def __init__(self, name: str, pricing: Optional[Dict[str, float]] = None):
        self.name = name
        self.pricing = pricing or {"input_token_usd": 0.0, "output_token_usd": 0.0}
        self._requests = 0
        self._tokens_in = 0
        self._tokens_out = 0
        self._cost_total = 0.0

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> ModelResult:
        ...

    def _update_usage(self, result: ModelResult):
        self._requests += 1
        self._tokens_in += result.tokens_input
        self._tokens_out += result.tokens_output
        self._cost_total += result.cost_usd

    def usage_snapshot(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "requests_total": self._requests,
            "tokens_in_total": self._tokens_in,
            "tokens_out_total": self._tokens_out,
            "cost_total_usd": round(self._cost_total, 6)
        }

class OpenRouterProvider(ModelProvider):
    def __init__(self, name: str, api_key: str, base_url: str, model: str = "gpt-4", pricing: Optional[Dict[str, float]] = None):
        super().__init__(name, pricing)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=30)

    async def generate(self, prompt: str, **kwargs) -> ModelResult:
        t0 = time.time()
        # OpenAI-compatible chat completions format
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1000,
            "temperature": 0.7
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            resp = await self._client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = await resp.json()
            # Extract response from OpenAI-compatible format
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            in_toks = usage.get("prompt_tokens", 0)
            out_toks = usage.get("completion_tokens", 0)
            latency_ms = (time.time() - t0) * 1000
            cost = in_toks * self.pricing.get("input_token_usd", 0.0) + out_toks * self.pricing.get("output_token_usd", 0.0)
            result = ModelResult(
                text=text,
                raw=data,
                tokens_input=in_toks,
                tokens_output=out_toks,
                latency_ms=latency_ms,
                cost_usd=round(cost, 6)
            )
            self._update_usage(result)
            event_bus.publish(ModelInvocationEvent(
                event_type="model.invocation",
                provider=self.name,
                tokens_input=in_toks,
                tokens_output=out_toks,
                latency_ms=latency_ms,
                cost_usd=round(cost, 6),
                component="model_provider"
            ))
            return result
        except Exception as e:
            # Emit failure event (still standardized)
            event_bus.publish(ModelInvocationEvent(
                event_type="model.invocation",
                provider=self.name,
                tokens_input=0,
                tokens_output=0,
                latency_ms=(time.time() - t0) * 1000,
                cost_usd=0.0,
                component="model_provider",
                data={"error": str(e)}
            ))
            raise

__all__ = ["ModelProvider", "OpenRouterProvider", "ModelResult"]
