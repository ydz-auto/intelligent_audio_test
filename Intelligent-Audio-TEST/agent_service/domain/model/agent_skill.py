# -*- coding: utf-8 -*-
"""自定义 Skill 领域实体（INT-2549 §4.4 / §10）。

三张表对应三个实体：

- ``AgentSkill``：一份自定义 Skill 的当前指针（``version`` 指向版本表），
  正文不落本行（避免双写），由 ``AgentSkillVersion`` 承载；
- ``AgentSkillVersion``：不可变版本快照，``(skill_id, version)`` 唯一；
- ``AgentRunSkill``：run 激活快照。回放以「本表 + 版本表」为准，Skill 后续
  修改不影响历史 run（§4.4「安全与生命周期」）。

资源（``references/`` / ``scripts/`` / ``assets/``）只在表内存对象存储 key，
``resources`` 是「相对路径 → key」映射。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from agent_service.domain.enums import (
    SkillReviewAction, SkillScope, SkillStatus,
)


@dataclass(frozen=True)
class AgentSkill:
    """当前版本指针 + 元信息。"""

    id: str
    scope: SkillScope
    name: str
    description: str = ''
    version: str = '0'
    status: SkillStatus = SkillStatus.DRAFT
    content_hash: str = ''
    frontmatter: Mapping[str, Any] = field(default_factory=dict)
    resources: Mapping[str, str] = field(default_factory=dict)
    tenant_id: Optional[str] = None
    owner_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class AgentSkillVersion:
    """一个不可变版本快照（正文与 frontmatter 的唯一事实源）。"""

    skill_id: str
    version: str
    content_hash: str
    body: str
    frontmatter: Mapping[str, Any] = field(default_factory=dict)
    resources: Mapping[str, str] = field(default_factory=dict)
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class AgentRunSkill:
    """run 内一次 Skill 激活 / 切换的快照行。"""

    run_id: str
    skill_id: str
    version: str
    content_hash: str
    activated_at: Optional[datetime] = None


@dataclass(frozen=True)
class AgentSkillReview:
    """一次审核流动作的不可变审计行（INT-2551 §4.4「安全与生命周期」）。

    版本粒度可追溯：``version`` 是动作发生时 Skill 的版本指针，``action``
    是状态机迁移动作，``status_from`` / ``status_to`` 是迁移两端。整条链按
    ``created_at`` 升序即可还原「谁、哪一版、什么理由」。
    """

    id: str
    skill_id: str
    version: str
    action: SkillReviewAction
    status_from: SkillStatus
    status_to: SkillStatus
    reviewer_id: Optional[int] = None
    reason: str = ''
    tenant_id: Optional[str] = None
    created_at: Optional[datetime] = None


__all__ = [
    'AgentRunSkill', 'AgentSkill', 'AgentSkillReview', 'AgentSkillVersion',
]
