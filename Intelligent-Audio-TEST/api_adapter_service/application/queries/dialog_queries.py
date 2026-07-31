# -*- coding: utf-8 -*-
"""对话相关查询定义。"""

from dataclasses import dataclass


@dataclass
class GetTaskStatusQuery:
    """查询任务状态。"""
    task_id: str


@dataclass
class GetFinalResultQuery:
    """查询任务最终结果（对话或流式）。"""
    task_id: str
