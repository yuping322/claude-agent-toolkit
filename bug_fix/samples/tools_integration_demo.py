#!/usr/bin/env python3
"""
Tools Integration Demo

This sample demonstrates the integration and usage of filesystem and datatransfer
tools within the Claude Agent Toolkit, showcasing tool registration, execution,
and result handling.

Features demonstrated:
- Filesystem tool operations (read, write, list, search)
- Datatransfer tool operations (data serialization, transfer)
- Tool registration and lifecycle management
- Error handling in tool operations
- Performance monitoring and metrics
"""

import asyncio
import tempfile
import os
import json
from pathlib import Path
from claude_agent_toolkit.tools.filesystem import FilesystemTool
from claude_agent_toolkit.tools.datatransfer import DatatransferTool
from claude_agent_toolkit.system.observability import EventBus, ToolExecutionEvent
from claude_agent_toolkit.system.config import ToolConfig


async def demo_tools_integration():
    """Demonstrate tools integration and usage."""

    print("🔧 Claude Agent Toolkit - Tools Integration Demo")
    print("=" * 60)

    # Setup event monitoring
    event_bus = EventBus()
    tool_events = []

    async def tool_event_handler(event: ToolExecutionEvent):
        tool_events.append(event)
        print(f"📊 Tool Event: {event.tool_name} - {event.operation} - {event.status}")

    event_bus.subscribe("tool_execution", tool_event_handler)

    # Demo 1: Filesystem tool operations
    print("\n📁 Demo 1: Filesystem tool operations")

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Initialize filesystem tool
        fs_config = ToolConfig(
            name="filesystem_tool",
            type="filesystem",
            config={"root_path": str(temp_path)}
        )
        fs_tool = FilesystemTool(fs_config)

        # Create test files and directories
        test_dir = temp_path / "test_project"
        test_dir.mkdir()

        (test_dir / "main.py").write_text("""
def hello_world():
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
""")

        (test_dir / "config.json").write_text("""
{
    "app_name": "Test App",
    "version": "1.0.0",
    "settings": {
        "debug": true,
        "port": 8080
    }
}
""")

        # Test filesystem operations
        operations = [
            ("list_directory", {"path": str(test_dir)}),
            ("read_file", {"path": str(test_dir / "main.py")}),
            ("read_file", {"path": str(test_dir / "config.json")}),
            ("search_files", {"pattern": "*.py", "path": str(test_dir)}),
            ("get_file_info", {"path": str(test_dir / "main.py")}),
        ]

        for op_name, params in operations:
            print(f"\n🔍 Testing: {op_name}")
            try:
                result = await fs_tool.execute(op_name, params)
                if result.success:
                    print(f"✅ {op_name} succeeded")
                    if "content" in result.data:
                        content_preview = str(result.data["content"])[:100]
                        print(f"   Content preview: {content_preview}...")
                    elif "files" in result.data:
                        print(f"   Found {len(result.data['files'])} files")
                    elif "size" in result.data:
                        print(f"   File size: {result.data['size']} bytes")
                else:
                    print(f"❌ {op_name} failed: {result.error}")
            except Exception as e:
                print(f"❌ {op_name} error: {type(e).__name__}: {e}")

    # Demo 2: Datatransfer tool operations
    print("\n📤 Demo 2: Datatransfer tool operations")

    # Initialize datatransfer tool
    dt_config = ToolConfig(
        name="datatransfer_tool",
        type="datatransfer",
        config={"max_transfer_size": 1024 * 1024}  # 1MB limit
    )
    dt_tool = DatatransferTool(dt_config)

    # Test data structures
    test_data = {
        "user_profile": {
            "id": 12345,
            "name": "John Doe",
            "email": "john.doe@example.com",
            "preferences": {
                "theme": "dark",
                "notifications": True
            }
        },
        "project_metrics": {
            "total_files": 42,
            "lines_of_code": 15420,
            "test_coverage": 87.5,
            "performance_score": 92.3
        },
        "system_status": {
            "cpu_usage": 45.2,
            "memory_usage": 67.8,
            "disk_usage": 23.1,
            "network_io": {
                "bytes_sent": 1024000,
                "bytes_received": 2048000
            }
        }
    }

    # Test datatransfer operations
    transfer_operations = [
        ("serialize_data", {"data": test_data["user_profile"], "format": "json"}),
        ("serialize_data", {"data": test_data["project_metrics"], "format": "yaml"}),
        ("transfer_data", {
            "source": test_data["system_status"],
            "destination": "memory://system_metrics",
            "format": "json"
        }),
        ("validate_data", {"data": test_data["user_profile"], "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "email": {"type": "string", "format": "email"}
            },
            "required": ["id", "name", "email"]
        }}),
    ]

    for op_name, params in transfer_operations:
        print(f"\n🔍 Testing: {op_name}")
        try:
            result = await dt_tool.execute(op_name, params)
            if result.success:
                print(f"✅ {op_name} succeeded")
                if "serialized_data" in result.data:
                    data_preview = str(result.data["serialized_data"])[:100]
                    print(f"   Serialized preview: {data_preview}...")
                elif "transfer_id" in result.data:
                    print(f"   Transfer ID: {result.data['transfer_id']}")
                elif "is_valid" in result.data:
                    print(f"   Data valid: {result.data['is_valid']}")
            else:
                print(f"❌ {op_name} failed: {result.error}")
        except Exception as e:
            print(f"❌ {op_name} error: {type(e).__name__}: {e}")

    # Demo 3: Tool lifecycle management
    print("\n🔄 Demo 3: Tool lifecycle management")

    tools = [fs_tool, dt_tool]

    for tool in tools:
        print(f"\n🔧 Managing tool: {tool.name}")

        # Test tool status
        try:
            status = await tool.get_status()
            print(f"   Status: {status}")
        except Exception as e:
            print(f"   Status error: {type(e).__name__}")

        # Test tool cleanup
        try:
            await tool.cleanup()
            print("   Cleanup completed")
        except Exception as e:
            print(f"   Cleanup error: {type(e).__name__}")

    # Demo 4: Error handling in tools
    print("\n🚨 Demo 4: Error handling in tools")

    error_scenarios = [
        ("Invalid path", fs_tool, "read_file", {"path": "/nonexistent/path"}),
        ("Permission denied", fs_tool, "list_directory", {"path": "/root"}),
        ("Invalid data format", dt_tool, "serialize_data", {"data": set([1, 2, 3]), "format": "json"}),
        ("Oversized data", dt_tool, "serialize_data", {
            "data": {"large_field": "x" * (1024 * 1024 * 2)},  # 2MB
            "format": "json"
        }),
    ]

    for desc, tool, op_name, params in error_scenarios:
        print(f"\n🔍 Testing: {desc}")
        try:
            result = await tool.execute(op_name, params)
            if not result.success:
                print(f"✅ Correctly handled error: {result.error}")
            else:
                print("❌ Expected error but operation succeeded")
        except Exception as e:
            print(f"✅ Caught exception: {type(e).__name__}")

    # Demo 5: Performance monitoring
    print("\n📊 Demo 5: Performance monitoring")

    print(f"📈 Total tool events captured: {len(tool_events)}")

    # Analyze events
    successful_ops = sum(1 for e in tool_events if e.status == "success")
    failed_ops = sum(1 for e in tool_events if e.status == "error")

    print(f"   Successful operations: {successful_ops}")
    print(f"   Failed operations: {failed_ops}")

    # Group by tool
    tool_stats = {}
    for event in tool_events:
        if event.tool_name not in tool_stats:
            tool_stats[event.tool_name] = {"success": 0, "error": 0}
        tool_stats[event.tool_name][event.status] += 1

    print("   Tool statistics:")
    for tool_name, stats in tool_stats.items():
        total = stats["success"] + stats["error"]
        success_rate = (stats["success"] / total * 100) if total > 0 else 0
        print(f"     {tool_name}: {stats['success']}/{total} ({success_rate:.1f}% success)")

    # Demo 6: Tool configuration validation
    print("\n⚙️  Demo 6: Tool configuration validation")

    invalid_configs = [
        ("Missing name", {"type": "filesystem", "config": {}}),
        ("Invalid type", {"name": "test", "type": "invalid_type", "config": {}}),
        ("Missing config", {"name": "test", "type": "filesystem"}),
        ("Invalid config values", {
            "name": "test",
            "type": "filesystem",
            "config": {"root_path": 123}  # Should be string
        }),
    ]

    for desc, config_dict in invalid_configs:
        print(f"\n🔍 Testing: {desc}")
        try:
            config = ToolConfig(**config_dict)
            tool = FilesystemTool(config)  # This might fail during init
            print("❌ Expected validation error but config succeeded")
        except Exception as e:
            print(f"✅ Correctly caught validation error: {type(e).__name__}: {e}")

    print("\n🎉 Tools integration demo completed successfully!")
    print("🔧 Demonstrated comprehensive tool functionality and error handling")


if __name__ == "__main__":
    asyncio.run(demo_tools_integration())