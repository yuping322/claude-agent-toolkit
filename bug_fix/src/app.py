"""FC 单容器应用：任务提交、运行、查询

参考主项目的实现，但针对 FC 环境进行了简化：
- 使用直接 CLI 调用而不是 SDK（适合无状态函数环境）
- 使用本地文件系统（OSS 挂载）而不是 OSS SDK
- 支持多种执行器（claude-code, cursor, custom）
- 支持 Git 集成（克隆、提交、推送、创建 PR）

主要改进：
1. 改进错误处理和日志记录
2. 优化 Git 操作（使用 GitHelper）
3. 改进代码结构和注释
4. 移除冗余的 Git 操作函数，统一使用 GitHelper
"""

import os
import json
import hashlib
import asyncio
import subprocess
import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from executors import ExecutorFactory, Executor, ClaudeCodeExecutor
from .git import GitHelper, extract_github_repo_info

# 导入实时状态跟踪
try:
    from live_status import LiveStatusTracker, LiveStatusEntry
    LIVE_STATUS_AVAILABLE = True
except ImportError:
    LIVE_STATUS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("live_status not available, live status tracking disabled")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# OSS 本地挂载路径
OSS_MOUNT_PATH = os.environ.get('OSS_MOUNT_PATH', '/mnt/oss')
OSS_BASE_PATH = Path(OSS_MOUNT_PATH)

# 确保基础目录存在
OSS_BASE_PATH.mkdir(parents=True, exist_ok=True)
(OSS_BASE_PATH / "status").mkdir(parents=True, exist_ok=True)
(OSS_BASE_PATH / "logs").mkdir(parents=True, exist_ok=True)
(OSS_BASE_PATH / "workspace").mkdir(parents=True, exist_ok=True)
(OSS_BASE_PATH / "repos").mkdir(parents=True, exist_ok=True)  # 共享仓库目录
(OSS_BASE_PATH / "live_status").mkdir(parents=True, exist_ok=True)  # 实时状态目录

# 初始化实时状态跟踪器
live_status_tracker: Optional[LiveStatusTracker] = None
if LIVE_STATUS_AVAILABLE:
    try:
        live_status_path = OSS_BASE_PATH / "live_status" / "live_status.json"
        live_status_tracker = LiveStatusTracker(live_status_path)
        logger.info(f"Live status tracker initialized at {live_status_path}")
    except Exception as e:
        logger.warning(f"Failed to initialize live status tracker: {e}")
        live_status_tracker = None


class TaskRequest(BaseModel):
    """任务请求模型"""
    project: str = "default"
    model: str = "deepseek-chat"
    prompt: str
    notify_url: Optional[str] = None
    # 执行器配置（可选，默认使用 claude-code）
    executor_type: Optional[str] = None  # 执行器类型：claude-code, cursor, custom, cmd:xxx
    executor_config: Optional[Dict[str, Any]] = None  # 执行器配置（如 binary_path, command 等）
    # Git 配置（可选，如果未提供则从环境变量读取）
    git_repo_url: Optional[str] = None
    git_branch: Optional[str] = None  # 默认分支（通常是 main 或 master）
    git_token: Optional[str] = None  # GitHub token（用于创建 MR）


class TaskResponse(BaseModel):
    """任务响应模型"""
    task_id: str
    status: str
    log_url: Optional[str] = None
    status_url: Optional[str] = None


def generate_task_id(project: str, prompt: str) -> str:
    """生成任务 ID（基于项目 + prompt 的哈希）"""
    content = f"{project}:{prompt}"
    hash_obj = hashlib.md5(content.encode())
    return f"task-{hash_obj.hexdigest()[:16]}"


def task_exists(task_id: str) -> bool:
    """检查任务是否已存在（包括运行中的任务）"""
    status_path = OSS_BASE_PATH / "status" / f"{task_id}.json"
    running_lock_path = OSS_BASE_PATH / "status" / f"{task_id}.running"
    
    # 如果状态文件存在，任务已存在
    if status_path.exists():
        return True
    
    # 如果运行中标记文件存在，任务正在运行
    if running_lock_path.exists():
        return True
    
    return False


def is_task_running(task_id: str) -> bool:
    """检查任务是否正在运行"""
    running_lock_path = OSS_BASE_PATH / "status" / f"{task_id}.running"
    return running_lock_path.exists()


def create_running_lock(task_id: str) -> bool:
    """创建运行中标记文件（原子性操作，防止并发）
    
    使用 O_CREAT | O_EXCL 标志确保原子性创建，如果文件已存在则失败
    这是防止重复任务提交的关键机制
    """
    running_lock_path = OSS_BASE_PATH / "status" / f"{task_id}.running"
    
    # 确保目录存在
    running_lock_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # 使用 O_CREAT | O_EXCL 标志原子性创建文件
        # 如果文件已存在，会抛出 FileExistsError
        lock_fd = os.open(
            str(running_lock_path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644
        )
        
        # 写入锁文件内容
        with os.fdopen(lock_fd, 'w') as f:
            json.dump({
                "task_id": task_id,
                "started_at": datetime.now().isoformat(),
                "pid": os.getpid()
            }, f, indent=2)
        
        logger.debug(f"Created running lock for task {task_id}")
        return True
    except FileExistsError:
        # 文件已存在，说明任务正在运行
        logger.warning(f"Task {task_id} is already running (lock file exists)")
        return False
    except (IOError, OSError) as e:
        # 其他错误
        logger.error(f"Failed to create running lock for {task_id}: {e}")
        return False


def remove_running_lock(task_id: str):
    """移除运行中标记文件"""
    running_lock_path = OSS_BASE_PATH / "status" / f"{task_id}.running"
    try:
        if running_lock_path.exists():
            running_lock_path.unlink()
            logger.debug(f"Removed running lock for task {task_id}")
    except Exception as e:
        logger.warning(f"Failed to remove running lock for {task_id}: {e}")


def create_task_status(task_id: str, project: str, prompt: str, status: str):
    """创建任务状态文件"""
    status_data = {
        "task_id": task_id,
        "project": project,
        "prompt": prompt,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    status_path = OSS_BASE_PATH / "status" / f"{task_id}.json"
    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)


def update_task_status(task_id: str, status: str, exit_code: Optional[int] = None, error: Optional[str] = None):
    """更新任务状态"""
    status_path = OSS_BASE_PATH / "status" / f"{task_id}.json"
    
    # 读取现有状态
    if status_path.exists():
        with open(status_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    else:
        existing = {}
    
    # 更新状态
    existing.update({
        "status": status,
        "updated_at": datetime.now().isoformat(),
    })
    if exit_code is not None:
        existing["exit_code"] = exit_code
    if error:
        existing["error"] = error
    
    # 写入文件
    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


async def run_task(
    task_id: str,
    project: str,
    model: str,
    prompt: str,
    notify_url: Optional[str] = None,
    executor_type: Optional[str] = None,
    executor_config: Optional[Dict[str, Any]] = None,
    git_repo_url: Optional[str] = None,
    git_branch: Optional[str] = None,
    git_token: Optional[str] = None
):
    """运行任务（在后台执行）"""
    # 创建运行中标记文件（防止重复提交）
    if not create_running_lock(task_id):
        logger.warning(f"Task {task_id} is already running, skipping...")
        return
    
    # Git 配置必须从请求参数获取（每个任务可能使用不同的仓库）
    # 环境变量只作为后备（如果请求中未提供）
    repo_url = git_repo_url  # 必须从请求参数获取，不支持环境变量
    branch = git_branch or os.environ.get("GIT_BRANCH", "main")  # 分支可以从环境变量获取
    token = git_token or os.environ.get("GITHUB_TOKEN")  # Token 可以从环境变量获取（用于推送和创建 PR）
    
    try:
        # 使用本地挂载的 OSS 目录作为工作区
        workspace_path = OSS_BASE_PATH / "workspace" / task_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        # 如果有 Git 仓库配置，先拉取最新代码
        if repo_url:
            logger.info(f"Pulling latest code from {repo_url} (branch: {branch})")
            # 使用 GitHelper 进行 Git 操作（参考 src/sleepless_agent/storage/git.py）
            # 使用 worktree 模式：共享仓库 + 工作副本，提高效率
            git_helper = GitHelper(workspace_path)
            # 共享仓库基础路径：/mnt/oss/repos/
            shared_repos_base = OSS_BASE_PATH / "repos"
            if not git_helper.pull_latest(repo_url, branch, token, use_worktree=True, shared_repos_base=shared_repos_base):
                logger.warning(f"Failed to pull latest code, continuing with existing code")
        else:
            logger.info("No Git repository configured, using empty workspace")
        
        # 日志保存在工作区目录
        log_path = workspace_path / "session.log"
        
        # 更新状态为运行中
        update_task_status(task_id, "running")
        
        # 创建执行器
        # 默认使用 claude-code，如果未指定 executor_type
        executor_type = executor_type or os.environ.get("DEFAULT_EXECUTOR", "claude-code")
        executor_config = executor_config or {}
        
        # 如果使用 claude-code，确保环境变量已设置
        if executor_type in ["claude-code", "claude"]:
            if "ANTHROPIC_API_KEY" not in os.environ:
                logger.warning("ANTHROPIC_API_KEY is not set - Claude Code CLI may fail")
            if "ANTHROPIC_BASE_URL" not in os.environ:
                logger.warning("ANTHROPIC_BASE_URL is not set - Claude Code CLI may fail")
        
        try:
            executor = ExecutorFactory.create(executor_type, executor_config)
            
            # 如果是 ClaudeCodeExecutor，传入 live_status_tracker 和启用多阶段工作流
            if isinstance(executor, ClaudeCodeExecutor) and live_status_tracker:
                executor.live_status_tracker = live_status_tracker
                executor.enable_multi_agent = os.environ.get("ENABLE_MULTI_AGENT", "true").lower() == "true"
                logger.info(f"Created executor: {executor.get_name()} (multi-agent: {executor.enable_multi_agent})")
            else:
                logger.info(f"Created executor: {executor.get_name()}")
        except ValueError as e:
            error_msg = f"Invalid executor type '{executor_type}': {e}"
            logger.error(error_msg)
            update_task_status(task_id, "failed", error=error_msg)
            if notify_url:
                await send_notification(task_id, "failed", notify_url, error=error_msg)
            return
        except Exception as e:
            error_msg = f"Failed to create executor '{executor_type}': {e}"
            logger.error(error_msg)
            update_task_status(task_id, "failed", error=error_msg)
            if notify_url:
                await send_notification(task_id, "failed", notify_url, error=error_msg)
            return
        
        # 检查执行器是否可用
        if not executor.is_available():
            error_msg = f"Executor '{executor.get_name()}' is not available (not installed or not in PATH)"
            logger.error(error_msg)
            update_task_status(task_id, "failed", error=error_msg)
            if notify_url:
                await send_notification(task_id, "failed", notify_url, error=error_msg)
            return
        
        logger.info(f"Using executor: {executor.get_name()}")
        
        # 准备环境变量
        env = {}
        # Claude Code CLI 需要的环境变量
        if executor_type in ["claude-code", "claude"]:
            env["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "")
            env["ANTHROPIC_BASE_URL"] = os.environ.get("ANTHROPIC_BASE_URL", "")
        
        # 执行任务
        try:
            # 如果启用多阶段工作流且是 ClaudeCodeExecutor，使用多阶段工作流
            if isinstance(executor, ClaudeCodeExecutor) and executor.enable_multi_agent and executor.live_status_tracker:
                logger.info(f"Using multi-agent workflow for task {task_id}")
                stdout, files_modified, commands_executed, exit_code, usage_metrics, eval_status = await executor.execute_with_multi_agent(
                    task_id=task_id,
                    description=prompt,
                    workspace_path=workspace_path,
                    project_name=project,
                    timeout=840,  # 14 分钟超时（留 1 分钟缓冲）
                    env=env,
                    planner_max_turns=int(os.environ.get("PLANNER_MAX_TURNS", "10")),
                    worker_max_turns=int(os.environ.get("WORKER_MAX_TURNS", "30")),
                    evaluator_max_turns=int(os.environ.get("EVALUATOR_MAX_TURNS", "10")),
                    enable_planner=os.environ.get("ENABLE_PLANNER", "true").lower() == "true",
                    enable_worker=os.environ.get("ENABLE_WORKER", "true").lower() == "true",
                    enable_evaluator=os.environ.get("ENABLE_EVALUATOR", "true").lower() == "true",
                )
                
                # 记录使用指标
                if usage_metrics:
                    logger.info(f"Task {task_id} metrics: cost=${usage_metrics.get('total_cost_usd', 0):.4f}, "
                              f"turns={usage_metrics.get('num_turns', 0)}, "
                              f"duration={usage_metrics.get('duration_api_ms', 0)}ms")
                
                # 记录文件修改和命令执行
                if files_modified:
                    logger.info(f"Task {task_id} modified {len(files_modified)} files: {list(files_modified)[:5]}...")
                if commands_executed:
                    logger.info(f"Task {task_id} executed {len(commands_executed)} commands")
                
                # 记录评估状态
                if eval_status:
                    logger.info(f"Task {task_id} evaluation status: {eval_status}")
            else:
                # 使用简单执行模式
                logger.info(f"Using simple execution mode for task {task_id}")
                stdout, exit_code = await executor.execute(
                    prompt=prompt,
                    workspace_path=workspace_path,
                    timeout=840,  # 14 分钟超时（留 1 分钟缓冲）
                    env=env
                )
                files_modified = set()
                commands_executed = []
                usage_metrics = {}
                eval_status = None
        except subprocess.TimeoutExpired:
            error = f"Task timeout (14 minutes) - {executor.get_name()} may have been waiting for interactive input"
            logger.error(f"Task {task_id} timeout: {error}")
            update_task_status(task_id, "failed", error=error)
            if notify_url:
                await send_notification(task_id, "failed", notify_url, error=error)
            return
        except Exception as e:
            error = f"Executor '{executor.get_name()}' failed: {str(e)}"
            logger.error(f"Task {task_id} execution failed: {error}", exc_info=True)
            update_task_status(task_id, "failed", error=error)
            if notify_url:
                await send_notification(task_id, "failed", notify_url, error=error)
            return
        
        # 保存日志
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(stdout)
        
        # 复制日志到 logs 目录（方便查询）
        log_oss_path = OSS_BASE_PATH / "logs" / task_id / "session.log"
        log_oss_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.exists():
            with open(log_path, 'rb') as src, open(log_oss_path, 'wb') as dst:
                dst.write(src.read())
        
        # 工作区文件已经在 OSS 挂载目录中，无需额外复制
        
        # 更新状态
        status = "completed" if exit_code == 0 else "failed"
        update_task_status(task_id, status, exit_code=exit_code)
        
        # 如果任务成功完成且有 Git 配置，创建 Pull Request
        # 注意：推送和创建 PR 需要 token，但拉取公开仓库不需要
        pr_url = None
        if exit_code == 0 and repo_url:
            if token:
                logger.info("Creating Pull Request...")
                # 使用改进的 GitHelper 进行 PR 创建（参考 src/sleepless_agent/storage/git.py）
                pr_url = create_pull_request_with_helper(
                    workspace_path=workspace_path,
                    task_id=task_id,
                    project=project,
                    prompt=prompt,
                    repo_url=repo_url,
                    branch=branch,
                    token=token
                )
                if pr_url:
                    logger.info(f"Created Pull Request: {pr_url}")
                else:
                    logger.warning("Failed to create Pull Request, but code changes are saved locally")
            else:
                logger.warning("No GitHub token provided, skipping PR creation")
                logger.info("Code changes are saved locally, but not pushed to remote")
        
        # 清理 worktree（如果使用了共享仓库）
        # 注意：不要删除共享仓库本身，只清理工作副本
        # 注意：当前实现使用 GitHelper.pull_latest，它直接克隆到 workspace_path
        # 不使用 worktree，所以这里不需要清理 worktree
        # 如果需要使用 worktree 优化，可以在 GitHelper 中实现
        if repo_url:
            logger.debug(f"Workspace cleanup: {workspace_path} (worktree cleanup not implemented)")
            if pr_url:
                # 更新状态，添加 PR URL
                status_data = {
                    "status": status,
                    "exit_code": exit_code,
                    "pr_url": pr_url,
                    "updated_at": datetime.now().isoformat()
                }
                status_path = OSS_BASE_PATH / "status" / f"{task_id}.json"
                if status_path.exists():
                    with open(status_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    existing.update(status_data)
                    with open(status_path, 'w', encoding='utf-8') as f:
                        json.dump(existing, f, ensure_ascii=False, indent=2)
        
        # 发送通知
        if notify_url:
            await send_notification(
                task_id,
                status,
                notify_url,
                exit_code=exit_code,
                pr_url=pr_url
            )
        
    except Exception as e:
        update_task_status(task_id, "failed", error=str(e))
        if notify_url:
            await send_notification(task_id, "failed", notify_url, error=str(e))
    finally:
        # 无论成功还是失败，都要移除运行中标记
        remove_running_lock(task_id)


async def send_notification(
    task_id: str,
    status: str,
    notify_url: str,
    exit_code: Optional[int] = None,
    error: Optional[str] = None,
    pr_url: Optional[str] = None
):
    """发送通知（支持钉钉 Webhook 等）"""
    import aiohttp
    
    message = f"任务 {task_id} 状态: {status}"
    if exit_code is not None:
        message += f"\n退出码: {exit_code}"
    if error:
        message += f"\n错误: {error}"
    if pr_url:
        message += f"\nPull Request: {pr_url}"
    
    # 日志路径（本地挂载）
    log_path = OSS_BASE_PATH / "logs" / task_id / "session.log"
    message += f"\n日志路径: {log_path}"
    
    payload = {
        "msgtype": "text",
        "text": {"content": message}
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(notify_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    logger.debug(f"Notification sent successfully for task {task_id}")
                else:
                    logger.warning(f"Notification failed with status {response.status} for task {task_id}")
                await response.read()
    except asyncio.TimeoutError:
        logger.warning(f"Notification timeout for task {task_id}")
    except Exception as e:
        logger.error(f"Failed to send notification for task {task_id}: {e}")


# 全局任务字典，用于跟踪正在运行的任务（实例级别，不跨实例共享）
# 注意：在 FC 中，每个函数实例是独立的，这个字典只在当前实例内有效
# 任务状态通过 OSS 文件系统持久化，确保无状态执行
_running_tasks: dict[str, asyncio.Task] = {}


@app.post("/run", response_model=TaskResponse)
async def submit_and_run_task(request: TaskRequest):
    """提交任务并运行
    
    并发模型：
    - 每个 HTTP 请求会创建一个独立的 FC 函数实例（如果当前实例忙碌）
    - 每个实例是独立的、无状态的，使用 OSS 共享存储
    - 任务状态通过 OSS 文件系统持久化，确保跨实例查询
    - 即使函数实例被回收，任务状态和日志仍然保存在 OSS 中
    
    无状态执行：
    - 每次运行都是独立的，不依赖之前的执行状态
    - 任务隔离：每个任务有独立的工作区（/mnt/oss/workspace/{task_id}）
    - 状态持久化：任务状态和日志保存在 OSS 中，可以跨实例查询
    
    注意：在 FC 环境中，使用 asyncio.create_task 确保任务在同一个事件循环中运行
    这样可以确保即使 HTTP 请求返回，任务也能继续执行（直到 FC 函数 timeout）
    """
    
    # 生成任务 ID
    task_id = generate_task_id(request.project, request.prompt)
    
    # 检查唯一性（包括运行中的任务）
    if task_exists(task_id):
        # 检查是否是运行中
        if is_task_running(task_id):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Task is already running",
                    "task_id": task_id,
                    "status": "running",
                    "status_path": str(OSS_BASE_PATH / "status" / f"{task_id}.json")
                }
            )
        else:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Task already exists",
                    "task_id": task_id,
                    "status_path": str(OSS_BASE_PATH / "status" / f"{task_id}.json")
                }
            )
    
    # 创建任务状态
    create_task_status(task_id, request.project, request.prompt, "pending")
    
    # 使用 asyncio.create_task 在后台运行任务
    # 这样可以确保任务在同一个事件循环中运行，即使 HTTP 请求返回也能继续
    # 注意：FC 函数的 timeout 是 900 秒（15 分钟），任务必须在此时限内完成
    task = asyncio.create_task(
        run_task(
            task_id=task_id,
            project=request.project,
            model=request.model,
            prompt=request.prompt,
            notify_url=request.notify_url,
            executor_type=request.executor_type,
            executor_config=request.executor_config,
            git_repo_url=request.git_repo_url,
            git_branch=request.git_branch,
            git_token=request.git_token
        )
    )
    
    # 添加到运行任务字典
    _running_tasks[task_id] = task
    
    # 添加完成回调，清理任务
    def cleanup_task(t):
        _running_tasks.pop(task_id, None)
    
    task.add_done_callback(cleanup_task)
    
    log_path = str(OSS_BASE_PATH / "logs" / task_id / "session.log")
    status_path = str(OSS_BASE_PATH / "status" / f"{task_id}.json")
    
    return TaskResponse(
        task_id=task_id,
        status="running",
        log_url=log_path,
        status_url=status_path
    )


@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    status_path = OSS_BASE_PATH / "status" / f"{task_id}.json"
    
    if not status_path.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    
    with open(status_path, 'r', encoding='utf-8') as f:
        status_data = json.load(f)
    
    return status_data


@app.get("/logs/{task_id}")
async def get_task_logs(task_id: str, lines: Optional[int] = None):
    """获取任务日志"""
    log_path = OSS_BASE_PATH / "logs" / task_id / "session.log"
    
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Logs not found")
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        log_content = f.read()
    
    # 如果指定了行数，返回最后 N 行
    if lines:
        log_lines = log_content.split('\n')
        log_content = '\n'.join(log_lines[-lines:])
    
    return {
        "task_id": task_id,
        "logs": log_content,
        "total_lines": len(log_content.split('\n'))
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    available_executors = ExecutorFactory.list_available()
    return {
        "status": "healthy",
        "oss_mount_path": str(OSS_BASE_PATH),
        "oss_mounted": OSS_BASE_PATH.exists(),
        "available_executors": available_executors,
        "default_executor": os.environ.get("DEFAULT_EXECUTOR", "claude-code"),
        "running_tasks": len(_running_tasks)
    }


@app.get("/tasks")
async def list_running_tasks():
    """列出正在运行的任务"""
    tasks_info = []
    for task_id, task in _running_tasks.items():
        tasks_info.append({
            "task_id": task_id,
            "status": "running" if not task.done() else ("completed" if task.exception() is None else "failed"),
            "done": task.done(),
            "cancelled": task.cancelled()
        })
    return {
        "total": len(tasks_info),
        "tasks": tasks_info
    }


@app.get("/live_status/{task_id}")
async def get_live_status(task_id: str):
    """获取任务的实时状态"""
    if not live_status_tracker:
        raise HTTPException(status_code=503, detail="Live status tracking not available")
    
    try:
        entry = live_status_tracker.get_entry(task_id)
        if entry:
            return entry.to_dict()
        else:
            raise HTTPException(status_code=404, detail="Live status not found")
    except Exception as e:
        logger.error(f"Failed to get live status for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get live status: {str(e)}")


@app.get("/live_status")
async def list_live_status(limit: Optional[int] = 10):
    """列出所有任务的实时状态"""
    if not live_status_tracker:
        raise HTTPException(status_code=503, detail="Live status tracking not available")
    
    try:
        entries = live_status_tracker.entries()
        # 限制返回数量
        if limit:
            entries = entries[:limit]
        return {
            "total": len(entries),
            "entries": [entry.to_dict() for entry in entries]
        }
    except Exception as e:
        logger.error(f"Failed to list live status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list live status: {str(e)}")




def get_repo_hash(repo_url: str) -> str:
    """生成仓库的唯一哈希（用于共享仓库路径）
    
    注意：当前实现不使用 worktree，此函数保留用于未来优化
    """
    import hashlib
    # 移除可能的 token 和协议差异，生成一致的哈希
    normalized_url = repo_url
    if "@" in normalized_url:
        # 移除 token
        normalized_url = re.sub(r'://[^@]+@', '://', normalized_url)
    normalized_url = normalized_url.replace("git@", "").replace("https://", "").replace("http://", "").replace(".git", "")
    hash_obj = hashlib.md5(normalized_url.encode())
    return hash_obj.hexdigest()[:16]


def pull_latest_code_deprecated(workspace_path: Path, repo_url: str, branch: str = "main", token: Optional[str] = None) -> bool:
    """已废弃：使用 GitHelper.pull_latest 代替
    
    保留此函数仅用于向后兼容，新代码应使用 GitHelper
    
    原实现使用 git worktree 共享仓库，但当前实现已简化为直接克隆到工作目录
    """
    try:
        import shutil
        
        # 获取共享仓库路径
        repo_hash = get_repo_hash(repo_url)
        shared_repo_path = OSS_BASE_PATH / "repos" / repo_hash
        
        # 检查共享仓库是否存在
        shared_git_dir = shared_repo_path / ".git"
        
        if not shared_git_dir.exists():
            # 如果共享仓库不存在，先克隆
            logger.info(f"Cloning shared repository from {repo_url} to {shared_repo_path}")
            shared_repo_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 如果目录已存在但损坏，清理它
            if shared_repo_path.exists():
                shutil.rmtree(shared_repo_path)
            
            shared_repo_path.mkdir(parents=True, exist_ok=True)
            
            # 克隆仓库（支持 HTTPS URL 带 token）
            clone_url = repo_url
            # 如果是私有仓库且提供了 token，尝试添加到 URL
            # 公开仓库不需要 token
            if token and "://" in repo_url and "@" not in repo_url:
                # 尝试在 URL 中嵌入 token（用于私有仓库）
                if "github.com" in repo_url:
                    if repo_url.startswith("https://"):
                        clone_url = repo_url.replace("https://", f"https://{token}@")
                    elif repo_url.startswith("http://"):
                        clone_url = repo_url.replace("http://", f"http://{token}@")
            
            result = subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", clone_url, str(shared_repo_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                # 如果指定分支失败，可能是：
                # 1. 私有仓库需要 token（如果 token 未嵌入 URL）
                # 2. 分支不存在
                # 3. 网络问题
                logger.warning(f"Failed to clone repository with branch {branch}: {result.stderr}")
                
                # 如果是因为认证问题，尝试使用 token
                if "Authentication failed" in result.stderr or "401" in result.stderr:
                    if token and not token in clone_url:
                        logger.info("Retrying with token in URL...")
                        if clone_url.startswith("https://"):
                            clone_url = clone_url.replace("https://", f"https://{token}@")
                        elif clone_url.startswith("http://"):
                            clone_url = clone_url.replace("http://", f"http://{token}@")
                
                # 尝试克隆默认分支
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, str(shared_repo_path)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.error(f"Failed to clone repository (fallback): {result.stderr}")
                    # 如果是公开仓库，提示不需要 token
                    if "github.com" in repo_url and not token:
                        logger.info("Note: Public repositories don't require a token for cloning")
                    return False
                # 切换到指定分支
                result_check = subprocess.run(
                    ["git", "ls-remote", "--heads", "origin", branch],
                    cwd=str(shared_repo_path),
                    capture_output=True,
                    text=True
                )
                if result_check.returncode == 0 and result_check.stdout.strip():
                    subprocess.run(
                        ["git", "checkout", "-b", branch, f"origin/{branch}"],
                        cwd=str(shared_repo_path),
                        capture_output=True
                    )
                else:
                    logger.warning(f"Branch {branch} not found, staying on default branch")
            
            # 配置 git
            subprocess.run(
                ["git", "config", "user.name", "Sleepless Agent"],
                cwd=str(shared_repo_path),
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "agent@sleepless.local"],
                cwd=str(shared_repo_path),
                capture_output=True
            )
        else:
            # 如果共享仓库已存在，更新它
            logger.info(f"Updating shared repository from {repo_url}")
            
            # 配置 git
            subprocess.run(
                ["git", "config", "user.name", "Sleepless Agent"],
                cwd=str(shared_repo_path),
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "agent@sleepless.local"],
                cwd=str(shared_repo_path),
                capture_output=True
            )
            
            # 获取远程 URL（如果还没有设置）
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(shared_repo_path),
                capture_output=True,
                text=True
            )
            if result.returncode != 0 or not result.stdout.strip():
                subprocess.run(
                    ["git", "remote", "add", "origin", repo_url],
                    cwd=str(shared_repo_path),
                    capture_output=True
                )
            else:
                # 更新远程 URL（以防 URL 变化，但移除可能的 token）
                current_url = result.stdout.strip()
                # 如果 URL 变化，更新它
                if current_url != repo_url and not (token and token in current_url):
                    subprocess.run(
                        ["git", "remote", "set-url", "origin", repo_url],
                        cwd=str(shared_repo_path),
                        capture_output=True
                    )
            
            # 获取最新代码
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(shared_repo_path),
                capture_output=True,
                timeout=60
            )
            
            # 检查当前分支
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(shared_repo_path),
                capture_output=True,
                text=True
            )
            current_branch = result.stdout.strip()
            
            # 切换到目标分支并拉取
            if current_branch != branch:
                # 检查远程分支是否存在
                result_check = subprocess.run(
                    ["git", "ls-remote", "--heads", "origin", branch],
                    cwd=str(shared_repo_path),
                    capture_output=True,
                    text=True
                )
                if result_check.returncode == 0 and result_check.stdout.strip():
                    # 远程分支存在，创建本地分支跟踪远程分支
                    subprocess.run(
                        ["git", "checkout", "-b", branch, f"origin/{branch}"],
                        cwd=str(shared_repo_path),
                        capture_output=True
                    )
                else:
                    # 远程分支不存在，在当前分支创建新分支
                    subprocess.run(
                        ["git", "checkout", "-b", branch],
                        cwd=str(shared_repo_path),
                        capture_output=True
                    )
            else:
                # 当前分支就是目标分支，重置到远程分支
                subprocess.run(
                    ["git", "reset", "--hard", f"origin/{branch}"],
                    cwd=str(shared_repo_path),
                    capture_output=True
                )
            
            logger.info(f"Successfully updated shared repository from {branch}")
        
        # 使用 git worktree 为当前任务创建工作副本
        logger.info(f"Creating worktree for task at {workspace_path}")
        
        # 确保工作目录不存在或为空
        if workspace_path.exists():
            # 检查是否是已有的 worktree
            result = subprocess.run(
                ["git", "worktree", "list"],
                cwd=str(shared_repo_path),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # 查找是否已有这个路径的 worktree
                for line in result.stdout.split('\n'):
                    if str(workspace_path) in line:
                        # 移除已有的 worktree
                        subprocess.run(
                            ["git", "worktree", "remove", str(workspace_path)],
                            cwd=str(shared_repo_path),
                            capture_output=True
                        )
                        break
            # 清理目录
            shutil.rmtree(workspace_path)
        
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        # 创建 worktree（基于指定分支）
        # 注意：worktree 会共享 .git 目录，但工作目录是独立的
        # 这样可以复用 Git 对象，但依赖缓存需要单独处理
        result = subprocess.run(
            ["git", "worktree", "add", str(workspace_path), branch],
            cwd=str(shared_repo_path),
            capture_output=True,
            text=True
        )
        
        # 如果创建失败，尝试使用临时分支
        if result.returncode != 0:
            logger.warning(f"Failed to create worktree: {result.stderr}")
            # 尝试创建临时分支
            temp_branch = f"worktree-{os.getpid()}-{int(datetime.now().timestamp())}"
            result = subprocess.run(
                ["git", "worktree", "add", "-b", temp_branch, str(workspace_path), branch],
                cwd=str(shared_repo_path),
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.error(f"Failed to create worktree with temp branch: {result.stderr}")
                # 如果 worktree 创建失败，回退到独立克隆
                logger.info("Falling back to independent clone...")
                return pull_latest_code_fallback_deprecated(workspace_path, repo_url, branch, token)
        
        # 尝试共享依赖缓存（如果存在）
        # 注意：这需要根据项目类型来配置，比如 node_modules、.venv 等
        # 这里只是示例，实际实现需要根据项目类型判断
        if (shared_repo_path / "node_modules").exists():
            # 如果共享仓库有 node_modules，可以考虑使用符号链接
            # 但为了安全，这里不自动创建，避免不同任务之间的依赖冲突
            pass
        
        logger.info(f"Successfully created worktree at {workspace_path}")
        logger.debug(f"Shared repository: {shared_repo_path}, Worktree: {workspace_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error pulling latest code: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        # 如果 worktree 失败，回退到独立克隆
        logger.info("Falling back to independent clone...")
        return pull_latest_code_fallback_deprecated(workspace_path, repo_url, branch, token)


def pull_latest_code_fallback_deprecated(workspace_path: Path, repo_url: str, branch: str = "main", token: Optional[str] = None) -> bool:
    """已废弃：使用 GitHelper.pull_latest 代替
    
    保留此函数仅用于向后兼容，新代码应使用 GitHelper
    """
    try:
        import shutil
        
        # 检查是否是 git 仓库
        git_dir = workspace_path / ".git"
        
        if not git_dir.exists():
            # 如果不是 git 仓库，先初始化并克隆
            logger.info(f"Cloning git repository from {repo_url} (fallback mode)")
            # 移除目录内容（如果有）
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
            workspace_path.mkdir(parents=True, exist_ok=True)
            
            # 克隆仓库（支持 HTTPS URL 带 token）
            clone_url = repo_url
            # 如果是私有仓库且提供了 token，尝试添加到 URL
            # 公开仓库不需要 token
            if token and "://" in repo_url and "@" not in repo_url:
                # 尝试在 URL 中嵌入 token（用于私有仓库）
                if "github.com" in repo_url:
                    if repo_url.startswith("https://"):
                        clone_url = repo_url.replace("https://", f"https://{token}@")
                    elif repo_url.startswith("http://"):
                        clone_url = repo_url.replace("http://", f"http://{token}@")
            
            result = subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", clone_url, str(workspace_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                # 如果指定分支失败，可能是：
                # 1. 私有仓库需要 token（如果 token 未嵌入 URL）
                # 2. 分支不存在
                # 3. 网络问题
                logger.warning(f"Failed to clone repository with branch {branch}: {result.stderr}")
                
                # 如果是因为认证问题，尝试使用 token
                if "Authentication failed" in result.stderr or "401" in result.stderr:
                    if token and not token in clone_url:
                        logger.info("Retrying with token in URL...")
                        if clone_url.startswith("https://"):
                            clone_url = clone_url.replace("https://", f"https://{token}@")
                        elif clone_url.startswith("http://"):
                            clone_url = clone_url.replace("http://", f"http://{token}@")
                
                # 尝试克隆默认分支
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, str(workspace_path)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.error(f"Failed to clone repository (fallback): {result.stderr}")
                    # 如果是公开仓库，提示不需要 token
                    if "github.com" in repo_url and not token:
                        logger.info("Note: Public repositories don't require a token for cloning")
                    return False
                # 切换到指定分支
                result_check = subprocess.run(
                    ["git", "ls-remote", "--heads", "origin", branch],
                    cwd=str(workspace_path),
                    capture_output=True,
                    text=True
                )
                if result_check.returncode == 0 and result_check.stdout.strip():
                    subprocess.run(
                        ["git", "checkout", "-b", branch, f"origin/{branch}"],
                        cwd=str(workspace_path),
                        capture_output=True
                    )
                else:
                    logger.warning(f"Branch {branch} not found, staying on default branch")
        else:
            # 如果是 git 仓库，先拉取最新代码
            logger.info(f"Pulling latest code from {branch}")
            
            # 配置 git
            subprocess.run(
                ["git", "config", "user.name", "Sleepless Agent"],
                cwd=str(workspace_path),
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "agent@sleepless.local"],
                cwd=str(workspace_path),
                capture_output=True
            )
            
            # 获取远程 URL（如果还没有设置）
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True
            )
            if result.returncode != 0 or not result.stdout.strip():
                subprocess.run(
                    ["git", "remote", "add", "origin", repo_url],
                    cwd=str(workspace_path),
                    capture_output=True
                )
            else:
                # 更新远程 URL（以防 URL 变化）
                subprocess.run(
                    ["git", "remote", "set-url", "origin", repo_url],
                    cwd=str(workspace_path),
                    capture_output=True
                )
            
            # 获取最新代码
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(workspace_path),
                capture_output=True,
                timeout=60
            )
            
            # 检查当前分支
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True
            )
            current_branch = result.stdout.strip()
            
            # 切换到目标分支并拉取
            if current_branch != branch:
                # 检查远程分支是否存在
                result_check = subprocess.run(
                    ["git", "ls-remote", "--heads", "origin", branch],
                    cwd=str(workspace_path),
                    capture_output=True,
                    text=True
                )
                if result_check.returncode == 0 and result_check.stdout.strip():
                    # 远程分支存在，创建本地分支跟踪远程分支
                    subprocess.run(
                        ["git", "checkout", "-b", branch, f"origin/{branch}"],
                        cwd=str(workspace_path),
                        capture_output=True
                    )
                else:
                    # 远程分支不存在，在当前分支创建新分支
                    subprocess.run(
                        ["git", "checkout", "-b", branch],
                        cwd=str(workspace_path),
                        capture_output=True
                    )
            else:
                # 当前分支就是目标分支，重置到远程分支
                subprocess.run(
                    ["git", "reset", "--hard", f"origin/{branch}"],
                    cwd=str(workspace_path),
                    capture_output=True
                )
            
            logger.info(f"Successfully pulled latest code from {branch}")
        
        return True
    except Exception as e:
        logger.error(f"Error pulling latest code: {e}")
        return False


def create_pull_request_with_helper(
    workspace_path: Path,
    task_id: str,
    project: str,
    prompt: str,
    repo_url: str,
    branch: str,
    token: str
) -> Optional[str]:
    """创建 GitHub Pull Request（使用 GitHelper，参考 src/sleepless_agent/storage/git.py）
    
    改进点：
    1. 使用 GitHelper 统一 Git 操作
    2. 文件验证（secrets、Python 语法）
    3. 更好的错误处理和日志记录
    4. 支持 PR 已存在的情况
    """
    import requests
    
    # 使用 GitHelper 进行 Git 操作
    git_helper = GitHelper(workspace_path)
    
    # 提取 GitHub 仓库信息
    owner, repo = extract_github_repo_info(repo_url)
    if not owner or not repo:
        logger.error(f"Invalid GitHub repository URL: {repo_url}")
        return None
    
    # 创建功能分支
    feature_branch = f"agent/{task_id[:8]}"
    if not git_helper.create_feature_branch(feature_branch, branch):
        logger.error(f"Failed to create feature branch: {feature_branch}")
        return None
    
    # 检查是否有更改
    result = git_helper._run_git_safe("status", "--porcelain")
    if not result[0]:
        logger.info("No changes to commit")
        git_helper.checkout_branch(branch)
        git_helper._run_git_safe("branch", "-D", feature_branch)
        return None
    
    # 获取更改的文件列表
    changed_files = [
        line.split()[1] if len(line.split()) > 1 else line.split()[0]
        for line in result[1].split('\n') if line.strip()
    ]
    
    if not changed_files:
        logger.info("No changes to commit")
        git_helper.checkout_branch(branch)
        git_helper._run_git_safe("branch", "-D", feature_branch)
        return None
    
    # 验证文件（检查 secrets 和语法错误）
    is_valid, error_msg = git_helper.validate_changes(changed_files)
    if not is_valid:
        logger.warning(f"File validation failed: {error_msg}")
        logger.warning("Continuing despite validation issues...")
    
    # 暂存所有更改（GitHelper 会自动过滤被忽略的文件）
    # 使用 GitHelper 的 stage_files 方法（使用 GitPython）
    # 先获取所有更改的文件
    result = git_helper._run_git_safe("status", "--porcelain")
    if result[0]:
        changed_files = [
            line.split()[1] if len(line.split()) > 1 else line.split()[0]
            for line in result[1].split('\n') if line.strip()
        ]
        if changed_files:
            # 使用 GitHelper 的 stage_files 方法（使用 GitPython，会自动过滤被忽略的文件）
            git_helper.stage_files(changed_files)
        else:
            # 如果没有文件，尝试使用 git add -A（添加所有更改）
            # 注意：GitHelper 的 _run_git_safe 使用 GitPython 的 git.execute
            git_helper._run_git_safe("add", "-A")
    else:
        # 如果 status 失败，尝试直接 add -A
        git_helper._run_git_safe("add", "-A")
    
    # 提交更改
    commit_message = f"[Agent] {project}: {prompt[:100]}"
    commit_sha = git_helper.commit_changes(commit_message)
    if not commit_sha:
        logger.info("No changes to commit after staging")
        git_helper.checkout_branch(branch)
        git_helper._run_git_safe("branch", "-D", feature_branch)
        return None
    
    # 推送功能分支
    push_success = False
    try:
        push_success = git_helper.push_branch(feature_branch, "origin", token)
    except RuntimeError as e:
        logger.warning(f"Failed to push branch: {e}")
        # 检查分支是否已存在（可能之前的推送部分成功）
        result = git_helper._run_git_safe("ls-remote", "--heads", "origin", feature_branch)
        if result[0] and result[1].strip():
            logger.info(f"Branch {feature_branch} already exists on remote")
            push_success = True
    except Exception as e:
        logger.error(f"Unexpected error pushing branch: {e}")
    
    if not push_success:
        logger.warning(f"Push failed, but continuing to create PR...")
        logger.info(f"Branch: {feature_branch}, Commit: {commit_sha}")
        logger.info(f"Manual push: git push -u origin {feature_branch}")
    
    # 使用 GitHub API 创建 PR
    pr_title = f"[Agent] {project}: {prompt[:100]}"
    pr_body = f"""## Task Details
- **Task ID**: `{task_id}`
- **Project**: `{project}`
- **Prompt**: {prompt}

## Changes
This PR was automatically generated by Sleepless Agent after completing the task.

Please review the changes and merge if approved.

---
**Commit**: {commit_sha}
**Branch**: {feature_branch}
"""
    
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": pr_title,
        "body": pr_body,
        "head": feature_branch,
        "base": branch
    }
    
    # 检查 PR 是否已存在
    try:
        list_response = requests.get(
            f"{api_url}?head={owner}:{feature_branch}&state=open",
            headers=headers,
            timeout=30
        )
        if list_response.status_code == 200:
            existing_prs = list_response.json()
            if existing_prs and len(existing_prs) > 0:
                pr_data = existing_prs[0]
                pr_url = pr_data.get("html_url")
                logger.info(f"Pull Request already exists: {pr_url}")
                return pr_url
    except requests.exceptions.Timeout:
        logger.warning("Timeout checking existing PRs")
    except Exception as e:
        logger.warning(f"Failed to check existing PRs: {e}")
    
    # 创建新 PR（带重试）
    max_retries = 3
    pr_url = None
    for attempt in range(max_retries):
        try:
            response = requests.post(api_url, json=data, headers=headers, timeout=30)
            if response.status_code == 201:
                pr_data = response.json()
                pr_url = pr_data.get("html_url")
                logger.info(f"Created Pull Request: {pr_url}")
                return pr_url
            elif response.status_code == 422:
                error_data = response.json()
                if "already exists" in str(error_data):
                    # 再次尝试获取现有 PR
                    list_response = requests.get(
                        f"{api_url}?head={owner}:{feature_branch}",
                        headers=headers,
                        timeout=30
                    )
                    if list_response.status_code == 200:
                        existing_prs = list_response.json()
                        if existing_prs and len(existing_prs) > 0:
                            pr_data = existing_prs[0]
                            pr_url = pr_data.get("html_url")
                            logger.info(f"Found existing Pull Request: {pr_url}")
                            return pr_url
                logger.error(f"GitHub API error (422): {error_data}")
                break
            else:
                logger.warning(f"GitHub API request failed (attempt {attempt + 1}/{max_retries}): {response.status_code} - {response.text[:200]}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
        except requests.exceptions.Timeout:
            logger.warning(f"GitHub API timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"Exception creating PR (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)
    
    # 如果 PR 创建失败，但提交和推送成功，返回分支信息
    if commit_sha:
        logger.warning(f"Failed to create PR, but commit and push succeeded")
        logger.info(f"Branch: {feature_branch}, Commit: {commit_sha}")
        logger.info(f"Manual PR: https://github.com/{owner}/{repo}/compare/{branch}...{feature_branch}")
        return f"branch:{feature_branch}:{commit_sha}"
    
    return None


def create_pull_request(
    workspace_path: Path,
    task_id: str,
    project: str,
    prompt: str,
    repo_url: str,
    branch: str,
    token: str
) -> Optional[str]:
    """创建 GitHub Pull Request（兼容旧接口，内部调用新实现）"""
    return create_pull_request_with_helper(
        workspace_path=workspace_path,
        task_id=task_id,
        project=project,
        prompt=prompt,
        repo_url=repo_url,
        branch=branch,
        token=token
    )

