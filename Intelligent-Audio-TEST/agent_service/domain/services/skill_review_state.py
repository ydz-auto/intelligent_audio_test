# -*- coding: utf-8 -*-
"""TENANT 级共享 Skill 的审核状态机（INT-2551 §4.4「安全与生命周期」）。

唯一实现：``SkillService``（PENDING_REVIEW 冻结保存 / 停用）与
``SkillReviewService``（提交 / 批准 / 驳回 / 撤回）共用本模块，不在接口层
或服务层各写一份 if/else。

迁移表（动作 → 目标状态），``None`` 表示该动作在当前状态下非法：

| 当前状态       | SUBMIT         | APPROVE | REJECT | WITHDRAW | DISABLE |
|----------------|----------------|---------|--------|----------|---------|
| DRAFT          | PENDING_REVIEW | -       | -      | -        | DISABLED|
| PENDING_REVIEW | -              | ACTIVE  | DRAFT  | DRAFT    | DISABLED|
| ACTIVE         | -              | -       | -      | -        | DISABLED|
| DISABLED       | -              | -       | -      | -        | -       |

``USER`` 级不进审核流：它只允许 DISABLE 这一个动作（发布走 ``publish``），
由 :func:`ensure_review_scope` 在进入状态机之前拒绝。
"""
from typing import Dict, Optional

from agent_service.domain.enums import (
    SkillReviewAction, SkillScope, SkillStatus,
)
from agent_service.domain.exceptions import SkillStatusInvalid

# 状态 × 动作 → 目标状态（缺失即非法迁移）
_TRANSITIONS: Dict[SkillStatus, Dict[SkillReviewAction, SkillStatus]] = {
    SkillStatus.DRAFT: {
        SkillReviewAction.SUBMIT: SkillStatus.PENDING_REVIEW,
        SkillReviewAction.DISABLE: SkillStatus.DISABLED,
    },
    SkillStatus.PENDING_REVIEW: {
        SkillReviewAction.APPROVE: SkillStatus.ACTIVE,
        SkillReviewAction.REJECT: SkillStatus.DRAFT,
        SkillReviewAction.WITHDRAW: SkillStatus.DRAFT,
        SkillReviewAction.DISABLE: SkillStatus.DISABLED,
    },
    SkillStatus.ACTIVE: {
        SkillReviewAction.DISABLE: SkillStatus.DISABLED,
    },
    SkillStatus.DISABLED: {},
}


def target_status(current: SkillStatus,
                  action: SkillReviewAction) -> SkillStatus:
    """返回迁移目标状态；当前状态不允许该动作时抛 ``SKILL_STATUS_INVALID``。"""
    target: Optional[SkillStatus] = _TRANSITIONS.get(current, {}).get(action)
    if target is None:
        raise SkillStatusInvalid(
            f'状态 {current.value} 不允许动作 {action.value}'
            f'（合法迁移见 skill_review_state）')
    return target


def allowed_actions(current: SkillStatus) -> frozenset:
    """当前状态允许的动作集合（供接口 / 测试断言，不另写字面量）。"""
    return frozenset(_TRANSITIONS.get(current, {}))


def ensure_review_scope(scope: SkillScope) -> None:
    """审核流只对 ``TENANT`` 生效：``USER`` / ``PLATFORM`` 一律拒绝。"""
    if scope is SkillScope.USER:
        raise SkillStatusInvalid(
            'USER 级 Skill 不走审核流：本人显式发布（POST /skills/{id}/publish）')
    if scope is not SkillScope.TENANT:
        raise SkillStatusInvalid('PLATFORM 级 Skill 只读，不支持审核流')


__all__ = ['allowed_actions', 'ensure_review_scope', 'target_status']
