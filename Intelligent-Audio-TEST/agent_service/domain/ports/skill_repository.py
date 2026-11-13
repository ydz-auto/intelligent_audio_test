# -*- coding: utf-8 -*-
"""Skill 仓储端口（domain 定义，infrastructure/skill 实现）。

只负责「把 ``skills/`` 下的文档装载成领域对象」，不做校验取舍、不做权限
过滤——那是 application/skill_registry 的职责。
"""
from abc import ABC, abstractmethod

from agent_service.domain.model.skill_scan import SkillScanResult


class SkillRepository(ABC):
    @abstractmethod
    def load_all(self) -> SkillScanResult:
        """扫描 Skill 根目录，返回装载结果与目录级问题。

        目录不存在 / 不可读 / 为空、``skills/<name>/`` 缺 ``SKILL.md`` 都不抛
        异常：分别以 ``SKILLS_ROOT_MISSING`` / ``SKILLS_ROOT_UNREADABLE`` /
        ``SKILLS_ROOT_EMPTY`` / ``SKILL_FILE_MISSING`` 原因码回报（INT-2506），
        由 application 层统一判定严重度、是否让启动失败。单个 Skill 的格式
        问题仍通过 ``Skill.load_error`` 上报。
        """


__all__ = ['SkillRepository']
