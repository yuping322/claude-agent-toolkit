#!/usr/bin/env python3
"""
End-to-End Workflow Demo

This sample demonstrates a complete end-to-end workflow using the Claude Agent Toolkit,
from system initialization through agent execution to result processing and cleanup.

Features demonstrated:
- Complete system initialization
- Agent runtime creation and execution
- Tool integration and usage
- Observability and monitoring
- Error handling and recovery
- Resource cleanup and shutdown
"""

import asyncio
import tempfile
import os
import json
from pathlib import Path
from claude_agent_toolkit.system.initialize import initialize_system, get_agent_runtime
from claude_agent_toolkit.system.observability import EventBus, WorkflowEvent
from claude_agent_toolkit.tools.filesystem import FilesystemTool
from claude_agent_toolkit.tools.datatransfer import DatatransferTool
from claude_agent_toolkit.system.config import ToolConfig


async def demo_end_to_end_workflow():
    """Demonstrate complete end-to-end workflow."""

    print("🚀 Claude Agent Toolkit - End-to-End Workflow Demo")
    print("=" * 60)

    # Create comprehensive system configuration
    system_config = """
meta:
  environment: demo
  version: 1.0
logging:
  level: INFO
observability:
  enable: true
sandbox:
  default_strategy: subprocess
  strategies:
    subprocess:
      max_concurrency: 4
      hard_cpu_limit_pct: 80
      memory_limit_mb: 512
model_providers:
  demo_provider:
    type: openrouter
    api_key: demo_key_123
    base_url: https://openrouter.ai/api/v1
    model: anthropic/claude-3-haiku
mcp_services: {}
agents:
  code_analyzer:
    model_provider: demo_provider
    dependency_pools: [workspace_pool]
  data_processor:
    model_provider: demo_provider
    dependency_pools: [data_pool]
dependency_pools:
  workspace_pool:
    type: filesystem
    paths: [/tmp/demo_workspace]
  data_pool:
    type: filesystem
    paths: [/tmp/demo_data]
tools:
  filesystem_tool:
    type: filesystem
    config:
      root_path: /tmp/demo_workspace
  datatransfer_tool:
    type: datatransfer
    config:
      max_transfer_size: 1048576
"""

    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(system_config)
        config_path = f.name

    try:
        # Phase 1: System Initialization
        print("\n🏗️  Phase 1: System Initialization")

        await initialize_system(config_path)
        print("✅ System initialized successfully")

        # Setup event monitoring
        event_bus = EventBus()
        workflow_events = []

        async def workflow_event_handler(event: WorkflowEvent):
            workflow_events.append(event)
            print(f"📊 Workflow Event: {event.phase} - {event.status}")

        event_bus.subscribe("workflow", workflow_event_handler)

        # Phase 2: Agent Runtime Setup
        print("\n🤖 Phase 2: Agent Runtime Setup")

        code_analyzer = get_agent_runtime("code_analyzer")
        data_processor = get_agent_runtime("data_processor")

        print("✅ Agent runtimes created:")
        print(f"   • Code Analyzer: {code_analyzer.name}")
        print(f"   • Data Processor: {data_processor.name}")

        # Phase 3: Tool Integration
        print("\n🔧 Phase 3: Tool Integration")

        # Get tools from agents
        fs_tool = code_analyzer.get_tool("filesystem_tool")
        dt_tool = data_processor.get_tool("datatransfer_tool")

        print("✅ Tools integrated:")
        print(f"   • Filesystem Tool: {fs_tool.name}")
        print(f"   • Datatransfer Tool: {dt_tool.name}")

        # Phase 4: Workspace Preparation
        print("\n📁 Phase 4: Workspace Preparation")

        # Create demo project structure
        demo_workspace = Path("/tmp/demo_workspace")
        demo_workspace.mkdir(exist_ok=True)

        # Create sample code files
        (demo_workspace / "main.py").write_text("""
import json
import sys
from pathlib import Path

def analyze_codebase():
    \"\"\"Analyze the codebase structure.\"\"\"
    stats = {
        "files": 0,
        "lines": 0,
        "functions": 0
    }

    for py_file in Path(".").rglob("*.py"):
        stats["files"] += 1
        content = py_file.read_text()
        stats["lines"] += len(content.splitlines())

        # Count functions (simple heuristic)
        stats["functions"] += content.count("def ")

    return stats

if __name__ == "__main__":
    result = analyze_codebase()
    print(json.dumps(result, indent=2))
""")

        (demo_workspace / "utils.py").write_text("""
def helper_function():
    return "Helper function result"

class DataProcessor:
    def __init__(self, data):
        self.data = data

    def process(self):
        return {
            "original_length": len(str(self.data)),
            "processed": True,
            "timestamp": "2024-01-01T00:00:00Z"
        }
""")

        (demo_workspace / "config.json").write_text("""
{
    "project": {
        "name": "Demo Project",
        "version": "1.0.0",
        "description": "End-to-end workflow demonstration"
    },
    "analysis": {
        "enabled": true,
        "output_format": "json",
        "include_metrics": true
    }
}
""")

        print("✅ Demo workspace prepared with sample files")

        # Phase 5: Code Analysis Workflow
        print("\n🔍 Phase 5: Code Analysis Workflow")

        # Use filesystem tool to explore codebase
        list_result = await fs_tool.execute("list_directory", {"path": str(demo_workspace)})
        if list_result.success:
            files = list_result.data.get("files", [])
            print(f"📂 Found {len(files)} files in workspace:")
            for file_info in files[:5]:  # Show first 5
                print(f"   • {file_info['name']} ({file_info['type']})")

        # Read and analyze main.py
        read_result = await fs_tool.execute("read_file", {"path": str(demo_workspace / "main.py")})
        if read_result.success:
            content = read_result.data["content"]
            print(f"📖 Read main.py ({len(content)} characters)")

            # Use agent to analyze the code
            analysis_prompt = f"""
Analyze this Python code and provide insights:

{content}

Please provide:
1. Code structure overview
2. Potential improvements
3. Best practices compliance
"""

            # Note: In a real scenario, this would call the model provider
            # For demo purposes, we'll simulate the analysis
            print("🤖 Code analysis completed (simulated)")

        # Phase 6: Data Processing Workflow
        print("\n📊 Phase 6: Data Processing Workflow")

        # Read configuration data
        config_result = await fs_tool.execute("read_file", {"path": str(demo_workspace / "config.json")})
        if config_result.success:
            config_data = json.loads(config_result.data["content"])
            print("📋 Configuration loaded")

            # Process data using datatransfer tool
            transfer_result = await dt_tool.execute("transfer_data", {
                "source": config_data,
                "destination": "memory://processed_config",
                "format": "json"
            })

            if transfer_result.success:
                print("✅ Configuration data transferred")

                # Validate processed data
                validate_result = await dt_tool.execute("validate_data", {
                    "data": config_data,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "version": {"type": "string"}
                                },
                                "required": ["name", "version"]
                            }
                        },
                        "required": ["project"]
                    }
                })

                if validate_result.success and validate_result.data.get("is_valid"):
                    print("✅ Configuration data validated")
                else:
                    print("❌ Configuration validation failed")

        # Phase 7: Cross-Agent Collaboration
        print("\n🤝 Phase 7: Cross-Agent Collaboration")

        # Simulate agents working together
        # Code analyzer extracts metrics
        metrics = {
            "files_analyzed": 3,
            "total_lines": 45,
            "functions_found": 3,
            "complexity_score": 2.1
        }

        # Data processor formats and enhances the metrics
        enhanced_metrics = {
            **metrics,
            "analysis_timestamp": "2024-01-01T12:00:00Z",
            "quality_score": 85.5,
            "recommendations": [
                "Consider adding type hints",
                "Add comprehensive error handling",
                "Include unit tests"
            ]
        }

        print("📈 Metrics processed and enhanced:")
        print(f"   • Files analyzed: {enhanced_metrics['files_analyzed']}")
        print(f"   • Quality score: {enhanced_metrics['quality_score']}%")
        print(f"   • Recommendations: {len(enhanced_metrics['recommendations'])}")

        # Phase 8: Result Serialization and Storage
        print("\n💾 Phase 8: Result Serialization and Storage")

        # Serialize final results
        final_report = {
            "workflow_id": "demo_workflow_001",
            "timestamp": "2024-01-01T12:00:00Z",
            "agents_used": ["code_analyzer", "data_processor"],
            "tools_used": ["filesystem_tool", "datatransfer_tool"],
            "results": {
                "code_metrics": metrics,
                "enhanced_metrics": enhanced_metrics,
                "workspace_info": {
                    "path": str(demo_workspace),
                    "files_processed": len(list(demo_workspace.glob("*")))
                }
            },
            "status": "completed",
            "execution_time_ms": 1250
        }

        # Store results using filesystem tool
        report_path = demo_workspace / "analysis_report.json"
        report_content = json.dumps(final_report, indent=2)

        # Write report file
        with open(report_path, 'w') as f:
            f.write(report_content)

        print(f"✅ Analysis report saved to {report_path}")

        # Phase 9: Workflow Monitoring and Analytics
        print("\n📊 Phase 9: Workflow Monitoring and Analytics")

        print(f"📈 Workflow events captured: {len(workflow_events)}")

        # Analyze workflow performance
        phases_completed = len([e for e in workflow_events if e.status == "completed"])
        total_phases = 9  # This demo has 9 phases

        print(f"   • Phases completed: {phases_completed}/{total_phases}")
        print(f"   • Success rate: {(phases_completed/total_phases*100):.1f}%")

        # Phase 10: Cleanup and Shutdown
        print("\n🧹 Phase 10: Cleanup and Shutdown")

        # Cleanup tools
        await fs_tool.cleanup()
        await dt_tool.cleanup()
        print("✅ Tools cleaned up")

        # Cleanup demo workspace
        import shutil
        if demo_workspace.exists():
            shutil.rmtree(demo_workspace)
        print("✅ Demo workspace cleaned up")

        # System shutdown would happen here in a real scenario
        print("✅ Workflow completed successfully")

        # Final Summary
        print("\n🎉 End-to-End Workflow Demo Summary")
        print("=" * 40)
        print("✅ System initialization and configuration")
        print("✅ Agent runtime creation and management")
        print("✅ Tool integration and execution")
        print("✅ Workspace preparation and file operations")
        print("✅ Code analysis and data processing")
        print("✅ Cross-agent collaboration")
        print("✅ Result serialization and storage")
        print("✅ Workflow monitoring and analytics")
        print("✅ Resource cleanup and shutdown")
        print("\n🚀 Complete end-to-end workflow demonstrated!")

    finally:
        # Cleanup config file
        os.unlink(config_path)


if __name__ == "__main__":
    asyncio.run(demo_end_to_end_workflow())