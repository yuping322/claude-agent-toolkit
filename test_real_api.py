#!/usr/bin/env python3
"""
测试真实的OpenRouter API调用
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from claude_agent_toolkit.system.model_provider import OpenRouterProvider
from claude_agent_toolkit.system.observability import event_bus


async def test_real_openrouter_api():
    """测试真实的OpenRouter API调用"""
    print("🧪 测试真实的OpenRouter API调用")
    print("=" * 50)

    # 检查环境变量
    api_key = os.environ.get("OPENROUTER_KEY")
    if not api_key:
        print("❌ OPENROUTER_KEY环境变量未设置")
        return False

    print(f"✅ API Key: {api_key[:20]}...")

    # 创建事件监听器
    events_received = []
    def event_handler(event):
        events_received.append(event)
        print(f"📡 事件: {event.event_type}")

    event_bus.subscribe("model.invocation", event_handler)

    # 创建OpenRouter提供者
    provider = OpenRouterProvider(
        name="test_provider",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        model="gpt-4o-mini",  # 使用一个便宜的模型进行测试
        pricing={"input_token_usd": 0.0000015, "output_token_usd": 0.000002}
    )

    try:
        print("\n🤖 发送测试请求...")
        prompt = "Say 'Hello from real OpenRouter API!' in exactly 3 words."

        response = await provider.generate(prompt)

        print("✅ API调用成功！")
        print(f"📝 响应: {response.text}")
        print(f"📊 Token使用: 输入{response.tokens_input}, 输出{response.tokens_output}")
        print(f"💰 费用: ${response.cost_usd:.6f}")
        print(f"⏱️  延迟: {response.latency_ms:.2f}ms")

        # 检查事件
        model_events = [e for e in events_received if e.event_type == "model.invocation"]
        if model_events:
            print(f"✅ 收到 {len(model_events)} 个模型调用事件")
        else:
            print("⚠️  未收到模型调用事件")

        return True

    except Exception as e:
        print(f"❌ API调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    success = await test_real_openrouter_api()

    if success:
        print("\n🎉 OpenRouter API测试成功！系统可以正常使用真实API。")
    else:
        print("\n💥 OpenRouter API测试失败。请检查API密钥和网络连接。")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)