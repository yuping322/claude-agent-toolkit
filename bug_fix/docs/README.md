# bug_fix 模块文档索引

该目录用于存放架构设计、演进规划、决策记录与使用说明。

## 文件概览
| 文件 | 说明 |
|------|------|
| ARCHITECTURE.md | 总体融合架构与分层说明（GitHub Actions + FC + CLI + 多 Agent） |
| ROADMAP.md | 迭代路线图与阶段目标（待补充） |
| DESIGN_DECISIONS.md | 重大设计决策与权衡记录（待补充） |
| README.md | 当前索引文件 |

## 后续建议文档
- CONFIGURATION.md：各环境变量与配置优先级说明
- PIPELINE.md：多阶段执行语义与状态机细节
- METRICS.md：指标定义与收集策略
- SECURITY.md：安全策略（命令过滤 / secret 扫描 / 分支策略）

## 目录规划摘要
参见 `ARCHITECTURE.md` 获取详细分层结构与迁移计划。

## 快速查阅
- 如果你要扩展新的 Agent → 查看 `ARCHITECTURE.md` 中的 `AgentRegistry` 部分
- 如果你要在 GitHub Actions 中使用 → 使用未来的 `adapters/github_actions.py`
- 如果你要在 FC 部署 → 迁移 `app.py` 为 `adapters/fc_service.py`

---
需要我自动生成其余文档骨架请说明。