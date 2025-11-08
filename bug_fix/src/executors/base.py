#!/usr/bin/env python3
"""
Executor Base Classes - Abstract interfaces for execution backends.

This module defines the abstract base classes and protocols for different
execution backends that can run AI agents and tools.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any
from pathlib import Path


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