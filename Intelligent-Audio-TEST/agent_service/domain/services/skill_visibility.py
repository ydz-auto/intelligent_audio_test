# -*- coding: utf-8 -*-
"""Skill 三层来源的合并与去重（INT-2549 §4.4「来源与优先级」）。

唯一实现：``SkillRegistry``（L1 / 激活候选 / 权限可见性）与列表接口共用
本模块，不各写一套。仓储层只装载候选、不在这里做去重。

规则（**查看者相关**）：
- 可见范围：``PLATFORM`` 全体可见；``TENANT`` 只对同租户可见；``USER``
  只对本人可见（未传身份时只放行 ``PLATFORM``，安全默认）；
- 同名只在**同一查看者可见的范围内**比较：两个用户各自的同名 USER Skill
  互不遮蔽；某租户的同名 TENANT Skill 也不影响其他租户看到 PLATFORM；
- 遮蔽只发生在同一查看者的跨层同名：``USER > TENANT > PLATFORM``，
  被遮蔽项带 ``masked_by``（遮蔽它的作用域名）；
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


def skill_identity(skill: Skill) -> Tuple[str, Optional[object], str]:
    """Skill 的身份键（与库内局部唯一索引同一口径）。

    ``USER`` 按 ``owner_id``、``TENANT`` 按 ``tenant_id``、``PLATFORM`` 无归
    属；同名判断只在同一身份切片内成立，跨 owner / 跨租户的同名是不同 Skill。
    """
    scope = skill.scope if isinstance(skill.scope, SkillScope) \
        else SkillScope(str(skill.scope))
    if scope is SkillScope.TENANT:
        holder = skill.tenant_id
    elif scope is SkillScope.USER:
        holder = skill.owner_id
    else:
        holder = None
    return (scope.value, holder, skill.name)


def viewer_allows(skill: Skill, owner_id: Optional[int],
                  tenant_id: Optional[str]) -> bool:
    """可见范围（INT-2549）：USER 只对本人、TENANT 只对本租户、PLATFORM 全体。

    未传身份（``owner_id`` / ``tenant_id`` 为 ``None``）时只放行 PLATFORM，
    保证「读库失败 / 调用方漏传身份」不会把别人的私有 Skill 泄漏出去。
    """
    if skill.scope is SkillScope.PLATFORM:
        return True
    if skill.scope is SkillScope.TENANT:
        return tenant_id is not None and skill.tenant_id == tenant_id
    return owner_id is not None and skill.owner_id == owner_id


def merge_skill_layers(skills: Sequence[Skill], *,
                       owner_id: Optional[int] = None,
                       tenant_id: Optional[str] = None,
                       active_only: bool = True
                       ) -> Tuple[Tuple[Skill, ...], Tuple[Skill, ...]]:
    """按「当前查看者」合并三层来源，返回 ``(生效项, 被遮蔽项)``。

    合并键是 Skill 名称，但只在 ``viewer_allows`` 放行的范围内比较：
    不同 owner 的同名 USER Skill 各自生效，互不进入 ``masked``；某租户的
    同名 TENANT Skill 也不会遮蔽其他租户看到的 PLATFORM 同名 Skill。
    被遮蔽项带 ``masked_by``（遮蔽它的作用域名），用于列表标注；L1 只取
    生效项（调用方负责权限过滤）。
    """
    effective: List[Skill] = []
    masked: List[Skill] = []
    # 同名桶：平台层先入，自定义层按优先级覆盖（仅同一查看者视角）
    buckets: Dict[str, Skill] = {}
    others: Dict[str, List[Skill]] = {}

    def _accept(item: Skill) -> None:
        if active_only and not item.status.participates_in_trigger:
            return
        if not item.name:
            return
        if not viewer_allows(item, owner_id, tenant_id):
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

    for skill in skills:
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
    'skill_identity', 'text_list', 'to_domain_skill', 'viewer_allows',
]
