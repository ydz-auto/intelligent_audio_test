# -*- coding: utf-8 -*-
"""命令对象 — 应用层用例输入，纯数据载体。"""
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class CreateAPITestCommand:
    """创建（启动）API 测试会话命令

    与 APITestService.start_task 的签名对齐。
    """

    task_id: int
    case_ids: List[int] = field(default_factory=list)
    api_ids: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class StopAPITestCommand:
    """停止 API 测试会话命令"""

    task_id: int
