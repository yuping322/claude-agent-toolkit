#!/usr/bin/env python3
"""
Cursor Executor - Cursor CLI execution backend.

This module provides the CursorExecutor implementation for running Cursor CLI.
"""

import os
import subprocess
import asyncio
import logging
from typing import Optional, Tuple, Dict
from pathlib import Path

from .base import Executor

logger = logging.getLogger(__name__)


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
        exec_env = dict(os.environ)
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