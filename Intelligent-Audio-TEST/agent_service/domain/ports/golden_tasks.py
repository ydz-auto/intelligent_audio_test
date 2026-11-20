# -*- coding: utf-8 -*-
"""发布门槛的 golden tasks 端口（INT-2549 §4.4「安全与生命周期」）。

发布（``publish``）需 ≥ 3 条 golden tasks 且触发判定通过才转 ``ACTIVE``。
评测集复用 INT-2454 / INT-2465 的 golden 基座（``tests/agent_eval`` 的
``skill_trigger_tasks.json`` 结构：``{"tasks": [{skill, query}, ...]}``），
不新建第二套。端口只做读取，判定在 application 层。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class GoldenTask:
    """一条 golden task：归属于某 Skill 的用户口语请求。"""

    task_id: str
    skill: str
    query: str


class GoldenTaskProvider(ABC):
    @abstractmethod
    def tasks_for(self, skill_name: str) -> Sequence[GoldenTask]:
        """返回该 Skill 名下的 golden tasks（无数据返回空序列，不抛异常）。"""


class EmptyGoldenTaskProvider(GoldenTaskProvider):
    """未配置评测集时的空实现：发布门槛恒不通过（只能留 DRAFT）。"""

    def tasks_for(self, skill_name: str) -> Sequence[GoldenTask]:
        return ()


__all__ = ['EmptyGoldenTaskProvider', 'GoldenTask', 'GoldenTaskProvider']
