# -*- coding: utf-8 -*-
"""Skill 自定义层 + 平台只读层的合并仓储（INT-2549 §4.4）。

实现既有 ``SkillRepository`` 端口：``load_all()`` 合并「平台只读扫描 +
自定义层读库」，按 ``USER > TENANT > PLATFORM`` 去重、打 ``masked_by``、
按 ``status`` 过滤（只有 ``ACTIVE`` 参与自动触发与 L1 列表）。

合并规则只此一份（``domain.services.skill_visibility.merge_skill_layers``），
列表接口也复用同一实现，不出现双口径。
"""
import logging
from typing import Optional

from agent_service.domain.model.skill_scan import SkillScanResult
from agent_service.domain.ports.skill_repository import SkillRepository
from agent_service.domain.repositories import AgentSkillRepository
from agent_service.domain.services.skill_visibility import (
    merge_skill_layers, to_domain_skill,
)

logger = logging.getLogger(__name__)


class CompositeSkillRepository(SkillRepository):
    def __init__(self, platform: SkillRepository,
                 custom: Optional[AgentSkillRepository] = None):
        self._platform = platform
        self._custom = custom

    @property
    def root(self):
        return getattr(self._platform, 'root', '')

    def load_all(self) -> SkillScanResult:
        scan = self._platform.load_all()
        if self._custom is None:
            return scan
        try:
            rows = self._custom.list_active()
        except Exception:  # noqa: BLE001 - 库不可用时退化为平台层
            # 自定义层读库失败不阻断启动：平台只读 Skill 仍应可用；
            # 但必须留 WARNING，不能静默当成「没有自定义 Skill」。
            logger.warning('自定义 Skill 读取失败，本次只装载平台层', exc_info=True)
            return scan
        custom_skills = []
        for row in rows:
            try:
                version = self._custom.get_version(row.id, row.version)
            except Exception:  # noqa: BLE001 - 单行失败不拖垮整层
                logger.warning('自定义 Skill 版本读取失败 skill=%s', row.id,
                               exc_info=True)
                version = None
            custom_skills.append(to_domain_skill(row, version))
        effective, masked = merge_skill_layers(
            list(scan.skills), custom_skills, active_only=True)
        return SkillScanResult(skills=effective, issues=scan.issues,
                               masked=masked)


__all__ = ['CompositeSkillRepository']
