# -*- coding: utf-8 -*-
"""Skill 自定义层 + 平台只读层的候选装载仓储（INT-2549 §4.4）。

实现既有 ``SkillRepository`` 端口：``load_all()`` 返回「平台只读扫描 +
自定义层读库」的**候选集**，只按状态过滤（只有 ``ACTIVE`` 参与自动触发与
L1 列表）。

同名遮蔽不在这里做：三层合并是**查看者相关**的（不同 owner 的同名 USER
Skill 各自生效，某租户的同名 TENANT Skill 不影响其他租户看到 PLATFORM），
必须拿到 ``owner_id`` / ``tenant_id`` 才能判定。唯一实现在
``domain.services.skill_visibility.merge_skill_layers``，由
``SkillRegistry``（L1 / 激活候选）与列表接口按 viewer 调用，不出现双口径。
"""
import logging
from typing import Optional

from agent_service.domain.model.skill_scan import SkillScanResult
from agent_service.domain.ports.skill_repository import SkillRepository
from agent_service.domain.repositories import AgentSkillRepository
from agent_service.domain.services.skill_visibility import to_domain_skill

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
        # 平台层在前、自定义层在后：registry 的 ``get``（无身份视角）与
        # 合并桶的插入顺序都依赖这个次序。
        return SkillScanResult(
            skills=tuple(scan.skills) + tuple(custom_skills),
            issues=scan.issues)


__all__ = ['CompositeSkillRepository']
