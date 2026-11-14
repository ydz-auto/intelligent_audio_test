# -*- coding: utf-8 -*-
"""TENANT 级共享 Skill 的发布审核服务（INT-2551 §4.4）。

状态机（唯一实现在 ``domain.services.skill_review_state``）::

    DRAFT --SUBMIT--> PENDING_REVIEW --APPROVE--> ACTIVE
                          |               `--REJECT(reason)--> DRAFT
                          `--WITHDRAW--> DRAFT
    (任意非 DISABLED 状态) --DISABLE--> DISABLED

职责边界：

- **权限**：每个动作都要求租户管理员双条件（RBAC 权限码
  ``agent:skill:admin`` + 服务端复核的管理员角色）；跨租户一律 404。
- **禁止自审**：创建人（``owner_id`` / ``created_by``）与提交人（最近一条
  ``SUBMIT`` 的 ``reviewer_id``）都不得审批同一个版本 —— 提交人自己当审批人
  等于没有第二人复核（INT-2594 P1：换人提交再自己批准同样拦住）。
- **校验不绕过**：提交和批准都调用 ``SkillService.evaluate_publish``，
  与 INT-2549 的保存校验、注入检测、≥3 条 golden tasks 门槛**完全相同**，
  不复制任何一条规则；批准时复跑，防审批期间规则 / 权限变化。
- **并发**：状态推进一律 ``transition_if`` 条件更新，同一版本两个管理员
  同时批准只有一次生效，另一次拿到状态冲突。
- **审计**：每个动作追加一条 ``agent_skill_review``（谁、哪版、什么理由），
  版本粒度可还原完整审批链。
"""
import logging
from typing import Iterable, List, Optional

from agent_service.application.skill_service import (
    GateResult, SkillService, SkillView,
)
from agent_service.domain.enums import (
    SkillReviewAction, SkillReviewDecision, SkillStatus,
)
from agent_service.domain.exceptions import (
    SkillGateFailed, SkillSelfReviewForbidden, SkillServiceError,
    SkillStatusInvalid,
)
from agent_service.domain.model.agent_skill import AgentSkill, AgentSkillReview
from agent_service.domain.repositories import (
    AgentSkillRepository, SkillReviewRepository,
)
from agent_service.domain.services.skill_review_state import (
    ensure_review_scope, target_status,
)
from agent_service.domain.services.skill_tenancy import ensure_tenant_admin

logger = logging.getLogger(__name__)


class ReviewResult:
    """提交 / 审批的返回体（视图 + 门槛 + 本次审计行）。"""

    def __init__(self, *, skill: SkillView, review: AgentSkillReview,
                 gate: GateResult):
        self.skill = skill
        self.review = review
        self.gate = gate

    @property
    def participates_in_trigger(self) -> bool:
        return self.skill.status.participates_in_trigger


class SkillReviewService:
    """TENANT 级审核流应用服务（提交 / 批准 / 驳回 / 撤回 + 待审队列）。"""

    def __init__(self, *, skills: SkillService,
                 reviews: SkillReviewRepository,
                 repository: AgentSkillRepository):
        self._skills = skills
        self._reviews = reviews
        self._repository = repository

    # ------------------------------------------------------------ 命令侧

    def submit(self, skill_id: str, *, owner_id: int, tenant_id: str,
               permissions: Iterable[str] = (),
               is_admin: bool = False) -> ReviewResult:
        """``DRAFT → PENDING_REVIEW``：内容冻结，等管理员审批。

        提交即跑完整校验 + 注入检测 + 发布门槛：不达标的版本不能被送进
        审批队列（避免审批人替提交人兜底校验）。
        """
        ensure_tenant_admin(permissions=permissions, is_admin=is_admin)
        row = self._skills.tenant_review_row(
            skill_id, owner_id=owner_id, tenant_id=tenant_id)
        ensure_review_scope(row.scope)
        target = target_status(row.status, SkillReviewAction.SUBMIT)
        # 先校验再迁移：校验不过时状态一步都不动
        _skill, gate = self._skills.evaluate_publish(
            row, permissions=permissions)
        if not gate.passed:
            raise SkillGateFailed(
                '发布门槛未通过，不能提交审核：' + '；'.join(gate.failures),
                issues=[])
        if not self._repository.transition_if(
                row.id, [SkillStatus.DRAFT], target):
            raise SkillStatusInvalid(
                'Skill 状态已变化（可能已被并发提交），请刷新后重试')
        review = self._skills.append_review(
            self._skills.require_row(row.id),
            action=SkillReviewAction.SUBMIT,
            status_from=SkillStatus.DRAFT, status_to=target,
            reviewer_id=owner_id)
        self._skills.refresh_registry()
        return ReviewResult(
            skill=self._skills.get(
                row.id, owner_id=owner_id, tenant_id=tenant_id,
                permissions=permissions),
            review=review, gate=gate)

    def decide(self, skill_id: str, decision: SkillReviewDecision, *,
               owner_id: int, tenant_id: str,
               permissions: Iterable[str] = (),
               is_admin: bool = False,
               reason: str = '') -> ReviewResult:
        """``PENDING_REVIEW → ACTIVE``（批准）/ ``→ DRAFT``（驳回）。"""
        ensure_tenant_admin(permissions=permissions, is_admin=is_admin)
        row = self._skills.tenant_review_row(
            skill_id, owner_id=owner_id, tenant_id=tenant_id)
        ensure_review_scope(row.scope)
        action = decision.action
        target = target_status(row.status, action)
        reason = (reason or '').strip()
        if action.requires_reason and not reason:
            # 驳回无原因等于无声打回：必填（接口层 400）
            raise SkillServiceError('驳回必须填写原因 reason')
        self._ensure_not_self_review(row, actor_id=owner_id)

        gate = GateResult(golden_tasks=0, passed=True)
        if action is SkillReviewAction.APPROVE:
            # 审批时复跑同一套校验：防审批期间规则或权限变化被漏掉
            _skill, gate = self._skills.evaluate_publish(
                row, permissions=permissions)
            if not gate.passed:
                raise SkillGateFailed(
                    '批准前复跑发布门槛未通过：' + '；'.join(gate.failures),
                    issues=[])
        if not self._repository.transition_if(
                row.id, [SkillStatus.PENDING_REVIEW], target):
            raise SkillStatusInvalid(
                '该版本已被其他管理员处理（或已撤回），本次决策不生效')
        review = self._skills.append_review(
            self._skills.require_row(row.id), action=action,
            status_from=SkillStatus.PENDING_REVIEW, status_to=target,
            reviewer_id=owner_id, reason=reason)
        self._skills.refresh_registry()
        return ReviewResult(
            skill=self._skills.get(
                row.id, owner_id=owner_id, tenant_id=tenant_id,
                permissions=permissions),
            review=review, gate=gate)

    def withdraw(self, skill_id: str, *, owner_id: int, tenant_id: str,
                 permissions: Iterable[str] = (),
                 is_admin: bool = False) -> ReviewResult:
        """``PENDING_REVIEW → DRAFT``：撤回后可继续修改再提交。"""
        ensure_tenant_admin(permissions=permissions, is_admin=is_admin)
        row = self._skills.tenant_review_row(
            skill_id, owner_id=owner_id, tenant_id=tenant_id)
        ensure_review_scope(row.scope)
        target = target_status(row.status, SkillReviewAction.WITHDRAW)
        if not self._repository.transition_if(
                row.id, [SkillStatus.PENDING_REVIEW], target):
            raise SkillStatusInvalid(
                '只有 PENDING_REVIEW 的版本可以撤回')
        review = self._skills.append_review(
            self._skills.require_row(row.id),
            action=SkillReviewAction.WITHDRAW,
            status_from=SkillStatus.PENDING_REVIEW, status_to=target,
            reviewer_id=owner_id)
        self._skills.refresh_registry()
        return ReviewResult(
            skill=self._skills.get(
                row.id, owner_id=owner_id, tenant_id=tenant_id,
                permissions=permissions),
            review=review, gate=GateResult(golden_tasks=0, passed=True))

    # ------------------------------------------------------------ 查询侧

    def pending_queue(self, *, tenant_id: str,
                      status: SkillStatus = SkillStatus.PENDING_REVIEW,
                      limit: int = 100) -> List[AgentSkillReview]:
        """本租户当前处于 ``status`` 的 Skill 的最近一条迁移记录。

        同一 Skill 的多条历史记录只保留最新一条（仓储按 ``created_at``
        降序返回），队列里一条 Skill 只出现一次。
        """
        rows = self._reviews.list_current(status, tenant_id=tenant_id,
                                          limit=limit)
        seen = set()
        items: List[AgentSkillReview] = []
        for row in rows:
            if row.skill_id in seen:
                continue
            seen.add(row.skill_id)
            items.append(row)
        return items

    def history(self, skill_id: str, *, owner_id: int,
                tenant_id: str) -> List[AgentSkillReview]:
        """单个 Skill 的完整审批链（跨租户 / 非本人一律 404）。"""
        row = self._skills.tenant_review_row(
            skill_id, owner_id=owner_id, tenant_id=tenant_id)
        return self._reviews.list_for_skill(row.id)

    # ------------------------------------------------------------ internals

    def _ensure_not_self_review(self, row: AgentSkill, *,
                                actor_id: int) -> None:
        """创建人 / 提交人不得审批同一个版本（自审自批 = 无第二人复核）。

        INT-2594 P1：只拦创建人不够 —— 管理员 B 可以提交管理员 A 的草稿，
        再以 B 身份批准，A 全程不参与，第二人复核同样失效。因此还要拒绝
        「最近一次提交该版本的人」（``SUBMIT`` 审计行的 ``reviewer_id``）。

        ``submit`` 是「先条件迁移、后追加审计」，同一人并发提交 + 审批时
        仍有「状态已 PENDING_REVIEW、提交行尚未落库」的窗口：查不到当前
        版本的提交人时按 fail-closed 拒绝（可刷新重试），不放行无法核对
        第二人复核的决策。
        """
        creators = {value for value in (row.created_by, row.owner_id)
                    if value is not None}
        if actor_id in creators:
            raise SkillSelfReviewForbidden(
                '创建人不得审批自己提交的 Skill 版本：请由其他租户管理员审批')
        submitter = self._submitted_by(row)
        if submitter is None:
            raise SkillStatusInvalid(
                '审核链缺少本次提交记录，请刷新后重试')
        if actor_id == submitter:
            raise SkillSelfReviewForbidden(
                '提交人不得审批自己提交的 Skill 版本：请由其他租户管理员审批')

    def _submitted_by(self, row: AgentSkill) -> Optional[int]:
        """该版本最近一次提交人（无当前版本的 ``SUBMIT`` 记录返回 ``None``）。"""
        if self._reviews is None:
            return None
        submitter: Optional[int] = None
        for review in self._reviews.list_for_skill(row.id):  # created_at 升序
            if (review.action is SkillReviewAction.SUBMIT
                    and review.version == row.version):
                submitter = review.reviewer_id
        return submitter


__all__ = ['ReviewResult', 'SkillReviewService']
