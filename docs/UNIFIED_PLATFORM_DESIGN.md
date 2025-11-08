# 统一Agent平台标准服务设计

## 目标
提供一个可扩展、可观测、资源受控的多 Agent 运行平台，通过统一的配置与服务层，标准化以下能力：
1. 全局统一配置 -> 分发到具体 Agent 的局部配置
2. 模型提供者抽象（支持多后端/OpenRouter式统一接入 + 用量统计）
3. MCP 服务层（集中启动/注册工具服务，合并工具列表）
4. 沙箱执行环境（subprocess / docker / future: firecracker）
5. 标准日志事件与中间状态采集（Observability 事件总线）
6. 依赖池与外部资源（已实现）与事件集成

---
## 架构总览
```
+-------------------------------------------------------------+
|                   Unified Agent Platform                    |
|                                                             |
|  +------------------+   +------------------+                |
|  |  Global Config    |-->| Config Resolver  |--> AgentConfig |
|  +------------------+   +------------------+                |
|             |                         |                     |
|             v                         v                     |
|  +------------------+   +------------------+                |
|  | Model Providers   |<->| Usage Tracker    |                |
|  +------------------+   +------------------+                |
|             |                         |                     |
|             v                         v                     |
|  +------------------+   +------------------+                |
|  | MCP Registry      |   | Sandbox Manager  |                |
|  +------------------+   +------------------+                |
|             \__________________________/                    |
|                          |                                   |
|                    +-----------+                            |
|                    | Observability|<- Events: model, tool, dep|  |
|                    +-----------+                            |
+-------------------------------------------------------------+
```

---
## 1. 统一配置 Global Config
### 设计原则
- 单一入口 `global_config.yaml`
- Pydantic 校验与默认值填充
- 分层：`meta`、`logging`、`observability`、`sandbox`、`model_providers`、`mcp_services`、`agents`、`dependency_pools`
- 支持环境变量 `${VAR}` 与内嵌引用（未来可扩展）

### 示例结构
```yaml
meta:
  environment: prod
  version: 1
logging:
  level: INFO
  sinks:
    - type: stdout
    - type: file
      path: logs/agents.log
observability:
  enable: true
  event_buffer_size: 10000
  exporters:
    - type: memory
    - type: stdout
sandbox:
  default_strategy: subprocess
  strategies:
    subprocess:
      max_concurrency: 16
      hard_cpu_limit_pct: 80
    docker:
      image: agent-runtime:latest
      network_policy: deny-all
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
    root: /workspace
  git_ops:
    type: git
agents:
  bug_fixer:
    model_provider: openrouter_primary
    sandbox_strategy: subprocess
    tools: [fs_local, git_ops]
    dependency_pools: [filesystem_pool, claude_code_pool]
    max_context_tokens: 120k
dependency_pools:
  filesystem_pool:
    type: filesystem
    paths: [/workspace, /tmp]
  claude_code_pool:
    type: claude_code
    max_instances: 3
```

### 分发转换
`ConfigResolver.build_agent_config(agent_name)` -> 返回 AgentConfig：
- 解析模型 provider
- 合并 sandbox 默认策略 + agent override
- 工具引用解析为 MCP tool connection配置
- 注入 observability hooks

---
## 2. 模型提供者抽象与用量统计
### 接口定义
```python
class ModelProvider(ABC):
    name: str
    supports_stream: bool
    async def generate(self, prompt, **opts) -> ModelResult: ...
    async def stream(self, prompt, **opts) -> AsyncIterator[ModelChunk]: ...
    def get_usage(self) -> ProviderUsageSnapshot: ...
```
### Usage 维度
- requests_total
- tokens_input_total
- tokens_output_total
- latency_avg_ms / p95_ms
- cost_usd_accumulated (基于 pricing 配置)
### 聚合
`UsageTracker`：集中从所有 Provider 拉取 snapshot 并生成周期事件 `ModelUsageEvent` -> Observability bus。

### OpenRouter Provider Stub
- 统一 headers 与错误重试（指数退避）
- 解析响应：`usage.input_tokens` / `usage.output_tokens`
- 定价：通过 Config 中 pricing 转换为 cost
- 事件：每次完成后 emit `ModelInvocationEvent`

---
## 3. MCP 服务层
### 目标
统一启动/管理多个 MCP 服务，提供聚合工具描述，供 Agent 自动注册使用。
### 组件
```python
class McpServiceRegistry:
    async def register(service_config) -> ServiceHandle
    async def start_all()
    async def stop_all()
    def list_tools() -> list[ToolInfo]
```
### 运行策略
- 惰性启动：第一次有 Agent 请求才启动
- 健康检查：/health endpoint poll
- 工具合并：去重（按 name），冲突策略：后注册覆盖或显式命名空间 `fs.read` vs `git.read`

---
## 4. 沙箱执行环境
### 策略 & 扩展点
- subprocess: 当前默认，限制：执行超时、目录白名单
- docker: 容器隔离，参数：image、cpu/mem、network
- future: firecracker/microVM

### SandboxManager
```python
class SandboxManager:
    async def create_session(agent_id) -> SandboxSession
    async def run(session, task: SandboxTask) -> SandboxResult
    async def cleanup(session)
```
### 资源控制字段
- cpu_limit_pct
- memory_limit_mb
- max_open_files
- network_policy (allow/deny/list)
- filesystem_mounts (ro/rw)

### 安全与审计
- 所有执行产生 `SandboxExecutionEvent`
- 失败/超时 -> `SandboxViolationEvent`

---
## 5. 标准日志与中间状态采集 (Observability)
### 事件类型
| 事件 | 说明 |
|------|------|
| LogEvent | 标准化日志输出（level, component, message, context） |
| ModelInvocationEvent | 模型调用完成（provider, tokens, cost, latency） |
| ModelUsageEvent | 周期性 provider 聚合用量快照 |
| DependencyPoolEvent | acquire/release/cleanup 动作与统计 |
| SandboxExecutionEvent | 沙箱任务执行开始/结束 |
| StateSnapshot | Agent 中间状态（当前阶段、pending tasks、最近结果） |
| ToolInvocationEvent | MCP 工具调用（名称、耗时、成功/失败） |

### 事件总线
```python
class EventBus:
    def publish(event: BaseEvent)
    def subscribe(event_type, handler)
    def flush(exporter)
```
### Exporter
- stdout
- file(jsonl)
- memory(buffer for API查询)
- future: otlp / prometheus adapter

### 度量与日志统一
- 日志模块新增 `StructuredLogger` -> 生成 LogEvent -> EventBus
- 兼容现有 `set_logging`，增加 collector hook

---
## 6. 依赖池事件集成
在 `DependencyPool.acquire/release/cleanup` 中：
```python
bus.publish(DependencyPoolEvent(
  action="acquire",
  dependency_type=self.dependency_type,
  agent_id=agent_id,
  in_use=len(self._in_use),
  available=self._available.qsize()
))
```

---
## 7. 初始化流程
`initialize_system(config_path)`：
1. 加载并验证 global config
2. 构建 `UnifiedConfig` (Pydantic model)
3. 初始化 EventBus & exporters
4. 注册 ModelProviders -> UsageTracker 定时任务
5. 注册 MCP 服务 -> 惰性启动策略
6. 初始化 SandboxManager
7. 暴露 `get_agent_runtime(agent_name)` 构造 Agent 所需上下文：
   - provider handle
   - sandbox session factory
   - tools list
   - observability hooks

---
## 8. 错误与边界情况
| 场景 | 处理策略 |
|------|----------|
| 配置缺失字段 | 使用默认值 + Warning Event |
| Provider 请求失败 | 重试 + 记录失败计数 + CircuitBreaker（未来） |
| MCP 服务启动失败 | 标记服务不可用 + 发布 ServiceHealthEvent |
| 沙箱策略不支持 | 抛出 ConfigurationError + 事件通知 |
| 用量统计溢出 | 自动切分周期，归档老数据 |

---
## 9. 可扩展点
- Provider: 新增 HuggingFace / Local 模型 -> register
- Sandbox: 增加远程隔离（K8s job）适配器
- Observability: 增加 OpenTelemetry exporter
- Tool 层：加入工具调用性能分析（p95、错误率）

---
## 10. 代码骨架（示例片段）
```python
# system/config.py
class UnifiedConfig(BaseModel):
    meta: MetaConfig
    logging: LoggingConfig
    observability: ObservabilityConfig
    sandbox: SandboxConfig
    model_providers: Dict[str, ModelProviderConfig]
    mcp_services: Dict[str, McpServiceConfig]
    agents: Dict[str, AgentConfig]
    dependency_pools: Dict[str, DependencyPoolConfig]

# system/model_provider.py
class ModelProvider(ABC):
    name: str
    pricing: PricingModel
    async def generate(self, prompt: str, **opts) -> ModelResult: ...

class OpenRouterProvider(ModelProvider):
    async def generate(...):
        # httpx request -> parse usage -> update tracker -> emit event
        ...

# system/observability.py
class BaseEvent(BaseModel):
    ts: float = Field(default_factory=lambda: time.time())
    event_type: str

class EventBus:
    def publish(self, event: BaseEvent): ...
    def subscribe(self, etype: str, handler: Callable): ...

# system/sandbox.py
class SandboxManager:
    async def create_session(self, agent_id: str) -> SandboxSession: ...
```

---
## 11. 渐进实施优先级
1. 配置 Schema + EventBus 基础
2. ModelProvider + UsageTracker + OpenRouter stub
3. MCP Registry 与工具合并
4. SandboxManager 最小可用版本（subprocess）
5. Observability 事件类型与日志集成
6. AgentConfig 转换与全局入口
7. 深度集成：依赖池事件、工具调用事件、成本分析

---
## 12. 成功度量
| 指标 | 说明 |
|------|------|
| Provider 响应平均延迟 | 降低与监控是否准确 |
| Token 计费对账误差 | < 1% |
| 沙箱执行隔离失败率 | < 0.1% |
| 事件丢失率 | < 0.01% （内存 buffer 满做 backpressure） |
| 单 Agent 初始化时间 | < 500ms |

---
## 13. 后续演进
- 引入策略引擎对不同 Agent 分配模型/沙箱资源
- 动态弹性：基于当前用量自动扩容 Provider 或沙箱执行实例
- 风险审计：记录潜在越权文件访问事件
- 成本预测：基于近期 token 曲线预测未来 24h 成本

---
## 总结
该设计统一了多 Agent 平台的关键抽象：配置、模型调用、MCP 工具、沙箱与可观测性。通过事件总线与标准化 Schema，为后续的弹性扩展、成本优化与安全审计提供了坚实基础。接下来将逐步落地骨架代码与最小可运行实现。