# Claude Agent Toolkit - Demonstration Samples

This directory contains comprehensive demonstration samples showcasing all major functionalities of the Claude Agent Toolkit. These samples serve as both documentation and validation of system robustness.

## Available Samples

### Core System Components

#### `system_initialization_demo.py`
Demonstrates complete system initialization workflow including:
- Configuration loading and validation
- Component setup and dependency injection
- Event monitoring and system health checks
- Error handling during initialization

**Usage:**
```bash
python system_initialization_demo.py
```

#### `model_provider_demo.py`
Showcases model provider usage and integration:
- OpenRouter provider initialization
- API calls with error handling
- Usage tracking and metrics
- Provider failover scenarios

**Usage:**
```bash
python model_provider_demo.py
```

#### `sandbox_execution_demo.py`
Demonstrates sandbox execution capabilities:
- Session management and lifecycle
- Command execution with resource limits
- Resource monitoring and cleanup
- Error handling in sandboxed environments

**Usage:**
```bash
python sandbox_execution_demo.py
```

#### `dependency_pool_demo.py`
Shows dependency pool management:
- FileSystem pool operations
- Concurrent access control
- Resource cleanup and monitoring
- Pool statistics and analytics

**Usage:**
```bash
python dependency_pool_demo.py
```

#### `mcp_services_demo.py`
Demonstrates MCP service registry and management:
- Service registration and lifecycle
- Tool listing and metadata
- Service start/stop operations
- Error handling and recovery

**Usage:**
```bash
python mcp_services_demo.py
```

#### `observability_demo.py`
Showcases comprehensive system monitoring:
- Event bus usage and subscription
- Different event types and filtering
- Performance analysis and metrics
- Error event detection and alerting

**Usage:**
```bash
python observability_demo.py
```

### Advanced Features

#### `error_handling_demo.py`
Comprehensive error handling demonstration:
- Configuration validation errors
- Model provider failures and retries
- Sandbox execution errors
- Dependency pool timeouts
- MCP service failures
- Recovery strategies and fallbacks

**Usage:**
```bash
python error_handling_demo.py
```

#### `tools_integration_demo.py`
Tools integration and usage patterns:
- Filesystem tool operations (read, write, list, search)
- Datatransfer tool operations (serialization, transfer)
- Tool lifecycle management
- Performance monitoring and metrics

**Usage:**
```bash
python tools_integration_demo.py
```

#### `end_to_end_workflow_demo.py`
Create end-to-end workflow demo from config to execution and cleanup.

**Usage:**
```bash
python end_to_end_workflow_demo.py
```

#### `complete_workflow_demo.py`
**COMPLETE END-TO-END WORKFLOW** - Single script that handles everything from repository cloning to code improvement and push. This is the most comprehensive example showing a real-world development workflow.

**Features:**
- Git repository cloning
- Branch creation and management
- Claude Agent system initialization
- Code analysis and improvement
- Automated commit and push
- Complete error handling and cleanup

**Usage:**
```bash
python complete_workflow_demo.py
```

**Configuration:** Edit the script variables at the bottom:
```python
REPO_URL = "https://github.com/your-org/your-repo.git"  # Your target repository
TASK_DESCRIPTION = "Your task description"
BRANCH_NAME = "feature-branch-name"
```

**Real Usage:** Uncomment the workflow execution line in main() and configure:
- Valid Git repository URL with access
- Proper Git authentication (SSH keys or tokens)
- Claude API keys for model providers

## Prerequisites

Before running the samples, ensure you have:

1. **Python Environment**: Python 3.8+ with required dependencies
2. **Configuration**: Valid YAML configuration files for system components
3. **API Keys**: Model provider API keys (for model provider demos)
4. **Permissions**: Appropriate file system permissions for workspace operations

## Configuration

Most samples use temporary configurations for demonstration. For production use, create proper configuration files following the system schema.

## Running Samples

All samples can be run independently:

```bash
# Run all samples
for sample in *.py; do
    echo "Running $sample..."
    python "$sample"
    echo "Completed $sample"
    echo
done
```

## Sample Output

Each sample provides detailed console output showing:
- Operation progress and status
- Success/failure indicators
- Performance metrics
- Error handling demonstrations
- Event monitoring data

## Learning Path

For best understanding, run samples in this order:

1. `system_initialization_demo.py` - Understand system setup
2. `model_provider_demo.py` - Learn provider integration
3. `sandbox_execution_demo.py` - Explore execution environments
4. `dependency_pool_demo.py` - Master resource management
5. `mcp_services_demo.py` - Discover service architecture
6. `observability_demo.py` - Monitor system behavior
7. `error_handling_demo.py` - Handle edge cases
8. `tools_integration_demo.py` - Integrate custom tools
9. `end_to_end_workflow_demo.py` - See complete workflows

## Validation

These samples serve as comprehensive validation that:
- All system components work correctly
- Error handling is robust
- Performance meets requirements
- Integration points function properly
- Observability provides adequate monitoring

## Contributing

When adding new samples:
1. Follow the naming convention: `{feature}_demo.py`
2. Include comprehensive docstrings
3. Demonstrate both success and error scenarios
4. Add usage examples to this README
5. Ensure samples are self-contained

## Troubleshooting

- **Import Errors**: Ensure all dependencies are installed
- **Configuration Errors**: Check YAML syntax and required fields
- **Permission Errors**: Run with appropriate file system access
- **API Errors**: Verify API keys and network connectivity

For issues specific to samples, check the console output for detailed error messages and stack traces.