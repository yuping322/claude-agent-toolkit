"""执行器抽象接口，支持多种后端工具

参考主项目的 executor.py 实现，使用 claude-agent-sdk 保证功能一致性和稳定性：
- 使用 claude-agent-sdk 而不是直接调用 CLI（与主项目保持一致）
- 支持多阶段工作流（Planner, Worker, Evaluator）
- 支持实时状态跟踪（LiveStatusTracker）
- 支持流式输出、工具跟踪、使用指标等功能
- 更好的错误处理和日志记录
"""

import os
import re
import subprocess
import asyncio
import logging
import time
import shutil
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List, Set
from pathlib import Path
from abc import ABC, abstractmethod

# 导入 claude-agent-sdk
try:
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        CLINotFoundError,
        ProcessError,
        CLIJSONDecodeError,
        AssistantMessage,
        ToolUseBlock,
        ToolResultBlock,
        ResultMessage,
        TextBlock,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("claude-agent-sdk not available, falling back to direct CLI call")

# 导入实时状态跟踪
try:
    from .live_status import LiveStatusTracker, LiveStatusEntry
    LIVE_STATUS_AVAILABLE = True
except ImportError:
    LIVE_STATUS_AVAILABLE = False
    LiveStatusTracker = None  # type: ignore
    LiveStatusEntry = None  # type: ignore
    logger = logging.getLogger(__name__)
    logger.warning("live_status not available, live status tracking disabled")

logger = logging.getLogger(__name__)


class Executor(ABC):
    """执行器抽象基类，定义统一的执行接口"""
    
    @abstractmethod
    async def execute(
        self,
        prompt: str,
        workspace_path: Path,
        timeout: int = 840,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, int]:
        """执行任务
        
        Args:
            prompt: 任务提示词
            workspace_path: 工作目录路径
            timeout: 超时时间（秒）
            env: 环境变量字典
            
        Returns:
            Tuple[stdout, exit_code]
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查工具是否可用"""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """获取工具名称"""
        pass


class ClaudeCodeExecutor(Executor):
    """Claude Code CLI 执行器（使用 claude-agent-sdk）
    
    参考主项目 executor.py 的实现，使用 SDK 保证功能一致性和稳定性
    支持多阶段工作流、实时状态跟踪、工具使用跟踪等功能
    """
    
    def __init__(
        self,
        binary_path: str = "claude",
        model: Optional[str] = None,
        live_status_tracker: Optional[Any] = None,
        enable_multi_agent: bool = True,
    ):
        self.binary_path = binary_path
        self.model = model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
        self.sdk_available = SDK_AVAILABLE
        self.live_status_tracker = live_status_tracker if LIVE_STATUS_AVAILABLE else None
        self.enable_multi_agent = enable_multi_agent
        self._live_context: Dict[str, Dict[str, Optional[str]]] = {}
    
    def get_name(self) -> str:
        return "claude-code"
    
    def is_available(self) -> bool:
        """检查 Claude Code CLI 是否可用
        
        参考主项目 executor.py 的 _verify_claude_cli 实现
        """
        if not self.sdk_available:
            logger.warning("claude-agent-sdk not available, falling back to direct CLI check")
            # 回退到直接检查 CLI
            try:
                result = subprocess.run(
                    [self.binary_path, "--version"],
                    capture_output=True,
                    timeout=5
                )
                return result.returncode == 0
            except Exception:
                return False
        
        # 使用 SDK 时，检查 CLI 是否可用
        try:
            result = subprocess.run(
                [self.binary_path, "--version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.debug(f"Claude Code CLI verified: {self.binary_path}")
                return True
            else:
                logger.warning(f"Claude Code CLI version check failed: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error(f"Claude Code CLI not found: {self.binary_path}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Claude Code CLI version check timeout")
            return False
        except Exception as e:
            logger.warning(f"Claude Code CLI availability check failed: {e}")
            return False
    
    async def execute(
        self,
        prompt: str,
        workspace_path: Path,
        timeout: int = 840,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, int]:
        """执行 Claude Code CLI（使用 claude-agent-sdk）
        
        参考主项目 executor.py 的实现，使用 SDK 保证功能一致性和稳定性
        
        功能：
        - 流式输出处理
        - 工具使用跟踪
        - 使用指标收集
        - 结构化错误处理
        
        返回格式保持兼容：
        - stdout: 完整的文本输出（包含所有消息和工具调用）
        - exit_code: 0 表示成功，非 0 表示失败
        """
        if not self.sdk_available:
            # 回退到直接 CLI 调用
            logger.warning("claude-agent-sdk not available, falling back to direct CLI call")
            return await self._execute_direct_cli(prompt, workspace_path, timeout, env)
        
        # 确保工作目录存在
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Executing Claude Code CLI (via SDK) in workspace: {workspace_path}")
        logger.debug(f"Prompt length: {len(prompt)} characters, model: {self.model}")
        
        # 准备环境变量
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        
        # 设置 API 配置（从环境变量获取）
        api_key = exec_env.get("ANTHROPIC_API_KEY")
        base_url = exec_env.get("ANTHROPIC_BASE_URL")
        
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, Claude Code CLI may fail")
        
        # 构建输出文本（兼容原有接口）
        output_parts: List[str] = []
        exit_code = 0
        success = True
        
        try:
            # 创建 ClaudeAgentOptions（参考主项目实现）
            options = ClaudeAgentOptions(
                cwd=str(workspace_path),
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "TodoWrite"],
                permission_mode="acceptEdits",
                max_turns=30,  # 默认最大轮次
                model=self.model,
            )
            
            # 如果设置了 base_url，需要通过环境变量传递（SDK 会自动读取）
            if base_url:
                exec_env["ANTHROPIC_BASE_URL"] = base_url
            
            # 使用 SDK 执行（流式处理）
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    # 处理助手消息
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text = block.text.strip()
                            if text:
                                output_parts.append(text)
                                logger.debug(f"Assistant text: {text[:100]}...")
                        
                        elif isinstance(block, ToolUseBlock):
                            # 跟踪工具使用
                            tool_name = block.name
                            tool_input = block.input
                            tool_info = f"[Tool: {tool_name}]"
                            if tool_name == "Bash":
                                command = tool_input.get("command", "")
                                tool_info += f" {command}"
                            elif tool_name in ["Write", "Edit"]:
                                file_path = tool_input.get("file_path", "")
                                tool_info += f" {file_path}"
                            output_parts.append(tool_info)
                            logger.debug(f"Tool use: {tool_name}")
                        
                        elif isinstance(block, ToolResultBlock):
                            # 工具结果（可选，添加到输出）
                            result_content = block.content
                            if result_content:
                                output_parts.append(f"[Tool Result] {result_content[:200]}...")
                
                elif isinstance(message, ResultMessage):
                    # 处理结果消息
                    success = not message.is_error
                    if message.result:
                        output_parts.append(f"\n[Result: {message.result}]")
                    
                    # 记录使用指标
                    if message.total_cost_usd:
                        logger.info(f"Task cost: ${message.total_cost_usd:.4f}")
                    if message.duration_ms:
                        logger.info(f"Task duration: {message.duration_ms}ms")
                    if message.num_turns:
                        logger.info(f"Task turns: {message.num_turns}")
                    
                    # 设置退出码
                    exit_code = 0 if success else 1
                    
                    if not success:
                        error_msg = message.result or "Task failed"
                        output_parts.append(f"\n[Error] {error_msg}")
                        logger.error(f"Task failed: {error_msg}")
            
            # 合并输出
            stdout = "\n".join(output_parts)
            
            if exit_code != 0:
                logger.warning(f"Claude Code CLI exited with code {exit_code}")
                logger.debug(f"Output (last 500 chars): {stdout[-500:] if len(stdout) > 500 else stdout}")
            
            return stdout, exit_code
            
        except CLINotFoundError as e:
            error_msg = f"Claude Code CLI not found: {e}"
            logger.error(error_msg)
            return error_msg, 1
        
        except ProcessError as e:
            error_msg = f"Claude Code CLI process error: {e}"
            logger.error(error_msg)
            return error_msg, 1
        
        except CLIJSONDecodeError as e:
            error_msg = f"Claude Code CLI JSON decode error: {e}"
            logger.error(error_msg)
            return error_msg, 1
        
        except asyncio.TimeoutError:
            error_msg = f"Task timeout after {timeout} seconds"
            logger.error(error_msg)
            return error_msg, 1
        
        except Exception as e:
            error_msg = f"Claude Code CLI execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg, 1
    
    async def _execute_direct_cli(
        self,
        prompt: str,
        workspace_path: Path,
        timeout: int,
        env: Optional[Dict[str, str]],
    ) -> Tuple[str, int]:
        """回退到直接 CLI 调用（当 SDK 不可用时）"""
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        
        exec_env["CI"] = "true"
        exec_env["NO_INTERACTIVE"] = "1"
        exec_env["TERM"] = "dumb"
        
        def run_claude_sync():
            try:
                process = subprocess.run(
                    [self.binary_path, "code", "--yes"],
                    input=prompt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(workspace_path),
                    env=exec_env,
                    text=True,
                    timeout=timeout,
                    bufsize=0
                )
                return process.stdout, process.returncode
            except subprocess.TimeoutExpired:
                return f"Task timeout after {timeout} seconds.", 1
            except Exception as e:
                return f"Execution failed: {str(e)}", 1
        
        return await asyncio.to_thread(run_claude_sync)
    
    # ===================================================================
    # 实时状态跟踪方法（参考主项目实现）
    # ===================================================================
    
    def _live_update(
        self,
        task_id: str,
        *,
        phase: str,
        prompt: Optional[str] = None,
        answer: Optional[str] = None,
        status: str = "running",
    ) -> None:
        """发布实时状态更新（如果 tracker 可用）"""
        if not self.live_status_tracker:
            return
        
        context = self._live_context.get(task_id, {})
        try:
            entry = LiveStatusEntry(
                task_id=task_id,
                description=context.get("description", ""),
                project_name=context.get("project_name"),
                phase=phase,
                prompt_preview=prompt[:500] if prompt else "",
                answer_preview=answer[:500] if answer else "",
                status=status,
            )
            self.live_status_tracker.update(entry)
        except Exception as exc:
            logger.debug(f"Live status update failed for task {task_id}: {exc}")
    
    def _live_clear(self, task_id: str) -> None:
        """移除任务的实时状态跟踪"""
        if not self.live_status_tracker:
            return
        try:
            self.live_status_tracker.clear(task_id)
        except Exception as exc:
            logger.debug(f"Live status clear failed for task {task_id}: {exc}")
    
    # ===================================================================
    # 多阶段工作流方法（参考主项目实现）
    # ===================================================================
    
    async def execute_with_multi_agent(
        self,
        task_id: str,
        description: str,
        workspace_path: Path,
        project_name: Optional[str] = None,
        timeout: int = 840,
        env: Optional[Dict[str, str]] = None,
        planner_max_turns: int = 10,
        worker_max_turns: int = 30,
        evaluator_max_turns: int = 10,
        enable_planner: bool = True,
        enable_worker: bool = True,
        enable_evaluator: bool = True,
    ) -> Tuple[str, Set[str], List[str], int, Dict[str, Any], Optional[str]]:
        """执行多阶段工作流（Planner -> Worker -> Evaluator）
        
        Args:
            task_id: 任务 ID（字符串）
            description: 任务描述
            workspace_path: 工作目录路径
            project_name: 项目名称（可选）
            timeout: 超时时间（秒）
            env: 环境变量字典
            planner_max_turns: Planner 阶段最大轮次
            worker_max_turns: Worker 阶段最大轮次
            evaluator_max_turns: Evaluator 阶段最大轮次
            enable_planner: 是否启用 Planner 阶段
            enable_worker: 是否启用 Worker 阶段
            enable_evaluator: 是否启用 Evaluator 阶段
        
        Returns:
            Tuple of (output_text, files_modified, commands_executed, exit_code, usage_metrics, eval_status)
        """
        if not self.sdk_available:
            logger.warning("Multi-agent workflow requires SDK, falling back to simple execution")
            stdout, exit_code = await self._execute_direct_cli(description, workspace_path, timeout, env)
            return stdout, set(), [], exit_code, {}, None
        
        # 初始化实时状态上下文
        self._live_context[task_id] = {
            "description": description,
            "project_name": project_name,
        }
        
        # 确保工作目录存在
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化指标
        combined_metrics = {
            "total_cost_usd": 0.0,
            "duration_ms": 0,
            "duration_api_ms": 0,
            "num_turns": 0,
            "planner_cost_usd": None,
            "planner_duration_ms": None,
            "planner_turns": None,
            "worker_cost_usd": None,
            "worker_duration_ms": None,
            "worker_turns": None,
            "evaluator_cost_usd": None,
            "evaluator_duration_ms": None,
            "evaluator_turns": None,
        }
        
        all_output_parts = []
        all_files_modified: Set[str] = set()
        all_commands_executed: List[str] = []
        final_exit_code = 0
        eval_status: Optional[str] = None
        
        try:
            # 确保 README 存在
            self._ensure_readme_exists(workspace_path, task_id, description, project_name)
            
            # 读取工作区上下文
            workspace_context = self._read_workspace_context(workspace_path)
            
            # 阶段 1: Planner
            plan_text = ""
            if enable_planner:
                self._live_update(task_id, phase="planner", prompt=description, answer="", status="running")
                try:
                    plan_text, planner_metrics = await self._execute_planner_phase(
                        task_id=task_id,
                        workspace=workspace_path,
                        description=description,
                        context=workspace_context,
                        config_max_turns=planner_max_turns,
                        env=env,
                    )
                    all_output_parts.append(f"## Planner Output\n{plan_text}")
                    
                    # 更新指标
                    combined_metrics["planner_cost_usd"] = planner_metrics.get("planner_cost_usd")
                    combined_metrics["planner_duration_ms"] = planner_metrics.get("planner_duration_ms")
                    combined_metrics["planner_turns"] = planner_metrics.get("planner_turns")
                    if planner_metrics.get("planner_cost_usd"):
                        combined_metrics["total_cost_usd"] += planner_metrics["planner_cost_usd"]
                    if planner_metrics.get("planner_duration_ms"):
                        combined_metrics["duration_api_ms"] += planner_metrics["planner_duration_ms"]
                    if planner_metrics.get("planner_turns"):
                        combined_metrics["num_turns"] += planner_metrics["planner_turns"]
                    
                    # 更新 README
                    self._update_readme_with_plan(workspace_path, plan_text)
                except Exception as e:
                    logger.error(f"Planner phase failed: {e}")
                    plan_text = f"[Planner phase failed: {str(e)}]"
                    final_exit_code = 1
            else:
                plan_text = "[Planner phase disabled]"
            
            # 阶段 2: Worker
            if enable_worker and final_exit_code == 0:
                self._live_update(task_id, phase="worker", prompt=description, answer="", status="running")
                try:
                    worker_output, files_modified, commands_executed, exit_code, worker_metrics = await self._execute_worker_phase(
                        task_id=task_id,
                        workspace=workspace_path,
                        description=description,
                        plan_text=plan_text,
                        config_max_turns=worker_max_turns,
                        env=env,
                    )
                    all_output_parts.append(f"## Worker Output\n{worker_output}")
                    all_files_modified = files_modified
                    all_commands_executed = commands_executed
                    final_exit_code = exit_code
                    
                    # 更新指标
                    combined_metrics["worker_cost_usd"] = worker_metrics.get("worker_cost_usd")
                    combined_metrics["worker_duration_ms"] = worker_metrics.get("worker_duration_ms")
                    combined_metrics["worker_turns"] = worker_metrics.get("worker_turns")
                    if worker_metrics.get("worker_cost_usd"):
                        combined_metrics["total_cost_usd"] += worker_metrics["worker_cost_usd"]
                    if worker_metrics.get("worker_duration_ms"):
                        combined_metrics["duration_api_ms"] += worker_metrics["worker_duration_ms"]
                    if worker_metrics.get("worker_turns"):
                        combined_metrics["num_turns"] += worker_metrics["worker_turns"]
                except Exception as e:
                    logger.error(f"Worker phase failed: {e}")
                    all_output_parts.append(f"## Worker Output\n[Worker phase failed: {str(e)}]")
                    final_exit_code = 1
            else:
                all_output_parts.append("## Worker Output\n[Worker phase disabled or skipped]")
            
            # 阶段 3: Evaluator
            if enable_evaluator:
                self._live_update(task_id, phase="evaluator", prompt=description, answer="", status="running")
                try:
                    evaluation_summary, eval_status, eval_outstanding, eval_recommendations, evaluator_metrics = await self._execute_evaluator_phase(
                        task_id=task_id,
                        workspace=workspace_path,
                        description=description,
                        plan_text=plan_text,
                        worker_output="\n".join(all_output_parts),
                        files_modified=all_files_modified,
                        commands_executed=all_commands_executed,
                        config_max_turns=evaluator_max_turns,
                        env=env,
                    )
                    all_output_parts.append(f"## Evaluator Output\n{evaluation_summary}")
                    
                    # 更新 README
                    if eval_status:
                        self._update_readme_with_evaluation(
                            workspace=workspace_path,
                            status=eval_status,
                            outstanding_items=eval_outstanding,
                            recommendations=eval_recommendations,
                        )
                    
                    # 更新指标
                    combined_metrics["evaluator_cost_usd"] = evaluator_metrics.get("evaluator_cost_usd")
                    combined_metrics["evaluator_duration_ms"] = evaluator_metrics.get("evaluator_duration_ms")
                    combined_metrics["evaluator_turns"] = evaluator_metrics.get("evaluator_turns")
                    if evaluator_metrics.get("evaluator_cost_usd"):
                        combined_metrics["total_cost_usd"] += evaluator_metrics["evaluator_cost_usd"]
                    if evaluator_metrics.get("evaluator_duration_ms"):
                        combined_metrics["duration_api_ms"] += evaluator_metrics["evaluator_duration_ms"]
                    if evaluator_metrics.get("evaluator_turns"):
                        combined_metrics["num_turns"] += evaluator_metrics["evaluator_turns"]
                except Exception as e:
                    logger.error(f"Evaluator phase failed: {e}")
                    all_output_parts.append(f"## Evaluator Output\n[Evaluator phase failed: {str(e)}]")
                    eval_status = "FAILED"
                    final_exit_code = 1
            else:
                all_output_parts.append("## Evaluator Output\n[Evaluator phase disabled]")
            
            # 合并输出
            output_text = "\n".join(all_output_parts)
            
            # 更新最终状态
            self._live_update(
                task_id,
                phase="completed",
                prompt=description,
                answer=all_output_parts[-1] if all_output_parts else "",
                status="completed" if final_exit_code == 0 else "error",
            )
            
            return output_text, all_files_modified, all_commands_executed, final_exit_code, combined_metrics, eval_status
            
        except Exception as e:
            logger.error(f"Multi-agent workflow failed: {e}", exc_info=True)
            self._live_update(task_id, phase="error", prompt=description, answer=str(e), status="error")
            raise
        finally:
            self._live_context.pop(task_id, None)
    
    # ===================================================================
    # 辅助方法（参考主项目实现）
    # ===================================================================
    
    def _ensure_readme_exists(
        self,
        workspace: Path,
        task_id: str,
        task_description: str,
        project_name: Optional[str] = None,
    ) -> Path:
        """确保 README.md 存在"""
        readme_path = workspace / "README.md"
        if readme_path.exists():
            return readme_path
        
        try:
            template = self._get_readme_template()
            content = template.format(
                TASK_ID=task_id,
                TASK_TITLE=task_description[:50],
                TASK_DESCRIPTION=task_description,
                PROJECT_NAME=project_name or "None",
                CREATED_AT=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            )
            readme_path.write_text(content)
            logger.debug(f"Created README at {readme_path}")
        except Exception as e:
            logger.warning(f"Failed to create README: {e}")
        
        return readme_path
    
    def _get_readme_template(self) -> str:
        """获取 README 模板"""
        return """# Task Workspace

Task #{TASK_ID}: {TASK_TITLE}

## Summary
- Project: {PROJECT_NAME}
- Created: {CREATED_AT}

## Description
{TASK_DESCRIPTION}

## Plan & Analysis
(Generated by planner agent)

## TODO List
(Updated by worker agent)

## Status: PENDING

## Outstanding Items
(Updated by evaluator)

## Recommendations
(Updated by evaluator)

## Execution Summary
"""
    
    def _read_workspace_context(self, workspace: Path) -> str:
        """读取工作区上下文（README、文件列表）"""
        context_parts = []
        
        # 读取 README
        readme_path = workspace / "README.md"
        if readme_path.exists():
            try:
                context_parts.append("## Project README\n" + readme_path.read_text())
            except Exception as e:
                logger.warning(f"Failed to read README: {e}")
        
        # 列出文件
        try:
            items = list(workspace.iterdir())
            file_list = [item.name for item in items if item.name not in {".git", ".gitignore", "__pycache__"}]
            if file_list:
                context_parts.append(f"\n## Workspace Contents\n- " + "\n- ".join(sorted(file_list)))
        except Exception as e:
            logger.warning(f"Failed to list workspace: {e}")
        
        return "\n".join(context_parts) if context_parts else "Empty workspace"
    
    def _update_readme_with_plan(self, workspace: Path, plan_content: str) -> None:
        """更新 README 的计划部分"""
        readme_path = workspace / "README.md"
        if not readme_path.exists():
            return
        
        try:
            content = readme_path.read_text()
            content = re.sub(
                r'## Plan & Analysis\n\(Generated by planner agent\)',
                f'## Plan & Analysis\n{plan_content}',
                content
            )
            readme_path.write_text(content)
        except Exception as e:
            logger.warning(f"Failed to update README with plan: {e}")
    
    def _update_readme_with_evaluation(
        self,
        workspace: Path,
        status: str,
        outstanding_items: List[str],
        recommendations: List[str],
    ) -> None:
        """更新 README 的评估结果"""
        readme_path = workspace / "README.md"
        if not readme_path.exists():
            return
        
        try:
            content = readme_path.read_text()
            
            # 更新状态
            content = re.sub(r'## Status: \w+', f'## Status: {status}', content)
            
            # 更新待办事项
            if outstanding_items:
                items_text = '\n'.join(outstanding_items)
                content = re.sub(
                    r'## Outstanding Items\n(.*?)(?=##)',
                    f'## Outstanding Items\n{items_text}\n\n',
                    content,
                    flags=re.DOTALL
                )
            
            # 更新建议
            if recommendations:
                rec_text = '\n'.join(recommendations)
                content = re.sub(
                    r'## Recommendations\n(.*?)(?=##)',
                    f'## Recommendations\n{rec_text}\n\n',
                    content,
                    flags=re.DOTALL
                )
            
            readme_path.write_text(content)
        except Exception as e:
            logger.warning(f"Failed to update README with evaluation: {e}")
    
    def _get_workspace_files(self, workspace: Path) -> Set[str]:
        """获取工作区文件列表（排除元数据）"""
        files = set()
        exclude_patterns = {".git", ".gitignore", "__pycache__", ".DS_Store", "node_modules"}
        
        try:
            for path in workspace.rglob("*"):
                if path.is_file():
                    relative_path = path.relative_to(workspace)
                    parts = set(relative_path.parts)
                    
                    should_exclude = False
                    for pattern in exclude_patterns:
                        if pattern in parts or relative_path.name == pattern:
                            should_exclude = True
                            break
                        if any(part.startswith(".git") for part in parts):
                            should_exclude = True
                            break
                    
                    if not should_exclude:
                        files.add(str(relative_path))
        except Exception as e:
            logger.warning(f"Failed to scan workspace: {e}")
        
        return files
    
    async def _execute_planner_phase(
        self,
        task_id: str,
        workspace: Path,
        description: str,
        context: str,
        config_max_turns: int = 10,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """执行 Planner 阶段"""
        planner_prompt = f"""You are a planning expert. Analyze the task and workspace context, then create a structured plan.

## Task
{description}

## Workspace Context
{context}

## Your Task
1. Analyze the task requirements and workspace
2. Identify what needs to be done
3. Create a detailed TODO list with specific, actionable items
4. Note any dependencies between tasks
5. Estimate effort level for each TODO item

Output should be:
- Executive summary (2-3 sentences)
- Analysis of the task
- Structured TODO list (numbered, with clear descriptions)
- Notes on approach and strategy
- Any assumptions or potential blockers
"""
        
        prompt_preview = " ".join(planner_prompt.split())
        usage_metrics = {
            "planner_cost_usd": None,
            "planner_duration_ms": None,
            "planner_turns": None,
        }
        
        try:
            output_parts = []
            start_time = time.time()
            
            # 准备环境变量
            exec_env = os.environ.copy()
            if env:
                exec_env.update(env)
            
            options = ClaudeAgentOptions(
                cwd=str(workspace),
                allowed_tools=["Read", "Glob", "Grep"],
                permission_mode="acceptEdits",
                max_turns=config_max_turns,
                model=self.model,
            )
            
            async for message in query(prompt=planner_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text = block.text.strip()
                            if text:
                                output_parts.append(text)
                                self._live_update(
                                    task_id,
                                    phase="planner",
                                    prompt=prompt_preview,
                                    answer=text,
                                    status="running",
                                )
                
                elif isinstance(message, ResultMessage):
                    usage_metrics["planner_cost_usd"] = message.total_cost_usd
                    usage_metrics["planner_duration_ms"] = message.duration_ms
                    usage_metrics["planner_turns"] = message.num_turns
            
            plan_text = "\n".join(output_parts)
            
            self._live_update(
                task_id,
                phase="planner",
                prompt=prompt_preview,
                answer=plan_text,
                status="completed",
            )
            
            return plan_text, usage_metrics
            
        except Exception as e:
            logger.error(f"Planner phase failed: {e}")
            raise
    
    async def _execute_worker_phase(
        self,
        task_id: str,
        workspace: Path,
        description: str,
        plan_text: str,
        config_max_turns: int = 30,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Set[str], List[str], int, Dict[str, Any]]:
        """执行 Worker 阶段"""
        worker_prompt = f"""You are an expert developer/engineer. Execute the plan below to complete the task.

## Task
{description}

## Plan to Execute
{plan_text}

## Instructions
1. Execute the TODO items from the plan
2. Use TodoWrite to track progress on each item
3. Make changes using available tools (Read, Write, Edit, Bash)
4. Test your changes as needed
5. Provide a summary of what you completed

Please work through the plan systematically and update TodoWrite as you complete each item.
"""
        
        prompt_preview = " ".join(worker_prompt.split())
        files_modified: Set[str] = set()
        commands_executed: List[str] = []
        output_parts = []
        success = True
        usage_metrics = {
            "worker_cost_usd": None,
            "worker_duration_ms": None,
            "worker_turns": None,
        }
        tool_usage_counts: OrderedDict[str, int] = OrderedDict()
        
        try:
            files_before = self._get_workspace_files(workspace)
            start_time = time.time()
            
            # 准备环境变量
            exec_env = os.environ.copy()
            if env:
                exec_env.update(env)
            
            options = ClaudeAgentOptions(
                cwd=str(workspace),
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "TodoWrite"],
                permission_mode="acceptEdits",
                max_turns=config_max_turns,
                model=self.model,
            )
            
            async for message in query(prompt=worker_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text = block.text.strip()
                            if text:
                                output_parts.append(text)
                                self._live_update(
                                    task_id,
                                    phase="worker",
                                    prompt=prompt_preview,
                                    answer=text,
                                    status="running",
                                )
                        
                        elif isinstance(block, ToolUseBlock):
                            tool_name = block.name
                            tool_usage_counts.setdefault(tool_name, 0)
                            tool_usage_counts[tool_name] += 1
                            
                            if tool_name in ["Write", "Edit"]:
                                file_path = block.input.get("file_path", "")
                                if file_path:
                                    files_modified.add(file_path)
                            
                            elif tool_name == "Bash":
                                command = block.input.get("command", "")
                                if command:
                                    commands_executed.append(command)
                                self._live_update(
                                    task_id,
                                    phase="worker",
                                    prompt=prompt_preview,
                                    answer=f"[Bash] {command}",
                                    status="running",
                                )
                
                elif isinstance(message, ResultMessage):
                    success = not message.is_error
                    if message.result:
                        output_parts.append(f"\n[Result: {message.result}]")
                    
                    usage_metrics["worker_cost_usd"] = message.total_cost_usd
                    usage_metrics["worker_duration_ms"] = message.duration_ms
                    usage_metrics["worker_turns"] = message.num_turns
            
            output_text = "\n".join(output_parts)
            files_after = self._get_workspace_files(workspace)
            new_files = files_after - files_before
            all_modified_files = files_modified.union(new_files)
            
            exit_code = 0 if success else 1
            
            self._live_update(
                task_id,
                phase="worker",
                prompt=prompt_preview,
                answer=output_text,
                status="completed" if exit_code == 0 else "error",
            )
            
            return output_text, all_modified_files, commands_executed, exit_code, usage_metrics
            
        except Exception as e:
            logger.error(f"Worker phase failed: {e}")
            raise
    
    async def _execute_evaluator_phase(
        self,
        task_id: str,
        workspace: Path,
        description: str,
        plan_text: str,
        worker_output: str,
        files_modified: Set[str],
        commands_executed: List[str],
        config_max_turns: int = 10,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str, List[str], List[str], Dict[str, Any]]:
        """执行 Evaluator 阶段"""
        evaluator_prompt = f"""You are a quality assurance expert. Evaluate whether the task was completed successfully.

## Task
{description}

## Original Plan
{plan_text}

## Worker Output
{worker_output}

## Changes Made
- Files Modified: {len(files_modified)}
- Commands Executed: {len(commands_executed)}

## Your Task
1. Review the worker output against the original plan
2. Verify each TODO item was addressed
3. Check if the task objectives were met
4. Identify any incomplete items or issues
5. Provide a comprehensive evaluation summary

Output should include:
- Completion status (COMPLETE / INCOMPLETE / PARTIAL)
- Items successfully completed
- Any outstanding items
- Quality assessment
- Recommendations (if any)
"""
        
        usage_metrics = {
            "evaluator_cost_usd": None,
            "evaluator_duration_ms": None,
            "evaluator_turns": None,
        }
        
        try:
            output_parts = []
            prompt_preview = " ".join(evaluator_prompt.split())
            
            # 准备环境变量
            exec_env = os.environ.copy()
            if env:
                exec_env.update(env)
            
            options = ClaudeAgentOptions(
                cwd=str(workspace),
                allowed_tools=["Read", "Glob"],
                permission_mode="acceptEdits",
                max_turns=config_max_turns,
                model=self.model,
            )
            
            async for message in query(prompt=evaluator_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text = block.text.strip()
                            if text:
                                output_parts.append(text)
                                self._live_update(
                                    task_id,
                                    phase="evaluator",
                                    prompt=prompt_preview,
                                    answer=text,
                                    status="running",
                                )
                
                elif isinstance(message, ResultMessage):
                    usage_metrics["evaluator_cost_usd"] = message.total_cost_usd
                    usage_metrics["evaluator_duration_ms"] = message.duration_ms
                    usage_metrics["evaluator_turns"] = message.num_turns
            
            evaluation_text = "\n".join(output_parts)
            
            self._live_update(
                task_id,
                phase="evaluator",
                prompt=prompt_preview,
                answer=evaluation_text,
                status="completed",
            )
            
            # 提取评估状态、待办事项和建议
            status = self._extract_status_from_evaluation(evaluation_text)
            outstanding_items = self._extract_outstanding_items(evaluation_text)
            recommendations = self._extract_recommendations(evaluation_text)
            
            return evaluation_text, status, outstanding_items, recommendations, usage_metrics
            
        except Exception as e:
            logger.error(f"Evaluator phase failed: {e}")
            raise
    
    def _extract_status_from_evaluation(self, evaluation_text: str) -> str:
        """从评估文本中提取完成状态"""
        text_lower = evaluation_text.lower()
        
        if "complete" in text_lower and "partial" not in text_lower:
            return "COMPLETE"
        elif "partial" in text_lower:
            return "PARTIAL"
        elif "incomplete" in text_lower or "not completed" in text_lower:
            return "INCOMPLETE"
        elif "failed" in text_lower or "error" in text_lower:
            return "FAILED"
        else:
            return "PARTIAL"
    
    def _extract_outstanding_items(self, evaluation_text: str) -> List[str]:
        """从评估文本中提取待办事项"""
        items = []
        lines = evaluation_text.split('\n')
        in_outstanding = False
        
        for line in lines:
            if re.search(r'outstanding|incomplete|todo', line, re.IGNORECASE):
                in_outstanding = True
                continue
            
            if in_outstanding:
                if re.match(r'^\s*[-*❌✓]\s+', line) or re.match(r'^\s*\[\s*[x\s]\s*\]\s+', line):
                    items.append(line.strip())
                elif line.strip() == '':
                    in_outstanding = False
        
        return items
    
    def _extract_recommendations(self, evaluation_text: str) -> List[str]:
        """从评估文本中提取建议"""
        items = []
        lines = evaluation_text.split('\n')
        in_recommendations = False
        
        for line in lines:
            if re.search(r'recommendation', line, re.IGNORECASE):
                in_recommendations = True
                continue
            
            if in_recommendations:
                if re.match(r'^\s*[-*]\s+', line):
                    items.append(line.strip())
                elif line.strip() == '' or re.match(r'^##', line):
                    in_recommendations = False
        
        return items


class CursorExecutor(Executor):
    """Cursor CLI 执行器（如果支持）"""
    
    def __init__(self, binary_path: str = "cursor"):
        self.binary_path = binary_path
    
    def get_name(self) -> str:
        return "cursor"
    
    def is_available(self) -> bool:
        """检查 Cursor CLI 是否可用"""
        try:
            result = subprocess.run(
                [self.binary_path, "--version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.debug(f"Cursor CLI verified: {self.binary_path}")
                return True
            else:
                logger.warning(f"Cursor CLI version check failed: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.debug(f"Cursor CLI not found: {self.binary_path}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Cursor CLI version check timeout")
            return False
        except Exception as e:
            logger.warning(f"Cursor CLI availability check failed: {e}")
            return False
    
    async def execute(
        self,
        prompt: str,
        workspace_path: Path,
        timeout: int = 840,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, int]:
        """执行 Cursor CLI"""
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        
        # 强制非交互模式
        exec_env["CI"] = "true"
        exec_env["NO_INTERACTIVE"] = "1"
        exec_env["TERM"] = "dumb"
        
        def run_cursor_sync():
            """同步执行 Cursor CLI"""
            # 注意：Cursor CLI 的实际命令可能不同，需要根据实际 API 调整
            process = subprocess.run(
                [self.binary_path, "code", "--yes"],  # 假设命令类似
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(workspace_path),
                env=exec_env,
                text=True,
                timeout=timeout,
                bufsize=0
            )
            return process.stdout, process.returncode
        
        stdout, exit_code = await asyncio.to_thread(run_cursor_sync)
        return stdout, exit_code


class CustomCommandExecutor(Executor):
    """自定义命令执行器（支持任意命令行工具）"""
    
    def __init__(
        self,
        command: list[str],
        name: str = "custom",
        check_available_command: Optional[list[str]] = None,
    ):
        """
        Args:
            command: 执行命令（列表形式，如 ["python", "script.py"]）
            name: 执行器名称
            check_available_command: 检查可用性的命令（如 ["python", "--version"]）
        """
        self.command = command
        self.name = name
        self.check_available_command = check_available_command or command[:1] + ["--version"]
    
    def get_name(self) -> str:
        return self.name
    
    def is_available(self) -> bool:
        """检查自定义命令是否可用"""
        try:
            result = subprocess.run(
                self.check_available_command,
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.debug(f"Custom command verified: {self.check_available_command}")
                return True
            else:
                logger.warning(f"Custom command check failed: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.debug(f"Custom command not found: {self.check_available_command[0]}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Custom command check timeout")
            return False
        except Exception as e:
            logger.warning(f"Custom command availability check failed: {e}")
            return False
    
    async def execute(
        self,
        prompt: str,
        workspace_path: Path,
        timeout: int = 840,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, int]:
        """执行自定义命令"""
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        
        # 将 prompt 作为环境变量或标准输入传递
        exec_env["PROMPT"] = prompt
        
        def run_custom_sync():
            """同步执行自定义命令"""
            process = subprocess.run(
                self.command,
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(workspace_path),
                env=exec_env,
                text=True,
                timeout=timeout,
                bufsize=0
            )
            return process.stdout, process.returncode
        
        stdout, exit_code = await asyncio.to_thread(run_custom_sync)
        return stdout, exit_code


class ExecutorFactory:
    """执行器工厂类，根据配置创建执行器"""
    
    # 内置执行器映射
    _builtin_executors = {
        "claude-code": ClaudeCodeExecutor,
        "claude": ClaudeCodeExecutor,  # 别名
        "cursor": CursorExecutor,
    }
    
    @classmethod
    def _create_claude_executor(cls, config: Dict[str, Any]) -> ClaudeCodeExecutor:
        """创建 Claude Code 执行器（支持 model 配置）"""
        binary_path = config.get("binary_path", "claude")
        model = config.get("model")  # 支持从配置指定模型
        return ClaudeCodeExecutor(binary_path=binary_path, model=model)
    
    @classmethod
    def create(
        cls,
        executor_type: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Executor:
        """创建执行器
        
        Args:
            executor_type: 执行器类型（"claude-code", "cursor", "custom" 或自定义命令）
            config: 配置字典，可能包含：
                - binary_path: 二进制路径
                - command: 自定义命令（列表）
                - name: 执行器名称
                - check_command: 检查命令（列表）
        
        Returns:
            Executor 实例
        """
        config = config or {}
        
        # 检查是否是内置执行器
        if executor_type in cls._builtin_executors:
            executor_class = cls._builtin_executors[executor_type]
            # 特殊处理 Claude Code 执行器（支持 model 配置）
            if executor_type in ["claude-code", "claude"]:
                return cls._create_claude_executor(config)
            else:
                binary_path = config.get("binary_path", executor_type.split("-")[0])
                return executor_class(binary_path=binary_path)
        
        # 自定义命令执行器
        if executor_type == "custom" or executor_type.startswith("cmd:"):
            # 从 executor_type 解析命令，如 "cmd:python:script.py"
            if executor_type.startswith("cmd:"):
                command = executor_type[4:].split(":")
            else:
                command = config.get("command")
                if not command:
                    raise ValueError("Custom executor requires 'command' in config")
            
            name = config.get("name", "custom")
            check_command = config.get("check_command")
            return CustomCommandExecutor(
                command=command,
                name=name,
                check_available_command=check_command,
            )
        
        raise ValueError(f"Unknown executor type: {executor_type}")
    
    @classmethod
    def list_available(cls) -> list[str]:
        """列出所有可用的执行器
        
        参考主项目实现，但简化了检查逻辑
        """
        available = []
        checked = set()  # 避免重复检查（claude-code 和 claude 是同一个类）
        
        for executor_type, executor_class in cls._builtin_executors.items():
            # 跳过已检查的类型（claude-code 和 claude 是同一个类）
            if executor_type in checked:
                continue
            
            # 创建临时实例检查可用性
            try:
                if executor_type in ["claude-code", "claude"]:
                    executor = executor_class()
                    checked.add("claude-code")
                    checked.add("claude")
                elif executor_type == "cursor":
                    executor = executor_class()
                    checked.add("cursor")
                else:
                    continue
                
                if executor.is_available():
                    # 如果 claude-code 可用，同时添加 claude 别名
                    if executor_type == "claude-code":
                        available.extend(["claude-code", "claude"])
                    else:
                        available.append(executor_type)
            except Exception as e:
                logger.debug(f"Failed to check executor {executor_type}: {e}")
                continue
        
        return available

