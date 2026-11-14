# -*- coding: utf-8 -*-
"""自定义 Skill 应用服务（INT-2549 §4.4）。

编排职责（不碰 SQL / 文件系统细节，全部经 domain 端口）：

- CRUD 与版本：``create`` / ``update`` / ``list`` / ``get`` / ``delete``；
- 生命周期：``publish``（发布门槛）/ ``disable``；
- 入口：在线编辑（PUT）、zip 导入导出、fork、对话沉淀（建议由编排层产出，
  用户确认后走 ``create``）；
- 落库前逐项校验：名称 / 必填 / 正文节与行数 / 体积 / 路径 / 工具 / 权限 /
  凭证 / 内网地址 / 二进制；发布额外做注入检测；
- run 回放：以 ``agent_run_skill`` + ``agent_skill_version`` 为准。

校验复用 ``skill_registry.validate_skill``（与启动装载同一实现），不另写一套。
"""
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from agent_service.application.skill_guard import GuardIssue, SkillGuard
from agent_service.application.skill_registry import (
    SkillIssue, SkillRegistry, validate_skill,
)
from agent_service.application.skill_trigger import matches as trigger_matches
from agent_service.domain.enums import (
    SkillIssueCode, SkillIssueSeverity, SkillReviewAction, SkillScope,
    SkillStatus,
)
from agent_service.domain.exceptions import (
    SkillImportInvalid, SkillInjectionDetected, SkillNameConflict,
    SkillNotFound, SkillPermissionEscalation, SkillServiceError,
    SkillStatusInvalid,
)
from agent_service.domain.model.agent_skill import (
    AgentSkill, AgentSkillReview, AgentSkillVersion,
)
from agent_service.domain.model.skill import (
    FIELD_ALLOWED_TOOLS, FIELD_BUDGETS, FIELD_DESCRIPTION, FIELD_NAME,
    FIELD_PERMISSIONS, FIELD_VERSION, REQUIRED_SECTIONS,
    SKILL_NAME_PATTERN, WILDCARD_PERMISSION, Skill, SkillMeta,
)
from agent_service.domain.ports.golden_tasks import GoldenTaskProvider
from agent_service.domain.ports.skill_repository import SkillResourceStore
from agent_service.domain.repositories import (
    AgentRunSkillRepository, AgentSkillRepository, SkillReviewRepository,
)
from agent_service.domain.services.skill_review_state import target_status
from agent_service.domain.services.skill_tenancy import ensure_tenant_admin
from agent_service.domain.services.skill_visibility import (
    merge_skill_layers, to_domain_skill,
)
from shared.skill_package import (
    DEFAULT_MAX_UPLOAD_BYTES, PackageIssueCode, SkillPackageError,
    SkillPackageLimits, build_skill_package, read_skill_package,
)

logger = logging.getLogger(__name__)

PLATFORM_ID_PREFIX = 'platform:'


@dataclass(frozen=True)
class SkillSettings:
    """Skill 写入口径（配置化，禁止魔法值）。"""

    max_body_lines: int = 500
    max_skill_bytes: int = 64 * 1024
    max_resource_bytes: int = 512 * 1024
    max_package_bytes: int = 5 * 1024 * 1024
    # 上传（压缩前）体积上限：接口层 / 网关在读入内存前按同一口径拒绝
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_entries: int = 200
    max_compression_ratio: int = 100
    publish_min_golden_tasks: int = 3
    resource_prefix: str = 'agent-skill'

    def package_limits(self) -> SkillPackageLimits:
        return SkillPackageLimits(
            max_entries=self.max_entries,
            max_skill_bytes=self.max_skill_bytes,
            max_resource_bytes=self.max_resource_bytes,
            max_total_bytes=self.max_package_bytes,
            max_compression_ratio=self.max_compression_ratio,
            max_upload_bytes=self.max_upload_bytes)


@dataclass(frozen=True)
class GateResult:
    golden_tasks: int
    passed: bool
    failures: List[str] = field(default_factory=list)
    note: str = '命中拒绝、未命中不等于安全'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'golden_tasks': self.golden_tasks,
            'passed': self.passed,
            'failures': list(self.failures),
            'note': self.note,
        }


@dataclass(frozen=True)
class PublishResult:
    skill: AgentSkill
    gate: GateResult

    @property
    def participates_in_trigger(self) -> bool:
        return self.skill.status.participates_in_trigger


@dataclass(frozen=True)
class SkillView:
    """列表 / 详情项（接口层直接序列化）。"""

    id: str
    scope: SkillScope
    name: str
    description: str
    version: str
    status: SkillStatus
    content_hash: str
    masked_by: Optional[str] = None
    owner_id: Optional[int] = None
    tenant_id: Optional[str] = None
    created_by: Optional[int] = None
    updated_at: Optional[datetime] = None
    allowed_tools: Tuple[str, ...] = ()
    permissions: Tuple[str, ...] = ()
    owner: str = ''
    budgets: Dict[str, int] = field(default_factory=dict)
    issues: Tuple[SkillIssue, ...] = ()


@dataclass(frozen=True)
class SkillDraftPayload:
    """新建 / 保存的请求体（服务端身份字段不在此处）。

    字段为 ``None`` 表示「本次不改动」（PUT 语义）：保存时沿用当前版本内容，
    避免只改正文却把资源整包清空。
    """

    name: Optional[str] = None
    description: Optional[str] = None
    frontmatter: Optional[Mapping[str, Any]] = None
    body: Optional[str] = None
    resources: Optional[Mapping[str, str]] = None


class SkillService:
    def __init__(self, *,
                 repository: AgentSkillRepository,
                 run_skills: AgentRunSkillRepository,
                 registry: SkillRegistry,
                 resource_store: SkillResourceStore,
                 golden_tasks: Optional[GoldenTaskProvider] = None,
                 guard: Optional[SkillGuard] = None,
                 known_tools: Optional[Callable[[], Iterable[str]]] = None,
                 settings: Optional[SkillSettings] = None,
                 platform_resources: Optional[Callable[[Any], Mapping[str, str]]] = None,
                 reviews: Optional[SkillReviewRepository] = None,
                 review_clock: Optional[Callable[[], datetime]] = None):
        self._repository = repository
        self._run_skills = run_skills
        self._registry = registry
        self._resources = resource_store
        self._golden_tasks = golden_tasks
        self._guard = guard or SkillGuard()
        self._known_tools = known_tools
        self._settings = settings or SkillSettings()
        # 平台 Skill 的资源文本读取（fork 时随草稿复制；infrastructure 注入）
        self._platform_resources = platform_resources
        # INT-2551：TENANT 级停用要落一条审核链审计（谁、哪版、什么理由）；
        # 仓储只追加。未注入时拒绝 TENANT 停用，不静默丢审计。
        self._reviews = reviews
        self._review_clock = review_clock or _now

    # ------------------------------------------------------------ 查询

    def list(self, *, owner_id: int, tenant_id: str,
             permissions: Iterable[str] = (),
             scope: Optional[SkillScope] = None,
             status: Optional[SkillStatus] = None) -> List[SkillView]:
        """本人可见的 Skill 列表（平台层 + 自定义层，带遮蔽标注）。"""
        granted = set(permissions or ())
        platform = [
            skill for skill in self._platform_skills()
            if _granted(skill, granted)
            and (scope is None or skill.scope is scope)
            and (status is None or skill.status is status)
        ]
        rows = self._repository.list_visible(
            tenant_id=tenant_id, owner_id=owner_id,
            scopes=[scope] if scope else None,
            statuses=[status] if status else None)
        active_rows = [row for row in rows
                       if row.status.participates_in_trigger]
        active_skills = [self._domain_skill(row) for row in active_rows]
        effective, masked = merge_skill_layers(
            platform + active_skills, owner_id=owner_id, tenant_id=tenant_id,
            active_only=True)
        items = [self._view_from_skill(skill) for skill in effective]
        items.extend(self._view_from_skill(skill) for skill in masked)
        # DRAFT / DISABLED 不参与合并，但列表要能看到（筛选已由仓储层完成）
        for row in rows:
            if row.status.participates_in_trigger:
                continue
            items.append(self._view_from_row(row))
        items.sort(key=lambda item: (item.scope is SkillScope.PLATFORM,
                                     item.name))
        return items

    def get(self, skill_id: str, *, owner_id: int, tenant_id: str,
            permissions: Iterable[str] = ()) -> SkillView:
        row = self._owned_row(skill_id, owner_id=owner_id, tenant_id=tenant_id)
        if row is not None:
            return self._view_from_row(row)
        skill = self._platform_skill(skill_id)
        if skill is None or not _granted(skill, set(permissions or ())):
            raise SkillNotFound(skill_id)
        return self._view_from_skill(skill)

    def versions(self, skill_id: str, *, owner_id: int,
                 tenant_id: str) -> List[AgentSkillVersion]:
        row = self._owned_row(skill_id, owner_id=owner_id, tenant_id=tenant_id)
        if row is None:
            raise SkillNotFound(skill_id)
        return self._repository.list_versions(row.id)

    def package_limits(self) -> SkillPackageLimits:
        """zip 包限制（接口层上传体积与包解析共用同一口径）。"""
        return self._settings.package_limits()

    # ------------------------------------------------------------ 写入口

    def create(self, payload: SkillDraftPayload, *, owner_id: int,
               tenant_id: str, permissions: Iterable[str] = (),
               created_by: Optional[int] = None,
               scope: SkillScope = SkillScope.USER,
               is_admin: bool = False) -> SkillView:
        """新建草稿（在线编辑的 POST；也用于「沉淀建议」用户确认后落库）。

        INT-2551：``scope=TENANT`` 时是「同租户共享」的草稿，写入口要求
        租户管理员双条件（权限码 + 角色），``tenant_id`` 由服务端按登录身份
        填、``owner_id`` 记创建人；``PLATFORM`` 层只读，不接受创建。
        """
        if scope is SkillScope.TENANT:
            ensure_tenant_admin(permissions=permissions, is_admin=is_admin)
        elif scope is not SkillScope.USER:
            raise SkillServiceError('PLATFORM 层只读，不能创建 Skill')
        return self._create(payload, owner_id=owner_id, tenant_id=tenant_id,
                            permissions=permissions,
                            created_by=created_by or owner_id, scope=scope)

    def update(self, skill_id: str, payload: SkillDraftPayload, *,
               owner_id: int, tenant_id: str,
               permissions: Iterable[str] = (),
               is_admin: bool = False) -> SkillView:
        """保存（version +1）。ACTIVE Skill 编辑后回到 DRAFT，需重新发布。

        INT-2551：``PENDING_REVIEW`` 期间内容冻结（``SKILL_STATUS_INVALID``），
        必须先撤回；TENANT 行仅租户管理员可改（租户内任意一条，不限创建人）。

        INT-2594 P2：``TENANT`` 的 ``ACTIVE`` 保存走状态机显式 ``EDIT`` 边
        （``ACTIVE → DRAFT`` 并落一条审核审计），``DISABLED`` 无出边直接 409
        —— 不允许 PUT 静默越过审核状态机、也不允许把已批准版本打回草稿后
        不留痕迹。迁移 / 版本行 / 当前行 / 审计是同一事务（``apply_edit``）
        的四件事，任一步失败整体回滚；资源写排在事务之前，失败时状态不动。
        资源键带本次请求的一次性段（见 ``_store_resources``），并发编辑的
        落败方不会覆盖胜出版本已提交的资源字节。
        """
        row = self._owned_row(skill_id, owner_id=owner_id,
                              tenant_id=tenant_id, writable=True,
                              permissions=permissions, is_admin=is_admin)
        if row is None:
            raise SkillNotFound(skill_id)
        if row.status.is_frozen:
            raise SkillStatusInvalid(
                f'状态 {row.status.value} 期间内容冻结，不能保存；'
                '请先撤回审核（POST /skills/{id}/withdraw）')
        # 状态机前置校验（不写库）：TENANT 已发布版本只能经显式 EDIT 迁移
        edit_target = self._tenant_edit_target(row)
        if payload.name and payload.name != row.name:
            self._assert_name_available(
                payload.name, scope=row.scope, owner_id=owner_id,
                tenant_id=tenant_id, exclude_id=row.id)
        current = self._repository.get_version(row.id, row.version)
        name = payload.name or row.name
        description = (payload.description
                       if payload.description is not None else row.description)
        frontmatter = dict(payload.frontmatter
                           if payload.frontmatter is not None
                           else (row.frontmatter or {}))
        # 名称 / 描述以请求体为准写回 frontmatter：防止「校验用一个名字、
        # 导出/导入用另一个名字」，也避免绕过同名冲突判定。
        frontmatter[FIELD_NAME] = name
        frontmatter[FIELD_DESCRIPTION] = description
        body = (normalize_body(payload.body) if payload.body is not None
                else (current.body if current is not None else ''))
        if payload.resources is None:
            resources = self._current_resources(row)
        else:
            resources = self._prepare_resources(row.id, payload.resources)
        skill = self._build_skill(name, description, frontmatter, body)
        self._validate_for_save(
            skill, frontmatter=frontmatter, body=body,
            permissions=permissions, resources=resources)
        version = str(int(row.version) + 1)
        hash_value = content_hash(skill.meta, frontmatter, body)
        # INT-2594 返工：资源写是可能失败且不可回滚的外部写，必须排在状态
        # 迁移之前 —— 失败时状态 / 版本 / 审计一步都没动，不会把已发布版本
        # 留在「DRAFT 且没有 EDIT 审计」的中间态（孤儿对象不对外可见，无害）。
        stored = self._store_resources(row.id, version, resources)
        edited = AgentSkillVersion(
            skill_id=row.id, version=version, content_hash=hash_value,
            body=body, frontmatter=frontmatter, resources=stored,
            created_by=owner_id)
        if edit_target is not None:
            # 条件迁移 + 版本行 + 当前行 + 审计收在一个仓储事务里：任一步
            # 失败整体回滚（状态保持原值、版本指针不动、无 EDIT 审计），
            # 也不会留下孤儿版本号挡住重试；并发两次编辑只有一次命中。
            applied = self._repository.apply_edit(
                row.id, from_status=row.status,
                row_fields=dict(
                    name=name, description=description, version=version,
                    status=SkillStatus.DRAFT.value, content_hash=hash_value,
                    frontmatter_json=dict(frontmatter), resources=stored,
                    updated_at=_now()),
                version=edited,
                # 审计记录的是被编辑的那一版（迁移的起点），产出的是 version +1
                review=self._build_review(
                    row, action=SkillReviewAction.EDIT,
                    status_from=row.status, status_to=edit_target,
                    reviewer_id=owner_id))
            if not applied:
                raise SkillStatusInvalid(
                    'Skill 状态已被其他请求变更，请刷新后重试')
        else:
            self._repository.add_version(edited)
            self._repository.update(
                row.id, name=name, description=description, version=version,
                status=SkillStatus.DRAFT.value, content_hash=hash_value,
                frontmatter_json=dict(frontmatter), resources=stored,
                updated_at=_now())
        self._refresh_registry()
        return self._view_from_row(self._require_row(row.id))

    def _tenant_edit_target(self, row: AgentSkill) -> Optional[SkillStatus]:
        """TENANT 已发布版本的编辑目标状态（INT-2594 P2）。

        ``DRAFT`` 保存是原地修改，不进状态机；``ACTIVE`` 必须经显式
        ``EDIT`` 边回 ``DRAFT``（随后重新提交 + 审批）；``DISABLED`` 没有
        出边，``target_status`` 抛 ``SKILL_STATUS_INVALID``（409）。

        ``EDIT`` 审计与状态迁移由 ``repository.apply_edit`` 在同一事务内
        落库，因此这里不再单独要求审核链仓储已装配（不会再静默丢审计）。
        """
        if row.scope is not SkillScope.TENANT or row.status is SkillStatus.DRAFT:
            return None
        return target_status(row.status, SkillReviewAction.EDIT)

    def disable(self, skill_id: str, *, owner_id: int, tenant_id: str,
                permissions: Iterable[str] = (),
                is_admin: bool = False,
                reason: str = '') -> SkillView:
        """强制停用：立即从 L1 / 激活候选消失；在办 run 按快照继续。

        INT-2551：TENANT 行租户管理员可停用本租户**任意**一条（不限创建人），
        且必须落一条 ``DISABLE`` 审计（谁、哪版、什么理由）。
        """
        row = self._owned_row(skill_id, owner_id=owner_id,
                              tenant_id=tenant_id, writable=True,
                              permissions=permissions, is_admin=is_admin)
        if row is None:
            raise SkillNotFound(skill_id)
        if row.status is not SkillStatus.DISABLED:
            if row.scope is SkillScope.TENANT:
                target_status(row.status, SkillReviewAction.DISABLE)
                if self._reviews is None:
                    raise SkillStatusInvalid(
                        'TENANT 级停用缺少审计仓储，拒绝执行（不静默丢审计）')
            status_from = row.status
            # 条件迁移：并发的两次停用只有一次生效，审计也只落一条
            if not self._repository.transition_if(
                    row.id, [status_from], SkillStatus.DISABLED):
                raise SkillStatusInvalid('Skill 状态已被其他请求变更，请刷新后重试')
            if row.scope is SkillScope.TENANT:
                self._append_review(
                    row, action=SkillReviewAction.DISABLE,
                    status_from=status_from, status_to=SkillStatus.DISABLED,
                    reviewer_id=owner_id, reason=reason)
            self._refresh_registry()
        return self._view_from_row(self._require_row(row.id))

    def delete(self, skill_id: str, *, owner_id: int, tenant_id: str,
               permissions: Iterable[str] = (),
               is_admin: bool = False) -> None:
        """删除当前行；版本行保留（历史 run 回放仍可读到旧内容）。

        TENANT 共享 Skill 不提供删除：共享资产的退出机制是「强制停用」，
        删除会丢掉同租户可见性语义（审计链虽在，但列表里凭空消失）。
        """
        row = self._owned_row(skill_id, owner_id=owner_id,
                              tenant_id=tenant_id, writable=True,
                              permissions=permissions, is_admin=is_admin)
        if row is None:
            raise SkillNotFound(skill_id)
        if row.scope is SkillScope.TENANT:
            raise SkillStatusInvalid(
                'TENANT 共享 Skill 不支持删除，请使用停用（disable）')
        self._repository.delete(row.id)
        self._refresh_registry()

    def publish(self, skill_id: str, *, owner_id: int, tenant_id: str,
                permissions: Iterable[str] = (),
                is_admin: bool = False) -> PublishResult:
        """发布门槛：≥3 条 golden tasks 且触发判定通过 → ACTIVE。

        注入检测在此额外执行：命中即拒绝（草稿仍保留），不静默降级。

        INT-2551：``TENANT`` 级**没有**这条旁路 —— 必须走
        ``submit-review`` + 管理员审批，否则等于绕过审核流直接 ACTIVE。
        """
        row = self._owned_row(skill_id, owner_id=owner_id,
                              tenant_id=tenant_id, writable=True,
                              permissions=permissions, is_admin=is_admin)
        if row is None:
            raise SkillNotFound(skill_id)
        if row.scope is SkillScope.TENANT:
            raise SkillStatusInvalid(
                'TENANT 级 Skill 发布须走审核流：'
                'POST /skills/{id}/submit-review 后由其他租户管理员审批')
        if row.status is SkillStatus.ACTIVE:
            raise SkillStatusInvalid('Skill 已是 ACTIVE，无需重复发布')
        if row.status is SkillStatus.DISABLED:
            raise SkillStatusInvalid('DISABLED 的 Skill 不能直接发布，请先另存为草稿')
        skill, gate = self.evaluate_publish(row, permissions=permissions)
        if not gate.passed:
            return PublishResult(skill=row, gate=gate)
        self._repository.update(
            row.id, status=SkillStatus.ACTIVE.value, updated_at=_now())
        self._refresh_registry()
        return PublishResult(skill=self._require_row(row.id), gate=gate)

    def evaluate_publish(self, row: AgentSkill, *,
                         permissions: Iterable[str] = ()
                         ) -> Tuple[Skill, GateResult]:
        """保存期校验复查 + 注入检测 + 发布门槛（发布 / 提交审核 / 批准共用）。

        INT-2551：TENANT 级提交审核与批准都要跑**完全相同**的这一套，
        不复制、不放宽任何一条规则；只在审批点复跑，防止审批期间规则或
        权限变化被漏掉。
        """
        version = self._repository.get_version(row.id, row.version)
        body = version.body if version is not None else ''
        frontmatter = (version.frontmatter if version is not None
                       else row.frontmatter)
        skill = self._build_skill(row.name, row.description, frontmatter, body)
        # 保存期校验复查（结构 / 工具 / 权限），发布不跳过
        resources = self._current_resources(row)
        self._validate_for_save(
            skill, frontmatter=frontmatter, body=body,
            permissions=permissions, resources=resources)
        # 发布额外做注入检测：正文、描述（经 L1 进系统提示）与文本资源
        # （经 L3 进上下文）都算不可信内容（复核 P2）。
        injection = self._guard.check_injection(body)
        if row.description:
            injection.extend(self._guard.check_injection(
                row.description, field='description'))
        for path, text in _text_resources(resources).items():
            injection.extend(self._guard.check_injection(
                text, field=f'resources.{path}'))
        if injection:
            raise SkillInjectionDetected(
                '正文 / 描述 / 资源命中注入规则，拒绝发布'
                '（草稿仍可保存，ACTIVE 不生效）',
                issues=[_guard_issue_to_skill(item, row.name)
                        for item in injection])
        return skill, self._evaluate_gate(row)

    def fork(self, source_id: str, *, owner_id: int, tenant_id: str,
             permissions: Iterable[str] = (), name: str = '',
             description: str = '') -> SkillView:
        """从内置 / 可见 Skill fork 出本人的草稿（默认 ``<name>-copy``）。"""
        source = self._resolve_visible_skill(
            source_id, owner_id=owner_id, tenant_id=tenant_id,
            permissions=permissions)
        new_name = (name or f'{source.name}-copy').strip()
        self._assert_name_available(new_name, owner_id=owner_id,
                                    tenant_id=tenant_id)
        version = None
        if source.is_custom:
            row = self._repository.get(source.skill_id)
            if row is None:
                raise SkillNotFound(source_id)
            version = self._repository.get_version(row.id, row.version)
        frontmatter = dict(version.frontmatter if version is not None
                           else _frontmatter_from_meta(source.meta))
        frontmatter[FIELD_NAME] = new_name
        frontmatter[FIELD_DESCRIPTION] = description or source.description
        resources = self._load_source_resources(source, version)
        payload = SkillDraftPayload(
            name=new_name,
            description=description or source.description,
            frontmatter=frontmatter, body=source.body, resources=resources)
        return self._create(payload, owner_id=owner_id, tenant_id=tenant_id,
                            permissions=permissions, created_by=owner_id)

    # ------------------------------------------------------------ 导入 / 导出

    def import_package(self, data: bytes, *, owner_id: int, tenant_id: str,
                       permissions: Iterable[str] = ()) -> SkillView:
        """zip 导入（与导出同一包结构；解析在内存，不落盘）。"""
        try:
            package = read_skill_package(
                data, limits=self._settings.package_limits())
        except SkillPackageError as exc:
            raise SkillImportInvalid(
                f'导入包非法：{exc.message}',
                issues=[SkillIssue(
                    code=_package_code(exc.code), severity=SkillIssueSeverity.ERROR,
                    skill='', path='', message=exc.message, field='package')])
        frontmatter, body = _parse_skill_md(package.skill_md)
        name = str(frontmatter.get(FIELD_NAME) or '').strip()
        description = str(frontmatter.get(FIELD_DESCRIPTION) or '').strip()
        resources = {path: payload.decode('utf-8')
                     for path, payload in package.resources.items()
                     if _is_text(payload)}
        payload = SkillDraftPayload(
            name=name, description=description, frontmatter=frontmatter,
            body=body, resources=resources)
        return self._create(payload, owner_id=owner_id, tenant_id=tenant_id,
                            permissions=permissions, created_by=owner_id)

    def export_package(self, skill_id: str, *, owner_id: int, tenant_id: str,
                       permissions: Iterable[str] = ()) -> Tuple[str, bytes]:
        """导出 zip（根级 ``SKILL.md`` + 资源），返回 ``(filename, bytes)``。"""
        skill = self._resolve_visible_skill(
            skill_id, owner_id=owner_id, tenant_id=tenant_id,
            permissions=permissions)
        if not skill.is_custom:
            skill_md = build_skill_md(
                _frontmatter_from_meta(skill.meta), skill.body)
            return f'{skill.name}.zip', build_skill_package(
                skill_md, limits=self._settings.package_limits())
        row = self._repository.get(skill.skill_id)
        if row is None:
            raise SkillNotFound(skill_id)
        version = self._repository.get_version(row.id, row.version)
        if version is None:
            raise SkillNotFound(skill_id)
        resources = {
            path: self._resources.get(key)
            for path, key in (version.resources or {}).items()
        }
        skill_md = build_skill_md(version.frontmatter, version.body)
        return f'{row.name}.zip', build_skill_package(
            skill_md, resources, limits=self._settings.package_limits())

    # ------------------------------------------------------------ run 回放

    def replay(self, run_id: str, *, owner_id: int,
               tenant_id: str) -> List[Dict[str, Any]]:
        """按 run 快照回放：Skill 后续修改不影响历史 run。"""
        snapshots = self._run_skills.list_by_run(run_id)
        items: List[Dict[str, Any]] = []
        for snapshot in snapshots:
            item: Dict[str, Any] = {
                'skill_id': snapshot.skill_id,
                'version': snapshot.version,
                'content_hash': snapshot.content_hash,
                'activated_at': (snapshot.activated_at.isoformat()
                                 if snapshot.activated_at else None),
                'scope': SkillScope.PLATFORM.value,
                'name': '',
                'body': '',
                'resolved': False,
                'content_hash_matches': False,
            }
            if snapshot.skill_id.startswith(PLATFORM_ID_PREFIX):
                skill = self._registry.get(
                    snapshot.skill_id[len(PLATFORM_ID_PREFIX):])
                if skill is not None:
                    item.update(name=skill.name, body=skill.body,
                                resolved=True,
                                content_hash_matches=(
                                    skill.content_hash == snapshot.content_hash))
                items.append(item)
                continue
            row = self._repository.get(snapshot.skill_id)
            version = self._repository.get_version(
                snapshot.skill_id, snapshot.version)
            if row is not None:
                item['scope'] = row.scope.value
                item['name'] = row.name
            if version is not None:
                item.update(body=version.body, resolved=True,
                            content_hash_matches=(
                                version.content_hash == snapshot.content_hash))
            items.append(item)
        return items

    def snapshot_skill(self, run_id: str):
        """按 run 快照还原领域 ``Skill``（在办 run 的 L2 / allowed-tools）。

        停用 / 修改 / 删除都不影响已开始 run：内容来自 ``agent_skill_version``，
        不重查可见性（§4.4「安全与生命周期」）。无快照返回 ``None``。
        """
        from agent_service.domain.model.skill import Skill as _Skill
        from agent_service.domain.services.skill_visibility import (
            meta_from_frontmatter,
        )
        snapshots = self._run_skills.list_by_run(run_id)
        if not snapshots:
            return None
        snapshot = snapshots[-1]
        if snapshot.skill_id.startswith(PLATFORM_ID_PREFIX):
            skill = self._registry.get(
                snapshot.skill_id[len(PLATFORM_ID_PREFIX):])
            if skill is None:
                return None
            if snapshot.content_hash and skill.content_hash != snapshot.content_hash:
                logger.warning('平台 Skill 内容与 run 快照不一致：%s',
                               snapshot.skill_id)
            return skill
        version = self._repository.get_version(
            snapshot.skill_id, snapshot.version)
        if version is None:
            return None
        row = self._repository.get(snapshot.skill_id)
        frontmatter = dict(version.frontmatter or {})
        name = (row.name if row is not None
                else str(frontmatter.get(FIELD_NAME) or ''))
        if name and FIELD_NAME not in frontmatter:
            frontmatter[FIELD_NAME] = name
        from dataclasses import replace as _replace
        meta = meta_from_frontmatter(frontmatter)
        if snapshot.version:
            meta = _replace(meta, version=str(snapshot.version))
        return _Skill(
            meta=meta,
            body=version.body or '', path=f'agent_skill/{snapshot.skill_id}',
            skill_id=snapshot.skill_id,
            scope=(row.scope if row is not None else SkillScope.USER),
            status=(row.status if row is not None else SkillStatus.DISABLED),
            content_hash=version.content_hash or snapshot.content_hash,
            resources=dict(version.resources or {}),
            owner_id=row.owner_id if row is not None else None,
            tenant_id=row.tenant_id if row is not None else None)

    # ------------------------------------------------------------ internals

    def _create(self, payload: SkillDraftPayload, *, owner_id: int,
                tenant_id: str, permissions: Iterable[str],
                created_by: Optional[int],
                scope: SkillScope = SkillScope.USER) -> SkillView:
        name = (payload.name or '').strip()
        description = (payload.description or '').strip()
        frontmatter = dict(payload.frontmatter or {})
        # 名称 / 描述以请求体为准写回 frontmatter（见 update 处同一口径）
        frontmatter[FIELD_NAME] = name
        frontmatter[FIELD_DESCRIPTION] = description
        self._assert_name_available(name, scope=scope, owner_id=owner_id,
                                    tenant_id=tenant_id)
        body = normalize_body(payload.body or '')
        resources = self._prepare_resources('', payload.resources)
        skill = self._build_skill(name, description, frontmatter, body)
        self._validate_for_save(
            skill, frontmatter=frontmatter, body=body,
            permissions=permissions, resources=resources)

        skill_id = str(uuid.uuid4())
        version = '1'
        hash_value = content_hash(skill.meta, frontmatter, body)
        stored = self._store_resources(skill_id, version, resources)
        now = _now()
        self._repository.add_version(AgentSkillVersion(
            skill_id=skill_id, version=version, content_hash=hash_value,
            body=body, frontmatter=frontmatter, resources=stored,
            created_by=created_by, created_at=now))
        row = self._repository.add(AgentSkill(
            id=skill_id, scope=scope, name=name,
            description=description, version=version,
            status=SkillStatus.DRAFT, content_hash=hash_value,
            frontmatter=frontmatter, resources=stored,
            tenant_id=tenant_id, owner_id=owner_id, created_by=created_by,
            created_at=now, updated_at=now))
        self._refresh_registry()
        return self._view_from_row(row)

    def _build_skill(self, name: str, description: str,
                     frontmatter: Mapping[str, Any], body: str) -> Skill:
        meta = SkillMeta(
            name=name, description=description,
            version=str(frontmatter.get(FIELD_VERSION) or ''),
            owner=str(frontmatter.get('owner') or ''),
            allowed_tools=_text_list(frontmatter.get(FIELD_ALLOWED_TOOLS)),
            permissions=_text_list(frontmatter.get(FIELD_PERMISSIONS)),
            budgets=_budget_map(frontmatter.get(FIELD_BUDGETS)),
        )
        return Skill(
            meta=meta, body=body or '', path='',
            scope=SkillScope.USER, status=SkillStatus.DRAFT,
            skill_id='', content_hash='')

    def _current_resources(self, row: AgentSkill) -> Dict[str, bytes]:
        """当前版本资源字节（发布复查 / fork 用）。"""
        version = self._repository.get_version(row.id, row.version)
        keys = ((version.resources if version is not None
                 else row.resources) or {})
        resources: Dict[str, bytes] = {}
        for path, key in keys.items():
            try:
                resources[path] = self._resources.get(key)
            except (KeyError, RuntimeError):
                logger.warning('读取 Skill 资源失败：%s', path)
        return resources

    def _validate_for_save(self, skill: Skill, *,
                           frontmatter: Mapping[str, Any], body: str,
                           permissions: Iterable[str],
                           resources: Optional[Mapping[str, bytes]] = None
                           ) -> None:
        """逐项校验（任一项 ERROR 即拒绝落库）。"""
        issues: List[SkillIssue] = []
        if not SKILL_NAME_PATTERN.match(skill.name or ''):
            issues.append(SkillIssue(
                code=SkillIssueCode.INVALID_NAME,
                severity=SkillIssueSeverity.ERROR, skill=skill.name, path='',
                message=('name 必须匹配 ^[a-z0-9][a-z0-9-]{1,63}$'
                         '（小写字母/数字/连字符，2~64 位）'),
                field='name'))
        issues.extend(validate_skill(
            skill, max_body_lines=self._settings.max_body_lines,
            required_sections=REQUIRED_SECTIONS,
            known_tools=self._known_tools, strict_tools=True))
        issues.extend(self._permission_issues(skill, permissions))
        issues.extend(_guard_issue_to_skill(item, skill.name)
                      for item in self._guard.check_structure(
                          skill_md=build_skill_md(frontmatter, body),
                          resources=dict(resources or {})))
        # 正文 / 描述 / frontmatter 自由文本都按不可信内容处理：描述不是纯
        # 展示字段，会经 L1 进系统提示（复核 P2，禁止凭证 / 内网 / 二进制）。
        text_sources: List[Tuple[str, str]] = [('body', body or '')]
        if skill.description:
            text_sources.append(('description', skill.description))
        text_sources.extend(_iter_frontmatter_texts(
            frontmatter, skip={FIELD_DESCRIPTION}))
        for field_name, text in text_sources:
            issues.extend(_guard_issue_to_skill(item, skill.name)
                          for item in self._guard.check_content(
                              text, field=field_name))
            issues.extend(_guard_issue_to_skill(item, skill.name)
                          for item in self._guard.check_binary_text(
                              text, field=field_name))
        for path, text in _text_resources(resources).items():
            issues.extend(_guard_issue_to_skill(item, skill.name)
                          for item in self._guard.check_content(
                              text, field=f'resources.{path}'))
        escalation = [i for i in issues
                      if i.code is SkillIssueCode.PERMISSION_ESCALATION]
        if escalation:
            raise SkillPermissionEscalation(
                'permissions / allowed-tools 超出当前用户权限，不得提权',
                issues=issues)
        fatal = [i for i in issues
                 if i.severity is SkillIssueSeverity.ERROR]
        if fatal:
            raise SkillServiceError(
                'Skill 校验未通过（%d 项），未落库' % len(fatal),
                issues=issues)
        if issues:
            logger.info('Skill 保存告警（%d 项，不阻断）：%s', len(issues),
                        [i.code.value for i in issues])

    def _permission_issues(self, skill: Skill,
                           permissions: Iterable[str]) -> List[SkillIssue]:
        """``permissions`` 必须 ⊆ 当前用户权限（``*`` 仅对通配用户放行）。"""
        granted = {p for p in (permissions or ()) if p}
        found: List[SkillIssue] = []
        if WILDCARD_PERMISSION in granted:
            return found
        for permission in skill.meta.permissions:
            if permission == WILDCARD_PERMISSION or permission not in granted:
                found.append(SkillIssue(
                    code=SkillIssueCode.PERMISSION_ESCALATION,
                    severity=SkillIssueSeverity.ERROR, skill=skill.name,
                    path='', field='permissions',
                    message=f'permissions 含当前用户没有的权限：{permission}'))
        return found

    def _prepare_resources(self, skill_id: str,
                           resources: Mapping[str, str]) -> Dict[str, bytes]:
        """请求体资源（相对路径 → 文本 / 字节）→ 待写入字节。"""
        payloads: Dict[str, bytes] = {}
        for path, content in (resources or {}).items():
            if isinstance(content, (bytes, bytearray)):
                payloads[path] = bytes(content)
            else:
                payloads[path] = str(content).encode('utf-8')
        return payloads

    def _store_resources(self, skill_id: str, version: str,
                         resources: Mapping[str, bytes]) -> Dict[str, str]:
        """写入资源字节，返回 ``path → 完整 key``。

        key 带**本次写请求的一次性段**（INT-2594 打回项）：资源写排在事务
        之前，同一 ``(skill_id, version)`` 的并发编辑（两人同时保存 / 同一人
        双击重试）会算出同一个 ``version``，若 key 只由 ``(skill, version,
        path)`` 决定，CAS / 版本行落败方会把自己那份字节写进胜出版本正在
        引用的键 —— 请求被 409 拒绝，却改写了已提交版本的内容。带一次性段
        后每次写各自成键，落败方写的是无人引用的孤儿对象（不可达、无害）。

        版本行存的是完整 key，历史版本照常可读，无需迁移。
        """
        prefix = self._settings.resource_prefix
        # 同一次写请求的所有资源共用一个段，便于按写入溯源
        write_token = uuid.uuid4().hex
        stored: Dict[str, str] = {}
        for path, payload in (resources or {}).items():
            key = f'{prefix}/{skill_id}/{version}/{write_token}/{path}'
            stored[path] = self._resources.put(key, payload)
        return stored

    def _load_source_resources(self, source: Skill,
                               version: Optional[AgentSkillVersion]
                               ) -> Dict[str, str]:
        if not source.is_custom and self._platform_resources is not None:
            try:
                return dict(self._platform_resources(source) or {})
            except Exception:  # noqa: BLE001 - 资源读取失败不阻断 fork
                logger.warning('读取平台 Skill 资源失败：%s', source.name,
                               exc_info=True)
                return {}
        keys = (version.resources if version is not None else source.resources) or {}
        resources: Dict[str, str] = {}
        for path, key in keys.items():
            try:
                data = self._resources.get(key)
            except (KeyError, RuntimeError):
                logger.warning('fork 读取资源失败，跳过：%s', path)
                continue
            if _is_text(data):
                resources[path] = data.decode('utf-8')
        return resources

    def _evaluate_gate(self, row: AgentSkill) -> GateResult:
        minimum = self._settings.publish_min_golden_tasks
        tasks = ()
        if self._golden_tasks is not None:
            tasks = tuple(self._golden_tasks.tasks_for(row.name) or ())
        failures: List[str] = []
        if len(tasks) < minimum:
            failures.append(
                f'golden tasks {len(tasks)} 条，未达发布门槛 {minimum} 条；'
                '当前状态保持 DRAFT，不参与自动触发')
            return GateResult(golden_tasks=len(tasks), passed=False,
                              failures=failures)
        passed, hits = trigger_matches(
            row.description, [task.query for task in tasks])
        if not passed:
            failures.append(
                '触发判定未通过（golden tasks 未命中 Skill 的 L1 触发词）；'
                '当前状态保持 DRAFT，不参与自动触发')
            return GateResult(golden_tasks=len(tasks), passed=False,
                              failures=failures)
        logger.info('Skill 发布门槛通过 name=%s golden_tasks=%d hits=%d',
                    row.name, len(tasks), len(hits))
        return GateResult(golden_tasks=len(tasks), passed=True)

    def _assert_name_available(self, name: str, *,
                               scope: SkillScope = SkillScope.USER,
                               owner_id: int, tenant_id: str,
                               exclude_id: Optional[str] = None) -> None:
        """同名规则（§4.4）：PLATFORM 不可覆盖；同作用域内同名拒绝。

        TENANT 与 USER 同名不算冲突（USER 优先并标注遮蔽），因此这里只查
        **目标作用域**这一层。TENANT 层按租户查，跨租户同名互不影响。
        """
        if not name:
            return
        platform_names = {skill.name for skill in self._platform_skills()}
        if name in platform_names:
            raise SkillNameConflict(
                f'与平台内置 Skill 同名：{name}（请改名或 fork）')
        if scope is SkillScope.TENANT:
            same_scope = self._repository.find_by_name(
                SkillScope.TENANT, name, tenant_id=tenant_id)
        else:
            same_scope = self._repository.find_by_name(
                SkillScope.USER, name, owner_id=owner_id)
        if same_scope is not None and same_scope.id != exclude_id:
            raise SkillNameConflict(f'同一作用域已有同名 Skill：{name}')

    def _owned_row(self, skill_id: str, *, owner_id: int, tenant_id: str,
                   writable: bool = False,
                   permissions: Iterable[str] = (),
                   is_admin: bool = False) -> Optional[AgentSkill]:
        """按作用域解析可见行；``writable`` 时再校验写权限。

        - ``USER``：只对本人可见 / 可写（非本人一律 404，不泄漏存在性）；
        - ``TENANT``：同租户可见；写要求租户管理员双条件，非管理员显式
          403（同租户用户本来就能看到这条，隐藏存在性没有意义）；
        - ``PLATFORM``：只读挂载，写入口恒 404。
        """
        if not skill_id or skill_id.startswith(PLATFORM_ID_PREFIX):
            return None
        row = self._repository.get(skill_id)
        if row is None:
            return None
        if row.scope is SkillScope.PLATFORM:
            return None
        if row.scope is SkillScope.USER and row.owner_id != owner_id:
            return None
        if row.scope is SkillScope.TENANT:
            if row.tenant_id != tenant_id:
                return None  # 跨租户：404，不泄漏「存在但无权」
            if writable:
                ensure_tenant_admin(permissions=permissions,
                                    is_admin=is_admin)
        return row

    def _require_row(self, skill_id: str) -> AgentSkill:
        row = self._repository.get(skill_id)
        if row is None:
            raise SkillNotFound(skill_id)
        return row

    def require_row(self, skill_id: str) -> AgentSkill:
        """按 id 取当前行（内部调用；对外可见性判定用 ``get``）。"""
        return self._require_row(skill_id)

    # ------------------------------------------------------------ 审核流支撑

    def tenant_review_row(self, skill_id: str, *, owner_id: int,
                          tenant_id: str) -> AgentSkill:
        """解析可进审核流的行（INT-2551）。

        - 不存在 / PLATFORM / 跨租户 / 非本人 USER → ``SKILL_NOT_FOUND``
          （404，不泄漏存在性）；
        - 本人 ``USER`` 行 → ``SKILL_STATUS_INVALID``：USER 级不走审核流，
          本人显式发布即可。
        """
        row = (None if not skill_id or skill_id.startswith(PLATFORM_ID_PREFIX)
               else self._repository.get(skill_id))
        if row is None or row.scope is SkillScope.PLATFORM:
            raise SkillNotFound(skill_id)
        if row.scope is SkillScope.USER:
            if row.owner_id != owner_id:
                raise SkillNotFound(skill_id)
            raise SkillStatusInvalid(
                'USER 级 Skill 不走审核流：请直接发布')
        if row.tenant_id != tenant_id:
            raise SkillNotFound(skill_id)  # 跨租户：404
        return row

    def refresh_registry(self) -> None:
        """自定义 Skill 状态变化后立即重载 L1 / 激活候选。"""
        self._refresh_registry()

    def append_review(self, row: AgentSkill, *,
                      action: SkillReviewAction,
                      status_from: SkillStatus, status_to: SkillStatus,
                      reviewer_id: Optional[int], reason: str = ''
                      ) -> AgentSkillReview:
        """追加一条审核链审计（只追加；仓储缺失即失败，不静默丢审计）。"""
        return self._append_review(
            row, action=action, status_from=status_from, status_to=status_to,
            reviewer_id=reviewer_id, reason=reason)

    def _build_review(self, row: AgentSkill, *,
                      action: SkillReviewAction,
                      status_from: SkillStatus, status_to: SkillStatus,
                      reviewer_id: Optional[int], reason: str = ''
                      ) -> AgentSkillReview:
        """构造一条 ``agent_skill_review`` 审计实体（由调用方决定落库方式）。"""
        return AgentSkillReview(
            id=str(uuid.uuid4()), skill_id=row.id, version=row.version,
            action=action, status_from=status_from, status_to=status_to,
            reviewer_id=reviewer_id, reason=reason or '',
            tenant_id=row.tenant_id, created_at=self._review_clock())

    def _append_review(self, row: AgentSkill, *,
                       action: SkillReviewAction,
                       status_from: SkillStatus, status_to: SkillStatus,
                       reviewer_id: Optional[int], reason: str = ''
                       ) -> AgentSkillReview:
        if self._reviews is None:
            raise SkillStatusInvalid(
                '审核链仓储未装配，拒绝执行（不静默丢审计）')
        return self._reviews.add(self._build_review(
            row, action=action, status_from=status_from,
            status_to=status_to, reviewer_id=reviewer_id, reason=reason))

    def _resolve_visible_skill(self, skill_id: str, *, owner_id: int,
                               tenant_id: str,
                               permissions: Iterable[str]) -> Skill:
        row = self._owned_row(skill_id, owner_id=owner_id, tenant_id=tenant_id)
        if row is not None:
            return self._domain_skill(row)
        skill = self._platform_skill(skill_id)
        if skill is not None and _granted(skill, set(permissions or ())):
            return skill
        raise SkillNotFound(skill_id)

    def _platform_skills(self) -> List[Skill]:
        # registry.skills 是候选集（含被自定义层遮蔽的平台项），按 viewer 的
        # 遮蔽由 merge_skill_layers 计算，这里只取平台层全集。
        return [s for s in self._registry.skills
                if s.scope is SkillScope.PLATFORM]

    def _platform_skill(self, skill_id: str) -> Optional[Skill]:
        if not skill_id.startswith(PLATFORM_ID_PREFIX):
            return None
        name = skill_id[len(PLATFORM_ID_PREFIX):]
        for skill in self._platform_skills():
            if skill.name == name:
                return skill
        return None

    def _domain_skill(self, row: AgentSkill) -> Skill:
        version = self._repository.get_version(row.id, row.version)
        return to_domain_skill(row, version)

    def _refresh_registry(self) -> None:
        """自定义 Skill 变更后立即重载 L1 / 激活候选（§4.4「立即生效」）。"""
        try:
            self._registry.reload()
        except Exception:  # noqa: BLE001 - 重载失败不掩盖本次写入结果
            logger.warning('SkillRegistry 重载失败', exc_info=True)

    def _view_from_row(self, row: AgentSkill) -> SkillView:
        frontmatter = dict(row.frontmatter or {})
        return SkillView(
            id=row.id, scope=row.scope, name=row.name,
            description=row.description, version=row.version,
            status=row.status, content_hash=row.content_hash,
            owner_id=row.owner_id, tenant_id=row.tenant_id,
            created_by=row.created_by, updated_at=row.updated_at,
            allowed_tools=_text_list(frontmatter.get(FIELD_ALLOWED_TOOLS)),
            permissions=_text_list(frontmatter.get(FIELD_PERMISSIONS)),
            owner=str(frontmatter.get('owner') or ''),
            budgets=_budget_map(frontmatter.get(FIELD_BUDGETS)))

    def _view_from_skill(self, skill: Skill) -> SkillView:
        return SkillView(
            id=skill.skill_id or f'{PLATFORM_ID_PREFIX}{skill.name}',
            scope=skill.scope, name=skill.name,
            description=skill.description, version=skill.meta.version or '0',
            status=skill.status, content_hash=skill.content_hash,
            masked_by=skill.masked_by, owner_id=skill.owner_id,
            tenant_id=skill.tenant_id,
            allowed_tools=skill.meta.allowed_tools,
            permissions=skill.meta.permissions,
            owner=skill.meta.owner,
            budgets=dict(skill.meta.budgets))


# ---------------------------------------------------------------- helpers


def _now() -> datetime:
    from shared.utils.time_utils import utcnow
    return utcnow()


def _text_list(value) -> Tuple[str, ...]:
    from agent_service.domain.services.skill_visibility import text_list
    return text_list(value)


def _budget_map(value) -> Dict[str, int]:
    from agent_service.domain.services.skill_visibility import budget_map
    return budget_map(value)


def _frontmatter_from_meta(meta: SkillMeta) -> Dict[str, Any]:
    frontmatter: Dict[str, Any] = {
        FIELD_NAME: meta.name, FIELD_DESCRIPTION: meta.description}
    if meta.version:
        frontmatter[FIELD_VERSION] = meta.version
    if meta.owner:
        frontmatter['owner'] = meta.owner
    if meta.allowed_tools:
        frontmatter[FIELD_ALLOWED_TOOLS] = list(meta.allowed_tools)
    if meta.permissions:
        frontmatter[FIELD_PERMISSIONS] = list(meta.permissions)
    if meta.budgets:
        frontmatter[FIELD_BUDGETS] = dict(meta.budgets)
    return frontmatter


def build_skill_md(frontmatter: Mapping[str, Any], body: str) -> str:
    """frontmatter 字典 + 正文 → ``SKILL.md`` 原文（导出 / 体积校验同一口径）。"""
    data = dict(frontmatter or {})
    dumped = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f'---\n{dumped}---\n\n{body or ""}'


def _parse_skill_md(raw: str) -> Tuple[Dict[str, Any], str]:
    from shared.skill_package import split_frontmatter
    frontmatter_text, body = split_frontmatter(raw)
    if frontmatter_text is None:
        raise SkillImportInvalid(
            f'SKILL.md 缺少 --- frontmatter',
            issues=[SkillIssue(code=SkillIssueCode.INVALID_FRONTMATTER,
                               severity=SkillIssueSeverity.ERROR,
                               skill='', path='', field='frontmatter',
                               message='SKILL.md 缺少 --- frontmatter')])
    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise SkillImportInvalid(
            f'frontmatter YAML 解析失败：{exc}',
            issues=[SkillIssue(code=SkillIssueCode.INVALID_FRONTMATTER,
                               severity=SkillIssueSeverity.ERROR,
                               skill='', path='', field='frontmatter',
                               message=f'frontmatter YAML 解析失败：{exc}')])
    if not isinstance(data, Mapping):
        raise SkillImportInvalid(
            'frontmatter 必须是映射（key: value）',
            issues=[SkillIssue(code=SkillIssueCode.INVALID_FRONTMATTER,
                               severity=SkillIssueSeverity.ERROR,
                               skill='', path='', field='frontmatter',
                               message='frontmatter 必须是映射')])
    return _normalize_frontmatter(dict(data)), body


def _normalize_frontmatter(value, *, path: str = ''):
    """frontmatter 标量归一为 JSON 可序列化值（返工 P3：YAML 日期）。

    ``yaml.safe_load`` 会把 ``released: 2026-11-14`` 解析成 ``datetime.date``，
    原样进 ``content_hash`` 的 ``json.dumps`` 与 JSONB 落库都会 500。这里统一
    转 ISO 字符串；其他非 JSON 标量（``!!binary`` 的 bytes、``!!set`` 等）
    按 ``INVALID_FRONTMATTER`` 拒绝，不让一个字段把导入打成 500。
    """
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_frontmatter(
                item, path=f'{path}.{key}' if path else str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_frontmatter(item, path=f'{path}[{index}]')
                for index, item in enumerate(value)]
    if isinstance(value, datetime):
        # datetime 是 date 的子类，先判 datetime 保留时间部分
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise SkillImportInvalid(
        f'frontmatter 字段 {path or "(root)"} 不是合法的 JSON 标量：'
        f'{type(value).__name__}',
        issues=[SkillIssue(
            code=SkillIssueCode.INVALID_FRONTMATTER,
            severity=SkillIssueSeverity.ERROR, skill='', path='',
            field=f'frontmatter.{path}' if path else 'frontmatter',
            message=(f'frontmatter 字段 {path or "(root)"} 的类型 '
                     f'{type(value).__name__} 不受支持（只允许字符串 / 数字 / '
                     '布尔 / 列表 / 映射）'))])


def normalize_body(text: str) -> str:
    """正文归一：去掉尾随换行，保证「导出 → 重新导入」内容指纹一致。"""
    return (text or '').rstrip('\n')


def content_hash(meta: SkillMeta, frontmatter: Mapping[str, Any],
                 body: str) -> str:
    """版本内容指纹（frontmatter + 正文，规范化 JSON 后 sha256）。"""
    payload = json.dumps(
        {'frontmatter': dict(frontmatter or {}), 'body': body or ''},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _guard_issue_to_skill(issue: GuardIssue, skill_name: str) -> SkillIssue:
    return SkillIssue(code=issue.code, severity=issue.severity,
                      skill=skill_name, path='', message=issue.message,
                      field=issue.field)


def _package_code(code: PackageIssueCode) -> SkillIssueCode:
    try:
        return SkillIssueCode(code.value)
    except ValueError:
        return SkillIssueCode.INVALID_PATH


def _is_text(payload: bytes) -> bool:
    return b'\x00' not in payload


def _text_resources(resources: Optional[Mapping[str, bytes]]
                    ) -> Dict[str, str]:
    """可解码为 UTF-8 的资源（二进制资源由 ``check_structure`` 兜底）。"""
    texts: Dict[str, str] = {}
    for path, payload in (resources or {}).items():
        try:
            texts[path] = payload.decode('utf-8')
        except UnicodeDecodeError:
            continue
    return texts


def _iter_frontmatter_texts(frontmatter: Mapping[str, Any],
                            *, skip: Iterable[str] = ()
                            ) -> List[Tuple[str, str]]:
    """frontmatter 里的自由文本值（逐项做凭证 / 内网 / 二进制检测）。

    键名只用于报错定位；``skip`` 跳过已单独判定的顶层键（``description``
    由调用方以 ``description`` 字段名单独校验，避免一处命中报两次）。
    """
    skipped = set(skip)
    found: List[Tuple[str, str]] = []

    def walk(node, prefix: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if not prefix and str(key) in skipped:
                    continue
                walk(value, f'{prefix}.{key}' if prefix else str(key))
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, f'{prefix}[{index}]')
        elif isinstance(node, str) and node:
            found.append((f'frontmatter.{prefix}', node))

    walk(frontmatter or {}, '')
    return found


def _granted(skill: Skill, granted: set) -> bool:
    required = skill.meta.permissions
    if not required:
        return True
    if WILDCARD_PERMISSION in granted:
        return True
    return bool(granted & set(required))


__all__ = [
    'GateResult', 'PLATFORM_ID_PREFIX', 'PublishResult', 'SkillDraftPayload',
    'SkillService', 'SkillSettings', 'SkillView', 'build_skill_md',
    'content_hash', 'normalize_body',
]
