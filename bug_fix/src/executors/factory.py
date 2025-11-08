#!/usr/bin/env python3
"""
Executor Factory - Factory for creating executor instances.

This module provides the ExecutorFactory for creating and managing
different executor implementations.
"""

import logging
from typing import Dict, Any, Optional

from .base import Executor
from .claude_code import ClaudeCodeExecutor
from .cursor import CursorExecutor
from .custom import CustomCommandExecutor

logger = logging.getLogger(__name__)


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