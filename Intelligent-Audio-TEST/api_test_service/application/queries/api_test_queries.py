# -*- coding: utf-8 -*-
"""查询对象 — 应用层只读用例输入，纯数据载体。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GetAPITestStatusQuery:
    """查询 API 测试任务状态"""

    task_id: int
