# Bug Fix Platform Architecture

> 目标：统一支持 GitHub Actions、函数计算(FC)、本地 CLI，多 Agent / 多执行器工作流，并可扩展至更多模型与任务类型。

## 1. 分层结构概览

```
bug_fix/
  app.py                  # FC 服务入口（将迁移为 adapters.fc_service）
  executors.py            # 将拆分为 executors/*.py
  git_helpers.py          # 将迁移到 git/helper.py
  bug_fix_agent.py        # Agent 接口与 Claude 实现，未来放入 agents/
  docs/                   # 文档
  tests/                  # 测试用例
  samples/                # 使用样例与演示脚本
```

建议演进到：
```
bug_fix/
  runtime/
    environment.py        # 统一加载运行环境（Actions / FC / CLI）
    paths.py              # 工作区/缓存路径解析
    context_loader.py     # Issue / 用户请求 / CLI Prompt 上下文加载
  agents/
    base.py               # BugFixAgentInterface 抽象
    claude_agent.py       # Claude 实现
    cursor_agent.py       # Cursor 占位
    registry.py           # AgentRegistry 动态注册
  executors/
    base.py               # Executor 抽象
    claude_code.py        # ClaudeCodeExecutor 拆分
    cursor.py             # CursorExecutor
    custom.py             # CustomCommandExecutor
    factory.py            # ExecutorFactory
  git/
    helper.py             # GitHelper
    pr_formatter.py       # 标准化 PR 描述生成
  workflows/
    pipeline.py           # 多阶段编排入口
    steps/
      planner_step.py
      worker_step.py
      evaluator_step.py
      git_commit_step.py
      pr_create_step.py
  observability/
    live_status.py        # 实时状态（已有）
    metrics.py            # 指标聚合
    logging_config.py     # 结构化日志
  adapters/
    github_actions.py     # 解析事件 + 调用 pipeline
    fc_service.py         # FastAPI 封装（替换 app.py）
    cli.py                # 本地命令行入口
  docs/
    ARCHITECTURE.md
    ROADMAP.md
    DESIGN_DECISIONS.md
  tests/
    unit/
    integration/
    e2e/
  samples/
    basic_run/
    multi_agent_ab/
```

## 2. 核心抽象

### RuntimeConfig
统一运行环境配置，兼容不同入口。
```python
class RuntimeConfig(BaseModel):
    env_type: Literal['github_actions','fc','cli']
    workspace_root: Path
    repo_url: str | None
    branch: str = 'main'
    token: str | None
    model: str = 'sonnet'
    executor_type: str = 'claude-code'
    agent_type: str = 'claude'
    task_type: str = 'issue_fix'
    enable_planner: bool = True
    enable_worker: bool = True
    enable_evaluator: bool = True
    planner_max_turns: int = 10
    worker_max_turns: int = 30
    evaluator_max_turns: int = 10
```
来源优先级：请求参数 > 环境变量 > 默认值。

### ExecutionPipeline
统一调度多阶段：Planner → Worker → Evaluator → Git/PR。

```python
class ExecutionPipeline:
    async def run(self, config: RuntimeConfig, task_context: TaskContext) -> PipelineResult:
        # 1. Git 初始化
        # 2. 选择 Agent + Executor
        # 3. Planner 阶段（可选）
        # 4. Worker 阶段（修改文件 + 记录命令）
        # 5. Evaluator 阶段（质量与完成度判定）
        # 6. PR 创建（条件满足且有 token）
        # 7. 指标与状态写入
        return result
```

### BugFixAgentInterface
扩展到支持不同 LLM 供应商 / IDE 助手。
接口：`analyze_codebase() / analyze_issue() / create_fix() / implement_changes()`。
未来增强：`plan() / evaluate()` 以适配可选内置规划 / 评估能力。

### Executor
职责：封装“如何执行模型交互与工具调用”，对外只暴露 `execute()` 与高级 `execute_with_multi_agent()`。

## 3. 多环境统一策略

| 维度 | GitHub Actions | FC | CLI | 抽象 |
|------|----------------|----|-----|------|
| Workspace | `$GITHUB_WORKSPACE` | `/mnt/oss/workspace/<task>` | `./workspace/<task>` | WorkspaceResolver |
| Repo 获取 | actions/checkout | worktree + 共享仓库 | git clone | GitStrategy |
| 状态持久化 | PR / artifact / console | JSON 文件 | 本地 JSON | StatusWriter |
| 并发控制 | job 自然隔离 | 文件锁 `.running` | 进程锁 | ConcurrencyGuard |
| 日志 | runner log | `/logs/<task>/session.log` | `stdout + file` | LogSink |
| PR 创建 | GITHUB_TOKEN | request.git_token | token 或跳过 | PRService |

## 4. 多 Agent 扩展规划

1. Registry 模式：
```python
AgentRegistry.register('claude', ClaudeBugFixAgent)
AgentRegistry.get('claude')
```
2. 能力标记：`AgentCapabilities(can_plan, can_edit_files, supports_streaming, supports_eval)`。
3. 实验模式：并行两个 agent → 两个分支 → 评估结果写入对比表。
4. 后续接入：Cursor / OpenAI function calling / DeepSeek / 自研 AST agent。

## 5. 质量与指标

统一指标结构：
```json
{
  "task_id": "...",
  "status": "completed",
  "phases": {
    "planner": {"turns": 5, "cost_usd": 0.012},
    "worker": {"turns": 18, "files_modified": 4, "commands": 3},
    "evaluator": {"status": "COMPLETE", "recommendations": []}
  },
  "summary": {
    "total_cost_usd": 0.034,
    "total_turns": 28,
    "duration_ms": 123456
  },
  "git": {
    "branch": "agent/task-xxxx",
    "pr_url": "https://github.com/org/repo/pull/123"
  }
}
```

扩展方向：
- 失败原因分类（超时 / 语法错误 / 评估未通过）
- 风险标签：`LARGE_DIFF`, `SECRET_RISK`, `LOW_TEST_COVERAGE`
- 自动回滚策略：评估失败时尝试 revert 工作区更改。

## 6. 安全
- Secret 扫描：正则 + entropy 结合（后续增强）
- Git 操作白名单：只允许修改 `src/`, `tests/`, 文档；禁止修改敏感文件（如 `.github/workflows`）
- Bash 命令过滤：收集命令并审计；危险命令（`rm -rf /`, `chmod 777 -R .`）阻断。

## 7. 执行流程状态机
```
PENDING → PLANNING → WORKING → EVALUATING → (FAILED | COMPLETED)
             ↘──────────── retry (规划失败) ─────↗
WORKING 失败 → 回滚 / 标记风险继续 → EVALUATING
```

## 8. Roadmap
| 阶段 | 内容 | 说明 |
|------|------|------|
| P0 | 目录重构 + Pipeline 雏形 | 保留现有功能不降级 |
| P1 | Executor/Agent 拆分文件 | 降低耦合与复杂度 |
| P2 | Metrics + StatusWriter 统一 | 便于可视化与比较 |
| P3 | 并行多 Agent A/B | 输出对比报告 |
| P4 | 风险标签与自动回滚 | 增强可信度 |
| P5 | 插件化工具层 (Test/Coverage) | 标准化质量闸 |
| P6 | 语义 diff 评估 | 减少潜在破坏性修改 |
| P7 | 远程缓存 & 依赖层 | 加速重复任务 |

## 9. 快速对接 GitHub Actions 示例（目标形态）
```yaml
- name: Run Bug Fix Pipeline
  run: |
    python -m bug_fix.adapters.github_actions \
      --issue-number "${{ github.event.issue.number }}" \
      --model claude-sonnet-4.1 \
      --executor claude-code \
      --agent claude
```

## 10. CLI 示例
```bash
python -m bug_fix.adapters.cli \
  --prompt "Improve logging structure" \
  --repo-url https://github.com/org/repo.git \
  --token $GITHUB_TOKEN
```

## 11. 后续文件迁移计划
| 现有文件 | 目标位置 | 状态 |
|----------|----------|------|
| app.py | adapters/fc_service.py | 待迁移 |
| executors.py | executors/*.py | 待拆分 |
| git_helpers.py | git/helper.py | 待迁移 |
| bug_fix_agent.py | agents/claude_agent.py + agents/base.py | 部分完成 |

## 12. 开发建议
1. 先引入 `RuntimeConfig` 与 `ExecutionPipeline` 空壳，保持旧接口兼容。
2. 新增 `tests/test_pipeline_smoke.py` 验证最小运行（无 PR、无 planner）。
3. 每拆分一个大文件，补充对应 README 或内联模块注释。
4. 引入 `metrics.py` 前先用简单 dict 聚合，最后写入 JSON。

---
如需我继续生成 skeleton 代码与迁移，请提出“继续”指令。