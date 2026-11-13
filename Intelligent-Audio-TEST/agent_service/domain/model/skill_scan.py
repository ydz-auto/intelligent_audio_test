# -*- coding: utf-8 -*-
"""Skill 目录扫描结果（domain 值对象，INT-2506）。

``SkillRepository.load_all`` 除了返回装载成功的 Skill，还必须把**目录级失败**
（根目录不存在 / 不可读 / 为空、目录缺 ``SKILL.md``）作为 ``SkillScanIssue``
一起回传：扫描阶段就带原因码，由 application 层统一收进 ``SkillRegistry.issues``
并决定严重度与取舍。这样「Skill 层整体消失」不会只留一行日志。
"""
from dataclasses import dataclass, field
from typing import Tuple

from agent_service.domain.enums import SkillIssueCode
from agent_service.domain.model.skill import Skill


@dataclass(frozen=True)
class SkillScanIssue:
    """一条目录级扫描问题。``path`` 是出问题的目录（不是 Skill 名）。"""

    code: SkillIssueCode
    path: str
    message: str = ''


@dataclass(frozen=True)
class SkillScanResult:
    """一次目录扫描的完整结果：装载到的 Skill + 目录级问题。"""

    skills: Tuple[Skill, ...] = ()
    issues: Tuple[SkillScanIssue, ...] = field(default_factory=tuple)


__all__ = ['SkillScanIssue', 'SkillScanResult']
