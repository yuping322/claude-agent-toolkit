#!/usr/bin/env python3
"""
Live Status Tracker - Real-time status tracking for tasks.

This module provides the LiveStatusTracker and LiveStatusEntry classes
for tracking task execution status in real-time.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class LiveStatusEntry:
    """实时状态条目"""
    task_id: str
    description: Optional[str] = None
    project_name: Optional[str] = None
    phase: str = "pending"
    prompt_preview: str = ""
    answer_preview: str = ""
    status: str = "running"


class LiveStatusTracker:
    """实时状态跟踪器"""

    def __init__(self):
        self._entries: Dict[str, LiveStatusEntry] = {}

    def update(self, entry: LiveStatusEntry) -> None:
        """更新任务状态"""
        self._entries[entry.task_id] = entry

    def get(self, task_id: str) -> Optional[LiveStatusEntry]:
        """获取任务状态"""
        return self._entries.get(task_id)

    def clear(self, task_id: str) -> None:
        """清除任务状态"""
        self._entries.pop(task_id, None)

    def list_all(self) -> Dict[str, LiveStatusEntry]:
        """列出所有任务状态"""
        return self._entries.copy()