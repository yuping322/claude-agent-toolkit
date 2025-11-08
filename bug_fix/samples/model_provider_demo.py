#!/usr/bin/env python3
"""
Model Provider Demo

This sample demonstrates how to use the Claude Agent Toolkit's model provider
system with OpenRouter API integration.

Features demonstrated:
- OpenRouter provider initialization
- Successful API calls with mock responses
- Error handling for API failures
- Usage tracking and cost calculation
- Event emission for model invocations
"""

import asyncio
from unittest.mock import AsyncMock, patch
from claude_agent_toolkit.system.model_provider import OpenRouterProvider
from claude_agent_toolkit.system.observability import event_bus, ModelInvocationEvent


async def demo_model_provider():
    """Demonstrate model provider functionality."""

    print("🧠 Claude Agent Toolkit - Model Provider Demo")
    print("=" * 60)

    # Initialize provider
    provider = OpenRouterProvider(
        name="demo_openrouter",
        api_key="demo_key_123",
        base_url="https://openrouter.ai/api/v1",
        model="gpt-4",
        pricing={
            "input_token_usd": 0.000001,
            "output_token_usd": 0.000002
        }
    )

    print("✅ OpenRouter provider initialized")
    print(f"   Name: {provider.name}")
    print(f"   Model: {provider.model}")
    print(f"   Base URL: {provider.base_url}")

    # Set up event listener
    invocation_events = []
    def event_handler(event):
        if isinstance(event, ModelInvocationEvent):
            invocation_events.append(event)
            print(f"📢 Model Event: {event.event_type} - Tokens: {event.tokens_input + event.tokens_output}")

    event_bus.subscribe("model.invocation", event_handler)

    # Demo 1: Successful API call with mocked response
    print("\n🔄 Demo 1: Successful API call (mocked)")

    mock_response = AsyncMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json = AsyncMock(return_value={
        "choices": [{
            "message": {
                "content": "Hello! This is a successful response from the OpenRouter API."
            }
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15
        }
    })
    mock_response.status_code = 200

    with patch.object(provider._client, 'post', return_value=mock_response):
        try:
            result = await provider.generate("Say hello to the user")
            print("✅ API call successful!")
            print(f"   Response: {result.text}")
            print(f"   Input tokens: {result.tokens_input}")
            print(f"   Output tokens: {result.tokens_output}")
            print(f"   Cost: ${result.cost_usd:.6f}")
            print(f"   Latency: {result.latency_ms:.2f}ms")
        except Exception as e:
            print(f"❌ API call failed: {e}")

    # Demo 2: API error handling
    print("\n❌ Demo 2: API error handling")

    mock_error_response = AsyncMock()
    mock_error_response.raise_for_status.side_effect = Exception("400 Bad Request: Invalid model")
    mock_error_response.status_code = 400

    with patch.object(provider._client, 'post', return_value=mock_error_response):
        try:
            result = await provider.generate("This should fail")
            print("❌ Unexpected success")
        except Exception as e:
            print(f"✅ Correctly caught API error: {e}")

    # Demo 3: Network error handling
    print("\n🌐 Demo 3: Network error handling")

    with patch.object(provider._client, 'post', side_effect=Exception("Connection timeout")):
        try:
            result = await provider.generate("This should fail due to network")
            print("❌ Unexpected success")
        except Exception as e:
            print(f"✅ Correctly caught network error: {e}")

    # Demo 4: Usage tracking
    print("\n📊 Demo 4: Usage tracking and statistics")

    usage_snapshot = provider.usage_snapshot()
    print("📈 Current usage statistics:")
    print(f"   Total requests: {usage_snapshot['requests_total']}")
    print(f"   Input tokens: {usage_snapshot['tokens_in_total']}")
    print(f"   Output tokens: {usage_snapshot['tokens_out_total']}")
    print(f"   Total cost: ${usage_snapshot['cost_total_usd']:.6f}")
    # Demo 5: Event emission
    print(f"\n📢 Demo 5: Event emission ({len(invocation_events)} events captured)")
    for i, event in enumerate(invocation_events, 1):
        print(f"   Event {i}: {event.event_type}")
        print(f"      Provider: {event.provider}")
        print(f"      Tokens: {event.tokens_input} in, {event.tokens_output} out")
        print(f"      Cost: ${event.cost_usd:.6f}")
        if hasattr(event, 'data') and event.data:
            print(f"      Error: {event.data.get('error', 'None')}")

    print("\n🎉 Model provider demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(demo_model_provider())