# -*- coding: utf-8 -*-
"""任务合并关系实体（值对象）"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskMergeRelationEntity:
    """任务合并关系实体（值对象）。"""
    merged_task_id: int
    source_task_id: int
    source_result_count: int = 0
