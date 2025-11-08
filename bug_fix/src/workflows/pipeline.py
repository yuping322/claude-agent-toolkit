#!/usr/bin/env python3
"""
Workflows Pipeline - Execution pipeline for bug fix workflows.

This module provides the ExecutionPipeline class that orchestrates
the multi-stage bug fix process: Planner → Worker → Evaluator → PR.
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime

from ..agents import AgentRegistry, BugFixAgentInterface
from ..executors import ExecutorFactory
from ..observability import LiveStatusTracker, LiveStatusEntry
from ..runtime import ExecutionContext

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """流水线阶段枚举"""
    PLANNER = "planner"
    WORKER = "worker"
    EVALUATOR = "evaluator"
    PR_CREATOR = "pr_creator"


class PipelineStatus(Enum):
    """流水线状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineResult:
    """流水线执行结果"""
    stage: PipelineStage
    status: PipelineStatus
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def duration(self) -> Optional[float]:
        """执行持续时间（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


@dataclass
class PipelineContext:
    """流水线上下文"""
    execution_context: ExecutionContext
    agent: BugFixAgentInterface
    executor: Any  # Executor instance
    status_tracker: LiveStatusTracker

    # 阶段间共享数据
    shared_data: Dict[str, Any] = field(default_factory=dict)

    # 结果存储
    results: Dict[PipelineStage, PipelineResult] = field(default_factory=dict)


class ExecutionPipeline:
    """执行流水线 - 协调多阶段 bug fix 流程"""

    def __init__(self,
                 agent_registry: Optional[AgentRegistry] = None,
                 executor_factory: Optional[ExecutorFactory] = None):
        self.agent_registry = agent_registry or AgentRegistry()
        self.executor_factory = executor_factory or ExecutorFactory()

        # 阶段处理器
        self.stage_handlers: Dict[PipelineStage, Callable[[PipelineContext], Awaitable[PipelineResult]]] = {
            PipelineStage.PLANNER: self._handle_planner_stage,
            PipelineStage.WORKER: self._handle_worker_stage,
            PipelineStage.EVALUATOR: self._handle_evaluator_stage,
            PipelineStage.PR_CREATOR: self._handle_pr_creator_stage,
        }

        # 流水线配置
        self.max_retries = 3
        self.timeout_per_stage = 300  # 5 minutes per stage

    async def execute(self, execution_context: ExecutionContext) -> Dict[PipelineStage, PipelineResult]:
        """执行完整的流水线

        Args:
            execution_context: 执行上下文

        Returns:
            各阶段的执行结果
        """
        logger.info(f"Starting execution pipeline for issue: {execution_context.issue_title}")

        # 初始化流水线上下文
        pipeline_context = await self._initialize_pipeline_context(execution_context)

        # 执行各个阶段
        results = {}
        for stage in PipelineStage:
            try:
                logger.info(f"Executing stage: {stage.value}")
                result = await self._execute_stage(stage, pipeline_context)
                results[stage] = result

                # 如果阶段失败，根据策略决定是否继续
                if result.status == PipelineStatus.FAILED:
                    if not self._should_continue_after_failure(stage, result):
                        logger.error(f"Pipeline stopped at stage {stage.value} due to failure")
                        break

            except Exception as e:
                logger.error(f"Unexpected error in stage {stage.value}: {e}")
                error_result = PipelineResult(
                    stage=stage,
                    status=PipelineStatus.FAILED,
                    error=str(e),
                    start_time=datetime.now(),
                    end_time=datetime.now()
                )
                results[stage] = error_result
                break

        logger.info(f"Pipeline execution completed with {len(results)} stages")
        return results

    async def _initialize_pipeline_context(self, execution_context: ExecutionContext) -> PipelineContext:
        """初始化流水线上下文"""
        # 获取 agent
        agent = self.agent_registry.create_bug_fix_agent(execution_context.agent_type)
        if not agent:
            raise ValueError(f"Agent type '{execution_context.agent_type}' not available")

        # 获取 executor
        executor = self.executor_factory.create(execution_context.executor_type)
        if not executor:
            raise ValueError(f"Executor type '{execution_context.executor_type}' not available")

        # 初始化状态跟踪器
        status_tracker = LiveStatusTracker()

        return PipelineContext(
            execution_context=execution_context,
            agent=agent,
            executor=executor,
            status_tracker=status_tracker
        )

    async def _execute_stage(self, stage: PipelineStage, context: PipelineContext) -> PipelineResult:
        """执行单个阶段"""
        start_time = datetime.now()

        # 创建结果对象
        result = PipelineResult(
            stage=stage,
            status=PipelineStatus.RUNNING,
            start_time=start_time
        )

        try:
            # 更新状态
            context.status_tracker.update(
                f"stage_{stage.value}",
                f"Executing {stage.value} stage",
                {"stage": stage.value, "status": "running"}
            )

            # 执行阶段处理器
            handler = self.stage_handlers.get(stage)
            if not handler:
                raise ValueError(f"No handler found for stage: {stage}")

            # 设置超时
            result = await asyncio.wait_for(
                handler(context),
                timeout=self.timeout_per_stage
            )

            result.status = PipelineStatus.COMPLETED
            logger.info(f"Stage {stage.value} completed successfully")

        except asyncio.TimeoutError:
            result.status = PipelineStatus.FAILED
            result.error = f"Stage {stage.value} timed out after {self.timeout_per_stage}s"
            logger.error(result.error)
        except Exception as e:
            result.status = PipelineStatus.FAILED
            result.error = f"Stage {stage.value} failed: {str(e)}"
            logger.error(result.error)
        finally:
            result.end_time = datetime.now()

            # 更新状态
            status = "completed" if result.status == PipelineStatus.COMPLETED else "failed"
            context.status_tracker.update(
                f"stage_{stage.value}",
                f"Stage {stage.value} {status}",
                {
                    "stage": stage.value,
                    "status": status,
                    "duration": result.duration,
                    "error": result.error
                }
            )

        return result

    async def _handle_planner_stage(self, context: PipelineContext) -> PipelineResult:
        """处理规划阶段"""
        # 分析代码库
        codebase_analysis = await context.agent.analyze_codebase(context.execution_context.repo_url)

        # 分析 issue
        issue_analysis = await context.agent.analyze_issue(
            context.execution_context.issue_title,
            context.execution_context.issue_body
        )

        # 生成修复计划
        fix_plan = {
            "codebase_analysis": codebase_analysis,
            "issue_analysis": issue_analysis,
            "estimated_complexity": self._estimate_complexity(issue_analysis),
            "required_files": self._extract_required_files(issue_analysis),
        }

        # 存储到共享数据
        context.shared_data["fix_plan"] = fix_plan

        return PipelineResult(
            stage=PipelineStage.PLANNER,
            status=PipelineStatus.COMPLETED,
            output=fix_plan,
            metadata={"files_analyzed": len(codebase_analysis.get("files", []))}
        )

    async def _handle_worker_stage(self, context: PipelineContext) -> PipelineResult:
        """处理工作阶段"""
        fix_plan = context.shared_data.get("fix_plan", {})

        # 创建修复
        fix_result = await context.agent.create_fix(
            context.execution_context.issue_title,
            context.execution_context.issue_body,
            fix_plan
        )

        # 执行修复
        execution_result = await context.executor.execute(fix_result)

        # 存储结果
        context.shared_data["fix_result"] = fix_result
        context.shared_data["execution_result"] = execution_result

        return PipelineResult(
            stage=PipelineStage.WORKER,
            status=PipelineStatus.COMPLETED,
            output={"fix": fix_result, "execution": execution_result},
            metadata={"changes_applied": len(fix_result.get("changes", []))}
        )

    async def _handle_evaluator_stage(self, context: PipelineContext) -> PipelineResult:
        """处理评估阶段"""
        fix_result = context.shared_data.get("fix_result", {})
        execution_result = context.shared_data.get("execution_result", {})

        # 评估修复效果
        evaluation = await context.agent.evaluate_fix(
            context.execution_context.issue_title,
            context.execution_context.issue_body,
            fix_result,
            execution_result
        )

        # 存储评估结果
        context.shared_data["evaluation"] = evaluation

        # 决定是否需要重新执行
        needs_retry = evaluation.get("needs_retry", False)
        if needs_retry:
            logger.warning("Evaluation indicates fix needs improvement")

        return PipelineResult(
            stage=PipelineStage.EVALUATOR,
            status=PipelineStatus.COMPLETED,
            output=evaluation,
            metadata={"needs_retry": needs_retry}
        )

    async def _handle_pr_creator_stage(self, context: PipelineContext) -> PipelineResult:
        """处理 PR 创建阶段"""
        fix_result = context.shared_data.get("fix_result", {})
        evaluation = context.shared_data.get("evaluation", {})

        # 如果评估失败，不创建 PR
        if not evaluation.get("success", False):
            return PipelineResult(
                stage=PipelineStage.PR_CREATOR,
                status=PipelineStatus.CANCELLED,
                error="PR creation cancelled due to failed evaluation"
            )

        # 生成 PR 描述
        pr_description = self._generate_pr_description(context.execution_context, fix_result, evaluation)

        # 创建 PR（这里需要实现实际的 PR 创建逻辑）
        pr_result = await self._create_pull_request(
            context.execution_context,
            pr_description,
            fix_result.get("changes", [])
        )

        return PipelineResult(
            stage=PipelineStage.PR_CREATOR,
            status=PipelineStatus.COMPLETED,
            output=pr_result,
            metadata={"pr_url": pr_result.get("url")}
        )

    def _should_continue_after_failure(self, stage: PipelineStage, result: PipelineResult) -> bool:
        """决定失败后是否继续执行"""
        # 对于规划阶段失败，不继续
        if stage == PipelineStage.PLANNER:
            return False

        # 对于其他阶段，可以根据错误类型决定
        error = result.error or ""
        if "timeout" in error.lower():
            return False  # 超时不重试

        return True  # 其他错误可以继续

    def _estimate_complexity(self, issue_analysis: Dict[str, Any]) -> str:
        """估算复杂度"""
        # 简单的复杂度估算逻辑
        severity = issue_analysis.get("severity", "medium")
        affected_files = len(issue_analysis.get("affected_files", []))

        if severity == "critical" or affected_files > 5:
            return "high"
        elif severity == "high" or affected_files > 2:
            return "medium"
        else:
            return "low"

    def _extract_required_files(self, issue_analysis: Dict[str, Any]) -> List[str]:
        """提取需要的文件"""
        return issue_analysis.get("affected_files", [])

    def _generate_pr_description(self, context: ExecutionContext, fix_result: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
        """生成 PR 描述"""
        from ..git import generate_pr_description, format_file_changes_for_pr

        changes = fix_result.get("changes", [])
        formatted_changes = format_file_changes_for_pr(changes)

        return generate_pr_description(
            issue_title=context.issue_title,
            issue_body=context.issue_body,
            changes=changes,
            repo_url=context.repo_url,
            branch=context.branch
        )

    async def _create_pull_request(self, context: ExecutionContext, description: str, changes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建拉取请求"""
        # 这里需要实现实际的 PR 创建逻辑
        # 可以使用 GitHub API 或其他方式

        # 暂时返回模拟结果
        return {
            "url": f"https://github.com/{context.repo_url.split('/')[-2]}/{context.repo_url.split('/')[-1]}/pull/123",
            "number": 123,
            "title": f"fix: {context.issue_title}",
            "description": description
        }