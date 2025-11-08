#!/usr/bin/env python3
"""
Custom Command Executor - Generic command execution backend.

This module provides the CustomCommandExecutor for running arbitrary command-line tools.
"""

import os
import subprocess
import asyncio
import logging
from typing import Optional, Tuple, Dict, List
from pathlib import Path

from .base import Executor

logger = logging.getLogger(__name__)


class CustomCommandExecutor(Executor):
    """自定义命令执行器（支持任意命令行工具）"""

    def __init__(
        self,
        command: List[str],
        name: str = "custom",
        check_available_command: Optional[List[str]] = None,
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