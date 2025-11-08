import asyncio
import pytest
import tempfile
import os
from unittest.mock import patch, AsyncMock
from pathlib import Path

from claude_agent_toolkit.system.model_provider import OpenRouterProvider, ModelProvider
from claude_agent_toolkit.system.observability import event_bus, ModelInvocationEvent


class TestModelProviderFailures:
    """测试模型提供者各种失败情况"""

    @pytest.mark.asyncio
    async def test_api_key_missing(self):
        """测试API密钥缺失的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="",  # 空密钥
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        with pytest.raises(Exception):  # 应该抛出异常
            await provider.generate("test prompt")

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        """测试无效API密钥的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="invalid_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        with pytest.raises(Exception):  # 应该抛出401或403错误
            await provider.generate("test prompt")

    @pytest.mark.asyncio
    async def test_network_timeout(self):
        """测试网络超时的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock httpx client to simulate timeout
        with patch.object(provider._client, 'post', side_effect=asyncio.TimeoutError()):
            with pytest.raises(asyncio.TimeoutError):
                await provider.generate("test prompt")

    @pytest.mark.asyncio
    async def test_server_error_500(self):
        """测试服务器错误的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock httpx response with 500 error
        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = Exception("500 Internal Server Error")
        mock_response.status_code = 500

        with patch.object(provider._client, 'post', return_value=mock_response):
            with pytest.raises(Exception):
                await provider.generate("test prompt")

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        """测试速率限制的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock httpx response with 429 error
        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = Exception("429 Too Many Requests")
        mock_response.status_code = 429

        with patch.object(provider._client, 'post', return_value=mock_response):
            with pytest.raises(Exception):
                await provider.generate("test prompt")

    @pytest.mark.asyncio
    async def test_invalid_model_name(self):
        """测试无效模型名称的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="invalid-model-name",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock httpx response with 400 error for invalid model
        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = Exception("400 Bad Request: Invalid model")
        mock_response.status_code = 400

        with patch.object(provider._client, 'post', return_value=mock_response):
            with pytest.raises(Exception):
                await provider.generate("test prompt")

    @pytest.mark.asyncio
    async def test_empty_prompt(self):
        """测试空提示的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock successful response
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "Empty response"}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 2}
        })
        mock_response.status_code = 200

        with patch.object(provider._client, 'post', return_value=mock_response):
            result = await provider.generate("")  # 空提示
            assert result.text == "Empty response"
            assert result.tokens_input == 0

    @pytest.mark.asyncio
    async def test_very_long_prompt(self):
        """测试超长提示的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # 创建一个非常长的提示
        long_prompt = "test " * 10000  # 约50,000字符

        # Mock response indicating token limit exceeded
        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = Exception("400 Bad Request: Token limit exceeded")
        mock_response.status_code = 400

        with patch.object(provider._client, 'post', return_value=mock_response):
            with pytest.raises(Exception):
                await provider.generate(long_prompt)

    @pytest.mark.asyncio
    async def test_malformed_response(self):
        """测试API返回格式错误的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock malformed response
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json = AsyncMock(return_value={
            "invalid_format": "no choices field"
        })
        mock_response.status_code = 200

        with patch.object(provider._client, 'post', return_value=mock_response):
            result = await provider.generate("test prompt")
            # Should handle gracefully with fallback
            assert result.text == ""  # Empty fallback
            assert result.tokens_input == 0
            assert result.tokens_output == 0

    @pytest.mark.asyncio
    async def test_connection_refused(self):
        """测试连接被拒绝的情况"""
        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock connection refused error
        with patch.object(provider._client, 'post', side_effect=Exception("Connection refused")):
            with pytest.raises(Exception):
                await provider.generate("test prompt")

    @pytest.mark.asyncio
    async def test_event_emission_on_failure(self):
        """测试失败时的事件发射"""
        events = []
        def event_handler(event):
            events.append(event)

        event_bus.subscribe("model.invocation", event_handler)

        provider = OpenRouterProvider(
            name="test_provider",
            api_key="test_key",
            base_url="https://openrouter.ai/api/v1",
            model="gpt-4",
            pricing={"input_token_usd": 0.000001, "output_token_usd": 0.000002}
        )

        # Mock failure
        with patch.object(provider._client, 'post', side_effect=Exception("Network error")):
            with pytest.raises(Exception):
                await provider.generate("test prompt")

        # Check that failure event was emitted
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ModelInvocationEvent)
        assert event.event_type == "model.invocation"
        assert event.provider == "test_provider"
        assert event.tokens_input == 0
        assert event.tokens_output == 0
        assert event.cost_usd == 0.0
        assert "error" in event.data