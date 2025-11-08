# Claude Agent Toolkit - 配置指南

## 概述

Claude Agent Toolkit 是一个统一的平台架构，用于构建和管理Claude Code agents。本文档介绍如何配置和运行完整的系统。

## 系统架构

该平台包含以下核心组件：

- **统一配置系统**: 基于Pydantic的全局配置，支持环境变量插值
- **依赖池管理**: 共享外部依赖（如文件系统、Claude Code连接等）
- **模型提供者抽象**: 支持多个AI模型提供商
- **MCP服务管理**: Model Context Protocol服务生命周期管理
- **沙箱环境**: 安全的代码执行环境
- **事件观测系统**: 结构化日志和事件转发

## 快速开始

### 1. 环境准备

确保你有Python 3.12+和以下依赖：

```bash
pip install claude-agent-toolkit
```

### 2. 创建配置文件

创建一个YAML配置文件（例如 `config.yaml`）：

```yaml
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
```

### 3. 设置环境变量

```bash
export OPENROUTER_KEY="your_openrouter_api_key_here"
```

### 4. 运行完整流程示例

```bash
python full_flow_example.py
```

这个示例会演示：
- 系统初始化
- 依赖池操作
- 沙箱命令执行
- 事件观测

## 配置详解

### 全局配置

#### Meta配置
```yaml
meta:
  environment: dev  # 环境标识
  version: 1        # 配置版本
```

#### 日志配置
```yaml
logging:
  level: INFO          # 日志级别: DEBUG, INFO, WARNING, ERROR
  forward_events: true # 是否将日志转发为事件
  sinks:
    - type: stdout     # 输出到控制台
    - type: file       # 输出到文件
      path: /var/log/agent.log
```

#### 观测配置
```yaml
observability:
  enable: true
  event_buffer_size: 5000
  exporters:
    - type: stdout
    - type: file
      path: /var/log/events.jsonl
```

### 沙箱配置

```yaml
sandbox:
  default_strategy: subprocess
  strategies:
    subprocess:
      max_concurrency: 8        # 最大并发数
      hard_cpu_limit_pct: 90    # CPU使用率限制
      memory_limit_mb: 512      # 内存限制
    docker:
      max_concurrency: 4
      hard_cpu_limit_pct: 70
      memory_limit_mb: 2048
      network_policy: deny-all  # 网络策略
```

### 模型提供者配置

#### OpenRouter提供者
```yaml
model_providers:
  openrouter_primary:
    type: openrouter
    api_key: ${OPENROUTER_KEY}           # 环境变量插值
    base_url: https://openrouter.ai/api/v1
    pricing:
      input_token_usd: 0.0000015         # 输入token价格
      output_token_usd: 0.000002         # 输出token价格
```

#### 其他提供者
系统支持扩展其他提供者类型。

### MCP服务配置

```yaml
mcp_services:
  fs_local:
    type: filesystem
    root: /tmp
  git_ops:
    type: git
    extras:
      default_branch: main
```

### Agent配置

```yaml
agents:
  code_analyzer:
    model_provider: openrouter_primary    # 引用的提供者
    sandbox_strategy: subprocess          # 沙箱策略
    tools: [fs_local]                     # MCP工具列表
    dependency_pools: [filesystem_pool]   # 依赖池列表
    max_context_tokens: 120000            # 最大上下文长度
```

### 依赖池配置

```yaml
dependency_pools:
  filesystem_pool:
    type: filesystem
    paths: [/tmp, /workspace]  # 允许访问的路径
    max_instances: 3           # 最大实例数
  claude_code_pool:
    type: claude_code
    oauth_token: ${CLAUDE_TOKEN}
    model: sonnet
    max_instances: 2
```

## 环境变量

系统支持环境变量插值，使用 `${VAR_NAME}` 语法：

- `OPENROUTER_KEY`: OpenRouter API密钥
- `CLAUDE_TOKEN`: Claude Code OAuth令牌
- `ANTHROPIC_KEY`: Anthropic API密钥（如果使用）

## 编程接口

### 系统初始化

```python
from claude_agent_toolkit.system.initialize import initialize_system, get_agent_runtime

# 初始化系统
await initialize_system("config.yaml")

# 获取agent运行时配置
agent_config = get_agent_runtime("code_analyzer")
```

### 依赖池使用

```python
from claude_agent_toolkit.agent.dependency_pool import get_shared_dependency_manager

manager = get_shared_dependency_manager()

# 获取依赖
fs_tool = await manager.get_dependency("agent_id", "filesystem_pool")

# 使用依赖
result = fs_tool.list_directory("/tmp")

# 释放依赖
await manager.release_dependency("agent_id", "filesystem_pool")
```

### 沙箱执行

```python
from claude_agent_toolkit.system.sandbox import SandboxManager

sandbox = SandboxManager(strategies_config)
session = await sandbox.create_session("agent_id", "subprocess")

result = await sandbox.run(session, "echo 'hello'")
print(f"Success: {result.success}, Output: {result.stdout}")
```

### 事件监听

```python
from claude_agent_toolkit.system.observability import event_bus

def handle_event(event):
    print(f"Event: {event.event_type} from {event.component}")

event_bus.subscribe("*", handle_event)
```

## 故障排除

### 常见问题

1. **MCP服务器启动失败**
   - 检查端口是否被占用
   - 确保FastMCP依赖正确安装

2. **依赖池获取失败**
   - 检查配置文件中的路径权限
   - 验证依赖池类型配置

3. **沙箱执行失败**
   - 检查psutil是否安装（用于资源监控）
   - 验证命令语法

4. **模型提供者连接失败**
   - 检查API密钥环境变量
   - 验证网络连接

### 调试模式

启用详细日志：

```yaml
logging:
  level: DEBUG
```

查看事件流：

```python
event_bus.subscribe("*", lambda e: print(f"DEBUG: {e}"))
```

## 扩展开发

### 添加新的模型提供者

1. 继承 `ModelProvider` 基类
2. 实现 `generate` 方法
3. 在配置中添加新的provider类型

### 添加新的依赖池类型

1. 继承 `DependencyPool` 基类
2. 实现 `create_instance`、`destroy_instance`、`validate_instance` 方法
3. 在初始化代码中添加池类型处理

### 添加新的MCP服务

1. 在配置中定义服务类型
2. 实现服务启动/停止逻辑
3. 添加到 `McpServiceRegistry`

## 完整示例

参考 `full_flow_example.py` 获取完整的系统使用示例。