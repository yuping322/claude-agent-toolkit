#!/usr/bin/env python3
"""
完整的全流程示例 - 展示统一平台架构的完整功能

这个示例展示了从系统初始化到agent执行的完整流程，包括：
1. 系统初始化和配置加载
2. 依赖池管理
3. MCP服务启动
4. 沙箱环境执行
5. 模型提供者调用
6. 事件观测和日志记录

使用方法：
    # 设置环境变量
    export OPENROUTER_KEY="your_openrouter_api_key"

    # 运行示例
    python full_flow_example.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from claude_agent_toolkit.system.initialize import initialize_system, get_agent_runtime
from claude_agent_toolkit.system.observability import event_bus, BaseEvent
from claude_agent_toolkit.agent.dependency_pool import get_shared_dependency_manager
from claude_agent_toolkit.logging import get_logger

logger = get_logger(__name__)


async def create_example_config():
    """创建示例配置文件"""
    config_content = """
meta:
  environment: dev
  version: 1
logging:
  level: INFO
  forward_events: true
  sinks:
    - type: stdout
observability:
  enable: true
  event_buffer_size: 5000
  exporters:
    - type: stdout
sandbox:
  default_strategy: subprocess
  strategies:
    subprocess:
      max_concurrency: 8
      hard_cpu_limit_pct: 90
      memory_limit_mb: 512
model_providers:
  openrouter_primary:
    type: openrouter
    api_key: ${OPENROUTER_KEY}
    base_url: https://openrouter.ai/api/v1
    pricing:
      input_token_usd: 0.0000015
      output_token_usd: 0.000002
mcp_services:
  fs_local:
    type: filesystem
    root: /tmp
agents:
  code_analyzer:
    model_provider: openrouter_primary
    sandbox_strategy: subprocess
    tools: [fs_local]
    dependency_pools: [filesystem_pool]
    max_context_tokens: 120000
dependency_pools:
  filesystem_pool:
    type: filesystem
    paths: [/tmp, /workspace]
    max_instances: 3
"""

    # 替换环境变量
    api_key = os.environ.get("OPENROUTER_KEY", "test_key_for_demo")
    config_content = config_content.replace("${OPENROUTER_KEY}", api_key)

    # 创建临时配置文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        return f.name


async def demonstrate_full_flow():
    """演示完整流程"""
    print("🚀 Claude Agent Toolkit - 完整流程演示")
    print("=" * 60)

    # 1. 创建配置文件
    print("📝 创建配置文件...")
    config_path = await create_example_config()
    print(f"✅ 配置文件创建完成: {config_path}")

    # 2. 事件监听器
    events_received = []
    def event_listener(event):
        events_received.append(event)
        print(f"📡 事件: {event.event_type} - {event.component}")

    event_bus.subscribe("*", event_listener)

    try:
        # 3. 系统初始化
        print("\n🔧 初始化系统...")
        await initialize_system(config_path)
        print("✅ 系统初始化完成")

        # 4. 获取agent运行时配置
        print("\n🤖 获取agent运行时配置...")
        agent_config = get_agent_runtime("code_analyzer")
        print(f"✅ Agent配置获取完成: {agent_config.name}")

        # 5. 演示依赖池操作
        print("\n🏗️  演示依赖池操作...")
        dep_manager = get_shared_dependency_manager()

        # 获取文件系统依赖
        fs_instance = await dep_manager.get_dependency("code_analyzer", "filesystem_pool")
        print("✅ 文件系统依赖获取成功")

        # 模拟使用依赖
        await asyncio.sleep(0.1)

        # 释放依赖
        await dep_manager.release_dependency("code_analyzer", "filesystem_pool")
        print("✅ 依赖释放完成")

        # 6. 演示沙箱执行
        print("\n🏃 演示沙箱执行...")
        from claude_agent_toolkit.system.sandbox import SandboxManager
        from claude_agent_toolkit.system.config import SandboxStrategyConfig

        sandbox = SandboxManager({
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        })

        session = await sandbox.create_session("test_agent", "subprocess")
        print("✅ 沙箱会话创建完成")

        # 执行简单命令
        result = await sandbox.run(session, "echo 'Hello from sandbox!'")
        print(f"✅ 命令执行完成: success={result.success}, latency={result.latency_ms:.2f}ms")
        print(f"   输出: {result.stdout.strip()}")

        # 7. 演示模型提供者（如果有API密钥）
        if os.environ.get("OPENROUTER_KEY") and os.environ.get("OPENROUTER_KEY") != "test_key_for_demo":
            print("\n🧠 演示模型提供者...")
            from claude_agent_toolkit.system.model_provider import OpenRouterProvider

            provider = OpenRouterProvider(
                name="demo_provider",
                api_key=os.environ["OPENROUTER_KEY"],
                base_url="https://openrouter.ai/api/v1",
                model="gpt-4",
                pricing={"input_token_usd": 0.0000015, "output_token_usd": 0.000002}
            )

            try:
                response = await provider.generate("Say 'Hello from AI model!' in exactly 5 words.")
                print(f"✅ 模型调用成功: {response.text}")
                print(f"   Token使用: 输入{response.tokens_input}, 输出{response.tokens_output}, 费用${response.cost_usd:.6f}")
            except Exception as e:
                print(f"⚠️  模型调用失败: {e}")
        else:
            print("\n🧠 跳过模型提供者演示（需要设置OPENROUTER_KEY环境变量）")

        # 8. 统计信息
        print("\n📊 流程统计:")
        print(f"   收到事件数量: {len(events_received)}")
        event_types = {}
        for event in events_received:
            event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

        print("   事件类型分布:")
        for event_type, count in event_types.items():
            print(f"     {event_type}: {count}")

        # 依赖池统计
        dep_stats = dep_manager.get_stats()
        print(f"   依赖池状态: {dep_stats['total_pools']} 个池, {dep_stats['total_agents']} 个agent")

        print("\n🎉 完整流程演示成功完成！")
        print("\n💡 演示的功能:")
        print("   ✅ 系统配置和初始化")
        print("   ✅ 依赖池管理")
        print("   ✅ MCP服务注册")
        print("   ✅ 沙箱环境执行")
        print("   ✅ 事件观测和记录")
        print("   ✅ 模型提供者集成（可选）")

        return True

    except Exception as e:
        print(f"\n❌ 流程演示失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # 清理配置文件
        try:
            os.unlink(config_path)
        except:
            pass


async def main():
    """主函数"""
    # 检查Python版本
    if sys.version_info < (3, 12):
        print("❌ 需要Python 3.12或更高版本")
        return 1

    # 检查必需的环境变量（可选）
    if not os.environ.get("OPENROUTER_KEY"):
        print("⚠️  未设置OPENROUTER_KEY环境变量，模型提供者演示将被跳过")

    # 运行演示
    success = await demonstrate_full_flow()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)