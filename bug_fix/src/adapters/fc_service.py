#!/usr/bin/env python3
"""
FC Service Adapter - Integration with Alibaba Cloud Function Compute.

This module provides the FCServiceAdapter class for handling
FC-specific functionality like OSS integration, logging, and
serverless execution management.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..runtime import ExecutionContext, get_environment_config

logger = logging.getLogger(__name__)


class FCServiceAdapter:
    """FC 服务适配器"""

    def __init__(self):
        self.env_config = get_environment_config()

    def is_available(self) -> bool:
        """检查是否在 FC 环境中"""
        return self.env_config.is_fc()

    def get_execution_context(self) -> ExecutionContext:
        """从 FC 环境获取执行上下文"""
        from ..runtime import load_execution_context
        return load_execution_context("fc")

    def get_oss_mount_path(self) -> Optional[str]:
        """获取 OSS 挂载路径"""
        return self.env_config.get("fc.oss_mount_path")

    def is_oss_available(self) -> bool:
        """检查 OSS 是否可用"""
        mount_path = self.get_oss_mount_path()
        if not mount_path:
            return False
        return Path(mount_path).exists()

    def get_function_info(self) -> Dict[str, Any]:
        """获取函数信息"""
        return {
            "runtime": self.env_config.get("fc.runtime", "unknown"),
            "instance_id": self.env_config.get("fc.instance_id", "unknown"),
            "memory_size": self.env_config.get("fc.memory_size", "unknown"),
            "timeout": self.env_config.get("fc.timeout", "unknown"),
        }

    def save_execution_result(self, execution_id: str, result: Dict[str, Any]) -> bool:
        """保存执行结果到 OSS"""
        if not self.is_oss_available():
            logger.warning("OSS not available, cannot save execution result")
            return False

        try:
            mount_path = self.get_oss_mount_path()
            result_path = Path(mount_path) / "results" / f"{execution_id}.json"

            # 确保目录存在
            result_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存结果
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved execution result to {result_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save execution result: {e}")
            return False

    def load_execution_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """从 OSS 加载执行结果"""
        if not self.is_oss_available():
            logger.warning("OSS not available, cannot load execution result")
            return None

        try:
            mount_path = self.get_oss_mount_path()
            result_path = Path(mount_path) / "results" / f"{execution_id}.json"

            if not result_path.exists():
                return None

            with open(result_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load execution result: {e}")
            return None

    def save_shared_repository(self, repo_url: str, repo_path: Path) -> bool:
        """保存共享仓库到 OSS"""
        if not self.is_oss_available():
            logger.warning("OSS not available, cannot save shared repository")
            return False

        try:
            mount_path = self.get_oss_mount_path()
            # 使用仓库哈希作为目录名
            from ..runtime import get_repo_hash
            repo_hash = get_repo_hash(repo_url)
            shared_path = Path(mount_path) / "repos" / repo_hash

            # 如果目标已存在，先清理
            if shared_path.exists():
                import shutil
                shutil.rmtree(shared_path)

            # 复制仓库
            if repo_path.exists():
                import shutil
                shutil.copytree(repo_path, shared_path)
                logger.info(f"Saved shared repository to {shared_path}")
                return True
            else:
                logger.warning(f"Source repository path does not exist: {repo_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to save shared repository: {e}")
            return False

    def load_shared_repository(self, repo_url: str, target_path: Path) -> bool:
        """从 OSS 加载共享仓库"""
        if not self.is_oss_available():
            logger.warning("OSS not available, cannot load shared repository")
            return False

        try:
            mount_path = self.get_oss_mount_path()
            from ..runtime import get_repo_hash
            repo_hash = get_repo_hash(repo_url)
            shared_path = Path(mount_path) / "repos" / repo_hash

            if not shared_path.exists():
                logger.info(f"Shared repository not found: {shared_path}")
                return False

            # 如果目标已存在，先清理
            if target_path.exists():
                import shutil
                shutil.rmtree(target_path)

            # 复制仓库
            import shutil
            shutil.copytree(shared_path, target_path)
            logger.info(f"Loaded shared repository from {shared_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load shared repository: {e}")
            return False

    def log_execution_metrics(self, execution_id: str, metrics: Dict[str, Any]):
        """记录执行指标"""
        try:
            # 在 FC 环境中，可以将指标记录到日志或 OSS
            metrics_json = json.dumps(metrics, indent=2, ensure_ascii=False)
            logger.info(f"Execution metrics for {execution_id}: {metrics_json}")

            # 也可以保存到 OSS
            if self.is_oss_available():
                mount_path = self.get_oss_mount_path()
                metrics_path = Path(mount_path) / "metrics" / f"{execution_id}.json"
                metrics_path.parent.mkdir(parents=True, exist_ok=True)

                with open(metrics_path, 'w', encoding='utf-8') as f:
                    json.dump(metrics, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to log execution metrics: {e}")

    def get_execution_timeout(self) -> int:
        """获取执行超时时间（秒）"""
        timeout_str = self.env_config.get("fc.timeout")
        if timeout_str:
            try:
                return int(timeout_str)
            except ValueError:
                pass
        return 300  # 默认 5 分钟

    def should_use_shared_repos(self) -> bool:
        """是否应该使用共享仓库"""
        # 在 FC 环境中，优先使用共享仓库来减少网络传输
        return self.is_oss_available()

    def get_memory_limit(self) -> Optional[int]:
        """获取内存限制（MB）"""
        memory_str = self.env_config.get("fc.memory_size")
        if memory_str:
            try:
                return int(memory_str)
            except ValueError:
                pass
        return None

    def cleanup_temp_files(self, execution_id: str):
        """清理临时文件"""
        try:
            # 在 FC 环境中，清理可能存在的临时文件
            # 这里可以实现具体的清理逻辑
            logger.info(f"Cleaning up temporary files for execution {execution_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup temporary files: {e}")

    def report_health_status(self) -> Dict[str, Any]:
        """报告健康状态"""
        return {
            "environment": "fc",
            "oss_available": self.is_oss_available(),
            "function_info": self.get_function_info(),
            "memory_limit": self.get_memory_limit(),
            "timeout": self.get_execution_timeout(),
        }