# -*- coding: utf-8 -*-
"""Skill 三层来源的合并与去重（INT-2549 §4.4「来源与优先级」）。

唯一实现：``CompositeSkillRepository`` 与列表接口共用本模块，不各写一套。

规则：
- 优先级 ``USER > TENANT > PLATFORM``；
- 同名时高层生效，低层进入 ``masked`` 并带 ``masked_by``（被哪个作用域遮蔽）；
- 只有 ``ACTIVE`` 参与自动触发与 L1 列表（是否过滤由调用方决定，本模块
  只做合并；``active_only=True`` 时先按状态过滤）。
"""
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from agent_service.domain.enums import SkillScope
from agent_service.domain.model.agent_skill import AgentSkill, AgentSkillVersion
from agent_service.domain.model.skill import (
    FIELD_ALLOWED_TOOLS,
    FIELD_BUDGETS, FIELD_DESCRIPTION, FIELD_NAME, FIELD_OWNER, FIELD_PERMISSIONS,
    FIELD_VERSION, Skill, SkillMeta,
)


def text_list(value) -> Tuple[str, ...]:
    """frontmatter 列表字段归一（与 FsSkillRepository 同口径）。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(',') if item.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def budget_map(value) -> Dict[str, int]:
    if not isinstance(value, dict):
        return {}
    budgets: Dict[str, int] = {}
    for key, raw in value.items():
        try:
            budgets[str(key)] = int(raw)
        except (TypeError, ValueError):
            continue
    return budgets


def meta_from_frontmatter(frontmatter) -> SkillMeta:
    """库内 ``frontmatter_json`` → ``SkillMeta``（解析只经字段常量）。"""
    data = frontmatter if isinstance(frontmatter, dict) else {}
    return SkillMeta(
        name=str(data.get(FIELD_NAME) or '').strip(),
        description=str(data.get(FIELD_DESCRIPTION) or '').strip(),
        version=str(data.get(FIELD_VERSION) or '').strip(),
        owner=str(data.get(FIELD_OWNER) or '').strip(),
        allowed_tools=text_list(data.get(FIELD_ALLOWED_TOOLS)),
        permissions=text_list(data.get(FIELD_PERMISSIONS)),
        budgets=budget_map(data.get(FIELD_BUDGETS)),
    )


def to_domain_skill(row: AgentSkill,
                    version: Optional[AgentSkillVersion]) -> Skill:
    """库内行 + 版本快照 → 领域 ``Skill``（正文取版本表，不双写）。"""
    body = version.body if version is not None else ''
    frontmatter = version.frontmatter if version is not None else row.frontmatter
    resources = version.resources if version is not None else row.resources
    meta = meta_from_frontmatter(frontmatter)
    if row.version:
        # 库内版本指针是权威值（frontmatter 里的 version 是作者手写的语义版本）
        meta = replace(meta, version=str(row.version))
    return Skill(
        meta=meta,
        body=body,
        path=f'agent_skill/{row.id}',
        references=tuple(sorted(p for p in resources or ()
                                 if p.startswith('references/'))),
        scripts=tuple(sorted(p for p in resources or ()
                             if p.startswith('scripts/'))),
        assets=tuple(sorted(p for p in resources or ()
                            if p.startswith('assets/'))),
        skill_id=row.id,
        scope=row.scope,
        status=row.status,
        content_hash=row.content_hash,
        resources=dict(resources or {}),
        owner_id=row.owner_id,
        tenant_id=row.tenant_id,
    )


def merge_skill_layers(platform: Sequence[Skill],
                       custom: Sequence[Skill], *,
                       active_only: bool = True
                       ) -> Tuple[Tuple[Skill, ...], Tuple[Skill, ...]]:
    """合并平台层与自定义层，返回 ``(生效项, 被遮蔽项)``。

    被遮蔽项带 ``masked_by``（遮蔽它的作用域名），用于列表标注；L1 只取
    生效项（调用方负责权限过滤）。
    """
    effective: List[Skill] = []
    masked: List[Skill] = []
    # 同名桶：先放平台层，再按优先级放入自定义层
    buckets: Dict[str, Skill] = {}
    others: Dict[str, List[Skill]] = {}

    def _accept(item: Skill) -> None:
        if active_only and not item.status.participates_in_trigger:
            return
        if not item.name:
            return
        current = buckets.get(item.name)
        if current is None:
            buckets[item.name] = item
            return
        if item.scope.precedence > current.scope.precedence:
            buckets[item.name] = item
            others.setdefault(item.name, []).append(current)
        else:
            others.setdefault(item.name, []).append(item)

    for skill in platform:
        _accept(skill)
    for skill in custom:
        _accept(skill)

    for name, skill in buckets.items():
        effective.append(skill)
        for shadowed in others.get(name, ()):
            masked.append(_with_masked_by(shadowed, skill.scope))
    return tuple(effective), tuple(masked)


def _with_masked_by(skill: Skill, by: SkillScope) -> Skill:
    return Skill(
        meta=skill.meta, body=skill.body, path=skill.path,
        references=skill.references, scripts=skill.scripts,
        assets=skill.assets, load_error=skill.load_error,
        skill_id=skill.skill_id, scope=skill.scope, status=skill.status,
        masked_by=by.value, content_hash=skill.content_hash,
        resources=skill.resources, owner_id=skill.owner_id,
        tenant_id=skill.tenant_id,
    )


__all__ = [
    'budget_map', 'merge_skill_layers', 'meta_from_frontmatter',
    'text_list', 'to_domain_skill',
]
