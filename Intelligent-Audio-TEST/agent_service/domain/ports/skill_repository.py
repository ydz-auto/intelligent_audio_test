# -*- coding: utf-8 -*-
"""Skill 仓储端口（domain 定义，infrastructure/skill 实现）。

只负责「把 ``skills/`` 下的文档装载成领域对象」，不做校验取舍、不做权限
过滤——那是 application/skill_registry 的职责。
"""
from abc import ABC, abstractmethod
from typing import Sequence

from agent_service.domain.model.skill import Skill


class SkillRepository(ABC):
    @abstractmethod
    def load_all(self) -> Sequence[Skill]:
        """扫描 Skill 根目录，返回全部 ``skills/<name>/SKILL.md``。

        目录不存在时返回空序列（服务照常启动，由调用方告警）；
        单个 Skill 的格式问题不抛异常，通过 ``Skill.load_error`` 上报。
        """


__all__ = ['SkillRepository']
