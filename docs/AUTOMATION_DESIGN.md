# Autonomous Ephemeral Task Design

> 状态：Draft (初版 PoC 设计)  
> 目标：以独立一次性任务模式（无集中调度）验证自动化开发与 PR 生产流程。

---
## 1. 背景与目标
我们希望在**无需长期常驻调度器**的前提下，让多个自动化任务（特性开发、重构、测试补齐、依赖升级等）像“临时开发者”一样并行工作：
- 每个任务自包含：启动 → 分析 → 生成变更 → 质量验证 → 推送分支 → 创建 PR → 退出
- 互不依赖，无共享内存或缓存；冲突用 `git rebase` 解决
- 人类开发者按需审阅、合并或反馈
- 可逐步演进为更系统化的只读聚合与可视化（当前阶段明确不考虑集中式任务调度）

---
## 2. 范围与非目标
| 范围 (In Scope) | 非目标 (Out of Scope 初期) |
|-----------------|-----------------------------|
| 单任务端到端执行 | 构建集中式队列/调度器 |
| 自动 PR 生成 | 权限/审计系统 |
| 质量闸（测试/覆盖率/lint） | 复杂语义差异验证 (形式化证明) |
| Rebase 冲突自处理（简单场景） | AI 自动解决复杂业务逻辑冲突 |
| 多任务并发（人工或脚本批量启动） | 跨任务共享缓存/向量索引 |

---
## 3. 示例目标仓库（抽象）
假设验证仓库：`github.com/org/sample-service`

结构简化示例：
```
.
├── src/
│   ├── service/
│   │   ├── user.py
│   │   ├── order.py
│   │   └── payment.py
│   ├── utils/
│   │   ├── retry.py
│   │   └── logging.py
│   └── __init__.py
├── tests/
│   ├── test_user.py
│   └── test_order.py
├── requirements.txt
├── pyproject.toml
└── README.md
```
特征：部分模块缺测试，如 `payment.py`；日志用法不统一；依赖老旧。

---
## 4. 核心概念模型
### 4.1 Task Specification (`task.yaml`)
```yaml
id: add-payment-tests
branch: auto/add-payment-tests
objective: "为 payment 模块补齐单元测试并提升覆盖率"
target:
  include:
    - "src/service/payment.py"
  exclude: []
strategy:
  batch_mode: single_file
limits:
  max_commits: 5
  max_runtime_minutes: 30
quality_gates:
  require_all_tests_pass: true
  min_coverage_delta: 0
  forbid_new_type_errors: true
pr:
  title_prefix: "feat(test):"
  risk_rules:
    high_if:
      - "coverage_delta < -2"
```

### 4.2 Execution Phases
1. PREPARE → 2. ANALYZE → 3. GENERATE → 4. VALIDATE → 5. COMMIT/REBASE → 6. AGGREGATE → 7. PR → 8. EXIT

### 4.3 Quality Metrics
| 指标 | 说明 | 数据来源 |
|------|------|----------|
| tests_passed / failed | 回归健康 | pytest exit code & report |
| coverage_before / after | 代码风险 | coverage 工具 |
| lint_errors | 规范一致性 | ruff / flake8 |
| type_errors | 稳定性 | mypy |
| diff_stats | 变更规模 | `git diff --shortstat` |
| risk_level | 自动评估 | 规则 + （可选 LLM） |

---
## 5. 命令清单（按阶段）
### 5.1 初始化 & 分支
```bash
git clone git@github.com:org/sample-service.git
cd sample-service
git fetch origin
git checkout main
git pull --ff-only
git checkout -b auto/<task-id>
```

### 5.2 环境依赖 & 基线
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
coverage run -m pytest -q || true
coverage report -m > baseline_coverage.txt
coverage xml  # 可选，后续做差异分析
```

### 5.3 生成/修改（示例：补测试）
```bash
# 由任务脚本或 Agent 写入 tests/test_payment.py
echo "<generated test code>" > tests/test_payment.py
```

### 5.4 质量闸执行
```bash
ruff check src/ tests/
python -m mypy src/ --ignore-missing-imports
coverage run -m pytest -q
coverage report -m > current_coverage.txt
git diff --name-only > changed_files.txt
```

### 5.5 提交与重试
```bash
git add tests/test_payment.py
git commit -m "test: add unit tests for payment module"
# 若推送失败或落后：
git fetch origin
git rebase origin/main || git rebase --abort
```

### 5.6 推送 & PR
```bash
git push -u origin auto/<task-id>
# 使用 GitHub CLI
gh pr create \
  --title "feat(test): add payment tests (auto)" \
  --body-file artifacts/<task-id>/pr.md \
  --label automated --label test
```

### 5.7 状态产物
```bash
mkdir -p artifacts/<task-id>
python scripts/gen_status_json.py --out artifacts/<task-id>/status.json
python scripts/gen_pr_body.py > artifacts/<task-id>/pr.md
```

### 5.8 退出码
| Exit Code | 含义 |
|-----------|------|
| 0 | 正常完成且通过质量闸 |
| 1 | 致命失败（构建/测试无法恢复） |
| 2 | 部分成功（PR 有风险标签） |

---
## 6. 关键场景模拟
### 场景 A：自动补测试成功
1. 启动任务 → 创建分支 `auto/add-payment-tests`
2. 生成 `tests/test_payment.py`，通过所有测试
3. 覆盖率 +2%，无 lint/type 错误
4. 推送并创建 PR，PR 描述自动总结
5. 人类 24h 后合并 → 任务完成

### 场景 B：测试失败回滚
1. 生成测试用例但失败（覆盖真实 bug）
2. 策略：保留失败用例 OR 回滚？（可配置）
3. 若配置为“保留”：提交并在 PR 标记 `risk: potential-bug`
4. PR 描述中嵌入失败日志摘要

### 场景 C：与主干并行其他开发者改动同一文件
1. 你的分支基于 main@A，另一开发者合并 main@B
2. 推送时报 `non-fast-forward`
3. 执行：`git fetch && git rebase origin/main`
4. 若产生冲突：
   - 仅测试文件冲突 → 自动保留两侧并合并
   - 业务逻辑冲突 → 放弃该文件修改 → 标记风险 → 继续
5. 最终 PR 标记：`needs-manual-review`

### 场景 D：覆盖率下降
1. 删除了一些未使用代码但覆盖率下降 1%
2. 规则：不允许下降 → 回滚该 commit
3. 继续剩余文件处理 → 成功后 PR 不包含有害变更

### 场景 E：并发启动 5 个自动任务
- 各自使用分支：`auto/task-1` … `auto/task-5`
- 无共享状态 → 只要不频繁改动同一热点文件则稳定运行
- 若多个任务针对同一目录：后推送者会经历一次 rebase

### 场景 F：任务半完成退出（超时）
- 处理了前 30% 文件 → 已提交 4 个 commit
- 超时时间到 → 写入 `status.json` 标记 `partial=true`
- PR 仍然创建，描述中提示“仅覆盖部分目标（30%）”

---
## 7. 质量与风险控制（规则明细）
| 规则 | 判定 | 动作 | PR 标记 |
|------|------|------|---------|
| 测试失败 | pytest exit != 0 | 回滚或保留失败用例（配置） | `tests-failed` |
| 覆盖率下降 | after < before | 回滚该批次 | `coverage-risk` |
| Lint 严重错误 | ruff exit != 0 | 不提交此批 | `style-fix-needed` |
| 类型错误新增 | mypy 新错误数 > 0 | 回滚该批 | `type-risk` |
| 大规模改动 | diff 行数 > 阈值 | 分拆或标记 | `large-diff` |
| 重复失败 N 次 | 同一批重试 > N | 终止任务 | `aborted` |

---
## 8. 数据产物格式
`artifacts/<task-id>/status.json` 示例：
```json
{
  "id": "add-payment-tests",
  "branch": "auto/add-payment-tests",
  "commits": 4,
  "tests_passed": 128,
  "tests_failed": 0,
  "coverage_before": 72.1,
  "coverage_after": 74.5,
  "lint_errors": 0,
  "type_errors": 0,
  "risk_labels": [],
  "partial": false,
  "pr_url": "https://github.com/org/sample-service/pull/123",
  "finished_at": "2025-11-07T12:34:56Z"
}
```

---
## 9. 安全与权限
| 风险 | 缓解措施 |
|------|----------|
| Git 凭证泄露 | 使用只读 PAT + 细粒度权限（仅 repo:write, pull_request） |
| 误删文件 | 仅操作 allowlist include 的文件路径 |
| 模型误修改关键逻辑 | 非测试类任务先运行“干预前 diff 预测”提示人工确认（后续演进） |
| 并发资源占用 | 最外层控制一次性启动数量（shell 限制/CI 并发） |

---
## 10. 演进路径 Roadmap
阶段 | 增强 | 说明
------|------|------
P0 | 单任务 PoC | 1 个补测试任务端到端
P1 | 并发多个任务 | 手工并行 + 观察冲突率
P2 | 统一任务模板库 | 产出 5–8 种任务类型（测试、重构、依赖等）
P3 | 结果聚合 | 汇总 status.json 生成 dashboard.md
P4 | 引入轻量任务启动器 | 扫描 tasks/ 并串行/并行执行
P5 | 语义风险评估 | LLM 对 diff 做语义安全等级评估
P6 | 自动分批拆分超大 PR | 大变更自动切片
P7 | AI 辅助冲突处理 | 针对重复冲突生成修正建议
P8 | 延伸到跨语言迁移 | 结合翻译 / AST 分析工具

---
## 11. 风险评估
| 风险 | 等级 | 备注 | 缓解 |
|------|------|------|------|
| 模型幻觉生成错误测试 | 中 | 误测通过 | 增加“脆弱断言检测”
| Lint / Type 工具性能 | 低 | 大项目慢 | 增量检查
| Rebase 冲突频繁 | 中 | 热点文件任务过多 | 任务排期/合并优先级
| 覆盖率波动导致阻塞 | 低 | 小数误差 | 允许 ±0.5% 漂移
| 人工审阅负担增加 | 中 | 任务多 PR 多 | 自动摘要+风险标注

---
## 12. 验证成功标准 (Success Criteria)
| 指标 | 目标 |
|------|------|
| 单任务平均耗时 | < 30 min |
| 人工审阅平均耗时 | < 5 min / PR |
| 冲突发生率 | < 10% 任务需要人工解决冲突 |
| 质量闸通过率 | > 85% 第一次尝试成功 |
| 覆盖率提升（测试类任务） | 每周 +1~2% 稳定上升 |

---
## 13. 附录：命令速览表
类别 | 命令 | 说明
-----|------|----
Git | `git checkout -b auto/<id>` | 创建任务分支
Git | `git pull --ff-only` | 更新 main
Git | `git rebase origin/main` | 冲突前置消解
依赖 | `pip install -r requirements.txt` | 安装依赖
测试 | `coverage run -m pytest -q` | 运行测试
覆盖率 | `coverage report -m` | 展示覆盖结果
Lint | `ruff check src/ tests/` | 代码规范
类型 | `mypy src/ --ignore-missing-imports` | 类型检查
Diff | `git diff --shortstat` | 变更统计
提交 | `git commit -m "feat: ..."` | 原子提交
推送 | `git push -u origin auto/<id>` | 推送分支
PR | `gh pr create --title ... --body-file ...` | 创建 PR
状态输出 | `python scripts/gen_status_json.py` | 生成状态文件

---
## 14. 下一步实施建议
1. 选取一个真实仓库建立第一份 `task.yaml`
2. 编写 `run_task.py`（纯脚手架 + 日志 + 子命令）
3. 跑首个“补测试”任务，验证：分支、提交、PR、质量闸
4. 加入第二类任务（例如：统一 logging 格式）
5. 建立 `artifacts/` 汇总输出并人工审阅

> 以上设计不依赖集中调度器，适合立即开始 PoC。后续任何平台化增强都可在不推翻结构的情况下叠加。

---
## 15. 可执行 Samples（真实可跑的顺序示例）
以下命令假设：
- 目标仓库：`github.com/org/sample-service`
- 任务 ID：`add-payment-tests`
- 使用 bash / Linux / macOS 环境

### 15.1 一次性全流程（成功路径）
```bash
# 1. 克隆与分支
git clone git@github.com:org/sample-service.git
cd sample-service
git fetch origin
git checkout main
git pull --ff-only
git checkout -b auto/add-payment-tests

# 2. 环境 & 基线
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
coverage run -m pytest -q || true
coverage report -m | tee artifacts_baseline.txt

# 3. 生成测试文件（示例占位）
mkdir -p tests
cat > tests/test_payment.py <<'EOF'
import pytest
from src.service.payment import calculate_fee

def test_positive_fee():
    assert calculate_fee(100) == 100 * 0.05

def test_zero_fee():
    assert calculate_fee(0) == 0
EOF

# 4. 质量闸
ruff check src/ tests/
python -m mypy src/ --ignore-missing-imports
coverage run -m pytest -q
coverage report -m | tee artifacts_current.txt

# 5. 差异与统计
git diff --shortstat > artifacts_diff.txt
git add tests/test_payment.py artifacts_baseline.txt artifacts_current.txt artifacts_diff.txt
git commit -m "test: add payment tests (auto)"

# 6. 推送与 PR (需 gh CLI 已登录)
git push -u origin auto/add-payment-tests
mkdir -p artifacts/add-payment-tests
cat > artifacts/add-payment-tests/pr.md <<'EOF'
## feat(test): add payment tests (auto)
增加 payment 模块单元测试；覆盖率 +2%。
EOF
gh pr create --title "feat(test): add payment tests (auto)" \
  --body-file artifacts/add-payment-tests/pr.md \
  --label automated --label test
```

### 15.2 推送失败（需要 rebase）
```bash
git fetch origin
git rebase origin/main || git rebase --abort
# 解决冲突后继续：
git add <conflict-files>
git rebase --continue
git push -f origin auto/add-payment-tests
```

### 15.3 失败任务生成失败 PR（保留痕迹）
```bash
# 假设测试失败
coverage run -m pytest -q || echo "TEST_FAILED" > FAIL_FLAG

if [ -f FAIL_FLAG ]; then
  mkdir -p artifacts/add-payment-tests-fail
  pytest -q || pytest -q --maxfail=1 | head -n 200 > artifacts/add-payment-tests-fail/trace.txt
  cat > artifacts/add-payment-tests-fail/FAILURE.md <<'EOF'
# Task Failure Report
Task: add-payment-tests
Phase: VALIDATE_TESTS
Failure: TESTS_FAILED
Summary: 新增测试未通过，可能暴露真实业务逻辑问题。
Next Steps: 人工修复后重试。
EOF
  git checkout -b auto/add-payment-tests-fail
  git add artifacts/add-payment-tests-fail/FAILURE.md artifacts/add-payment-tests-fail/trace.txt
  git commit -m "fail: add-payment-tests aborted (TESTS_FAILED)"
  git push -u origin auto/add-payment-tests-fail
  gh pr create --title "fail: add-payment-tests (TESTS_FAILED)" \
    --body-file artifacts/add-payment-tests-fail/FAILURE.md \
    --label automated --label failure --draft
fi
```

### 15.4 自动重试（仅网络类失败）
```bash
# 假设网络错误标记在 NET_FAIL_FLAG
if [ -f NET_FAIL_FLAG ]; then
  git checkout main
  git pull --ff-only
  git checkout -b auto/add-payment-tests-retry-1
  # 重新执行生成 + 质量闸...
fi
```

### 15.5 快速状态文件生成脚本示例（Python）
```bash
python - <<'PY'
import json, time
data = {
  "id": "add-payment-tests",
  "branch": "auto/add-payment-tests",
  "tests_passed": 128,
  "tests_failed": 0,
  "coverage_before": 72.1,
  "coverage_after": 74.3,
  "risk_labels": [],
  "finished_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
}
print(json.dumps(data, ensure_ascii=False, indent=2))
PY
```

### 15.6 清理草稿失败分支（人工处理后）
```bash
gh pr close <pr-number> --comment "Resolved in main via manual fix. Closing failure trace PR."
git branch -D auto/add-payment-tests-fail || true
```

> 上述 Samples 聚焦“可执行 + 可验证”，并明确当前阶段不引入集中调度，只做一次性任务脚本式运行。
