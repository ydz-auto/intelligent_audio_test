# -*- coding: utf-8 -*-
"""SkillRegistry：扫描、校验、权限过滤与三级渐进披露（落地方案 §4）。

职责（仅应用层，不碰文件系统具体实现）：
- 装载：调 ``SkillRepository.load_all``，逐个 Skill 校验 frontmatter 契约；
- 取舍：ERROR 级问题剔除该 Skill 并告警；``strict`` 模式下任何问题都让
  启动失败（§4.2 「启动告警/失败」）；
- 可见性：``permissions`` ∩ 用户权限 非空即可见（OR 语义，与工具注册表一致，
  §4.2 规则 7）；``permissions`` 为空表示不额外要求权限；``'*'`` 视为全部权限；
- 披露层级：L1 = name + description（每次模型调用常驻），L2 = 激活 Skill
  正文（仅当前激活时注入），L3 = ``references/`` 由模型按正文指引自行读取；
- 预算：L1 常驻 token 不得超过配置的 system 区段预算（§8.3 15%）。

架构红线：application 只依赖 domain 端口，具体目录扫描在
``infrastructure/skill/fs_skill_repository.py``。
"""
import logging
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from agent_service.domain.enums import (
    SkillIssueCode, SkillIssueSeverity,
)
from agent_service.domain.exceptions import SkillValidationError
from agent_service.domain.model.skill import (
    REQUIRED_SECTIONS, WILDCARD_PERMISSION, Skill,
)
from agent_service.domain.ports.skill_repository import SkillRepository
from agent_service.domain.services.skill_visibility import (
    merge_skill_layers, skill_identity,
)
from agent_service.domain.services.token_estimator import estimate_tokens

logger = logging.getLogger(__name__)

L1_BLOCK_HEADER = '## 可用 Skill（按需激活）'
L2_BLOCK_HEADER = '## 当前激活 Skill：{name}'
L1_LINE_TEMPLATE = '- {name}：{description}'


@dataclass(frozen=True)
class SkillIssue:
    """一条校验问题。"""

    code: SkillIssueCode
    severity: SkillIssueSeverity
    skill: str
    path: str
    message: str
    field: str = ''


def validate_skill(skill: Skill, *,
                   max_body_lines: int = 500,
                   required_sections: Sequence[str] = REQUIRED_SECTIONS,
                   known_tools: Optional[Callable[[], Iterable[str]]] = None,
                   strict_tools: bool = False) -> List[SkillIssue]:
    """frontmatter 契约逐项校验（唯一实现，注册表与保存 / 发布共用）。

    ``strict_tools=False`` 时未注册工具只算 WARNING（启动装载口径）；
    保存 / 发布走 ``strict_tools=True``：``allowed-tools`` 写未注册工具一律
    ERROR 拒绝（§4.4 逐项校验第 4 条）。
    """
    found: List[SkillIssue] = []

    def add(code: SkillIssueCode, severity: SkillIssueSeverity,
            message: str, field: str = '') -> None:
        found.append(SkillIssue(code=code, severity=severity,
                                skill=skill.name, path=skill.path,
                                message=message, field=field))

    if skill.load_error:
        add(SkillIssueCode.INVALID_FRONTMATTER, SkillIssueSeverity.ERROR,
            skill.load_error, 'frontmatter')
        return found
    if not skill.name.strip():
        add(SkillIssueCode.MISSING_NAME, SkillIssueSeverity.ERROR,
            'frontmatter 缺少 name', 'name')
    elif skill.path and not skill.is_custom:
        # 目录名一致性只对只读平台目录有意义（库内行没有目录）
        directory = skill.path.rstrip('/\\').split('\\')[-1].split('/')[-1]
        if directory != skill.name:
            add(SkillIssueCode.DIRECTORY_NAME_MISMATCH,
                SkillIssueSeverity.WARNING,
                f'目录名与 frontmatter name 不一致：{skill.path}', 'name')
    if not skill.description.strip():
        add(SkillIssueCode.MISSING_DESCRIPTION, SkillIssueSeverity.ERROR,
            'frontmatter 缺少 description', 'description')
    if max_body_lines > 0 and skill.body_line_count > max_body_lines:
        add(SkillIssueCode.BODY_TOO_LONG, SkillIssueSeverity.ERROR,
            f'正文 {skill.body_line_count} 行，超过 '
            f'{max_body_lines} 行上限（超出内容拆 references/）', 'body')
    for section in required_sections:
        if not skill.has_section(section):
            add(SkillIssueCode.MISSING_REQUIRED_SECTION,
                SkillIssueSeverity.ERROR, f'正文缺少 `## {section}` 一节', 'body')
    unknown = _unknown_tools(skill, known_tools)
    if unknown:
        add(SkillIssueCode.UNKNOWN_TOOL,
            SkillIssueSeverity.ERROR if strict_tools
            else SkillIssueSeverity.WARNING,
            'allowed-tools 引用未注册工具：' + '、'.join(sorted(unknown)),
            'allowed-tools')
    return found


def _unknown_tools(skill: Skill,
                   known_tools: Optional[Callable[[], Iterable[str]]]
                   ) -> Set[str]:
    names = skill.meta.allowed_tools
    if not names or known_tools is None:
        return set()
    try:
        known = set(known_tools() or ())
    except Exception:  # noqa: BLE001 - 注册表读取失败不阻断装载
        logger.warning('读取工具注册表失败，跳过 allowed-tools 校验',
                       exc_info=True)
        return set()
    return {n for n in names if n not in known}


class SkillRegistry:
    def __init__(self, repository: SkillRepository, *,
                 known_tools: Optional[Callable[[], Iterable[str]]] = None,
                 max_body_lines: int = 500,
                 required_sections: Sequence[str] = REQUIRED_SECTIONS,
                 strict: bool = False,
                 l1_budget_tokens: int = 0):
        self._repository = repository
        self._known_tools = known_tools
        self._max_body_lines = int(max_body_lines)
        self._required_sections = tuple(required_sections)
        self._strict = bool(strict)
        self._l1_budget_tokens = int(l1_budget_tokens)
        # INT-2549：装载口径是「候选集」——平台层 + 全部 ACTIVE 自定义层。
        # 同名遮蔽是**查看者相关**的（不同 owner 的同名 USER Skill 互不影响），
        # 因此合并推迟到 visible_for / get_visible 按 viewer 计算。
        self._skills: Tuple[Skill, ...] = ()
        self._issues: Tuple[SkillIssue, ...] = ()

    # ------------------------------------------------------------ loading

    def load(self) -> 'SkillRegistry':
        """重新扫描并校验。严格模式下有任何问题直接抛异常（启动失败）。

        目录级失败（根目录缺失 / 不可读 / 为空、目录缺 SKILL.md）由仓储层
        带回原因码（INT-2506），统一收进 issues。

        INT-2529：仓库一个 Skill 都没装到（空目录 / 缺 SKILL.md）属部署级
        故障，与 ``strict`` 无关一律 fail-fast —— Docker 对不存在的 bind 源
        会自动创建空目录，只读挂载静默变「零 Skill」不能等到运行期才发现。
        """
        issues: List[SkillIssue] = []
        accepted: List[Skill] = []
        # 身份键 = (scope, owner_id/tenant_id, name)：跨 owner / 跨租户的同名
        # 是不同 Skill，不能按裸 name 判重复（库内局部唯一索引同口径）。
        seen: Set[Tuple[str, Optional[object], str]] = set()
        scan = self._repository.load_all()
        for scan_issue in scan.issues:
            issues.append(SkillIssue(
                code=scan_issue.code,
                severity=SkillIssueSeverity.ERROR,
                skill='', path=scan_issue.path, message=scan_issue.message))
        if not scan.skills:
            # 零 Skill 的聚合原因码（INT-2529）：上面几条是目录级细节
            # （缺失 / 不可读 / 空 / 缺 SKILL.md），这条让运维一眼看到
            # 「一个 Skill 都没装到」，且与启动失败一一对应。
            issues.append(SkillIssue(
                code=SkillIssueCode.EMPTY_SKILLS_ROOT,
                severity=SkillIssueSeverity.ERROR,
                skill='', path=str(getattr(self._repository, 'root', '') or ''),
                message=('skills 目录未装载到任何 Skill（空目录或缺少 '
                         'SKILL.md）：检查只读挂载是否指向真实技能目录')))
        for skill in scan.skills:
            found = self._validate(skill)
            fatal = [i for i in found if i.severity is SkillIssueSeverity.ERROR]
            identity = skill_identity(skill)
            if not fatal and identity in seen:
                found.append(SkillIssue(
                    code=SkillIssueCode.DUPLICATE_NAME,
                    severity=SkillIssueSeverity.ERROR,
                    skill=skill.name, path=skill.path,
                    message=f'Skill 名称重复（同一作用域与归属）：{skill.name}'))
                fatal = [i for i in found
                         if i.severity is SkillIssueSeverity.ERROR]
            issues.extend(found)
            if fatal:
                continue
            seen.add(identity)
            accepted.append(skill)

        self._skills = tuple(accepted)
        budget_issue = self._check_l1_budget()
        if budget_issue is not None:
            issues.append(budget_issue)
        self._issues = tuple(issues)

        errors = [i for i in issues if i.severity is SkillIssueSeverity.ERROR]
        if self._strict and issues:
            raise SkillValidationError(self._issues)
        for issue in issues:
            level = logging.ERROR if issue.severity is SkillIssueSeverity.ERROR \
                else logging.WARNING
            logger.log(level, 'Skill 校验 %s %s %s %s', issue.severity.value,
                       issue.code.value, issue.skill or issue.path,
                       issue.message)
        logger.info('SkillRegistry 装载完成：%d 个可用 / %d 个问题',
                    len(self._skills), len(self._issues))
        if not self._skills:
            # INT-2506：0 个可用 Skill 不能只留 INFO（Skill 层整体消失时看板
            # / /health / /skills 全是 200，模型会退回凭记忆回答平台口径）。
            (logger.error if errors else logger.warning)(
                'Skill 装载结果为空：0 个可用 Skill / %d 个问题，'
                'skills 目录是否挂载正确？', len(self._issues))
        if not scan.skills:
            # INT-2529：空目录不是「某个 Skill 不合法」，而是部署配置错误：
            # 非 strict 也失败（Docker 对缺失 bind 源会自动建空目录）。
            raise SkillValidationError(self._issues)
        return self

    @property
    def skills(self) -> Tuple[Skill, ...]:
        """装载到的全部候选（平台层 + 全部 ACTIVE 自定义层）。

        这是**未按查看者合并**的候选集：同名遮蔽是查看者相关的，读取可见
        清单请走 ``visible_for`` / ``l1_block``（内部按 viewer 合并）。
        """
        return self._skills

    @property
    def issues(self) -> Tuple[SkillIssue, ...]:
        return self._issues

    def reload(self) -> 'SkillRegistry':
        """重新装载（自定义 Skill 增删改后由应用层调用，立即生效）。

        与 ``load`` 同一实现：仓储层每次 ``load_all`` 重新读库，因此停用 /
        删除在下一次 L1 / 激活候选组装前即可见（§4.4「立即生效」）。
        """
        return self.load()

    def issues_for(self, name: str) -> Tuple[SkillIssue, ...]:
        return tuple(i for i in self._issues if i.skill == name)

    # ------------------------------------------------------------ visibility

    def visible_for(self, permissions: Optional[Iterable[str]],
                    *, owner_id: Optional[int] = None,
                    tenant_id: Optional[str] = None) -> Tuple[Skill, ...]:
        """按用户权限与可见范围过滤（§4.2 规则 7：OR 语义）。

        INT-2549：``USER`` 只对 ``owner_id`` 本人可见、``TENANT`` 只对
        ``tenant_id`` 本租户可见；未传身份时只返回 ``PLATFORM``（安全默认）。
        同名合并按 viewer 计算：不同 owner 的同名 USER Skill 各自生效。
        """
        granted = self._granted(permissions)
        effective = self._merged(owner_id=owner_id, tenant_id=tenant_id)
        return tuple(s for s in effective if self._is_granted(s, granted))

    def get_visible(self, name: Optional[str],
                    permissions: Optional[Iterable[str]],
                    *, owner_id: Optional[int] = None,
                    tenant_id: Optional[str] = None) -> Optional[Skill]:
        if not name:
            return None
        granted = self._granted(permissions)
        for skill in self._merged(owner_id=owner_id, tenant_id=tenant_id):
            if skill.name == name:
                return skill if self._is_granted(skill, granted) else None
        return None

    def get(self, name: str) -> Optional[Skill]:
        """无身份视角（PLATFORM 层）按名称取生效项。

        需要按用户 / 租户取（含自定义层）时用 ``get_visible``；这里保持
        「未传身份只放行 PLATFORM」的安全默认，避免内部调用拿到他人私有项。
        """
        for skill in self._merged():
            if skill.name == name:
                return skill
        return None

    # ------------------------------------------------------------ disclosure

    def l1_block(self, permissions: Optional[Iterable[str]] = None, *,
                 owner_id: Optional[int] = None,
                 tenant_id: Optional[str] = None) -> str:
        """L1：全部可见 Skill 的 name + 单行 description。"""
        return self._render_l1(self.visible_for(
            permissions, owner_id=owner_id, tenant_id=tenant_id))

    def l2_block(self, skill: Skill) -> str:
        """L2：激活 Skill 的正文。"""
        header = L2_BLOCK_HEADER.format(name=skill.name)
        if skill.meta.version:
            header = f'{header}（v{skill.meta.version}）'
        return f'{header}\n\n{skill.body.strip()}'

    def system_section(self, permissions: Optional[Iterable[str]] = None,
                       active_skill: Optional[str] = None, *,
                       owner_id: Optional[int] = None,
                       tenant_id: Optional[str] = None,
                       active_skill_obj: Optional[Skill] = None) -> str:
        """system 区段的 Skill 部分：L1 常驻 + （可选）激活 Skill 的 L2。

        ``active_skill_obj``（INT-2549）：在办 run 的版本快照。传入即按快照
        正文注入 L2，不重查可见性 —— 停用 / 删除 / 修改不中途换内容。
        """
        blocks: List[str] = []
        l1 = self.l1_block(permissions, owner_id=owner_id,
                           tenant_id=tenant_id)
        if l1:
            blocks.append(l1)
        skill = active_skill_obj
        if skill is None and active_skill:
            skill = self.get_visible(active_skill, permissions,
                                     owner_id=owner_id, tenant_id=tenant_id)
            if skill is None:
                logger.warning('激活 Skill 不可用（未注册或权限不足）：%s',
                               active_skill)
        if skill is not None:
            blocks.append(self.l2_block(skill))
        return '\n\n'.join(blocks)

    def l1_tokens(self, permissions: Optional[Iterable[str]] = None, *,
                  owner_id: Optional[int] = None,
                  tenant_id: Optional[str] = None) -> int:
        return estimate_tokens(self.l1_block(
            permissions, owner_id=owner_id, tenant_id=tenant_id))

    @property
    def l1_budget_tokens(self) -> int:
        return self._l1_budget_tokens

    # ------------------------------------------------------------ internals

    def _merged(self, *, owner_id: Optional[int] = None,
                tenant_id: Optional[str] = None) -> Tuple[Skill, ...]:
        """按查看者合并候选集（唯一实现在 domain.services.skill_visibility）。"""
        effective, _ = merge_skill_layers(
            self._skills, owner_id=owner_id, tenant_id=tenant_id,
            active_only=False)
        return effective

    @staticmethod
    def _granted(permissions: Optional[Iterable[str]]) -> Set[str]:
        if isinstance(permissions, str):
            # 兜底：允许直接传网关身份头的逗号串
            permissions = permissions.split(',')
        return {p.strip() if isinstance(p, str) else p
                for p in (permissions or ()) if p}

    @staticmethod
    def _is_granted(skill: Skill, granted: Set[str]) -> bool:
        required = skill.meta.permissions
        if not required:
            return True
        if WILDCARD_PERMISSION in granted:
            return True
        return bool(granted & set(required))

    def _validate(self, skill: Skill) -> List[SkillIssue]:
        # 与保存 / 发布共用同一实现（INT-2549：不另写一套校验）
        return validate_skill(
            skill, max_body_lines=self._max_body_lines,
            required_sections=self._required_sections,
            known_tools=self._known_tools)

    def _check_l1_budget(self) -> Optional[SkillIssue]:
        if self._l1_budget_tokens <= 0:
            return None
        # 预算口径是「无身份视角」的 L1（PLATFORM 层），不把他人私有 Skill
        # 算进本部署的常驻预算。
        tokens = estimate_tokens(self._render_l1(self._merged()))
        if tokens <= self._l1_budget_tokens:
            return None
        return SkillIssue(
            code=SkillIssueCode.L1_BUDGET_EXCEEDED,
            severity=SkillIssueSeverity.WARNING,
            skill='', path='',
            message=(f'L1 常驻 {tokens} tokens 超过 system 区段预算 '
                     f'{self._l1_budget_tokens} tokens'))

    @staticmethod
    def _render_l1(skills: Sequence[Skill]) -> str:
        lines = [
            L1_LINE_TEMPLATE.format(
                name=s.name, description=' '.join(s.description.split()))
            for s in sorted(skills, key=lambda item: item.name)
        ]
        if not lines:
            return ''
        return '\n'.join([L1_BLOCK_HEADER] + lines)


__all__ = ['SkillIssue', 'SkillRegistry', 'L1_BLOCK_HEADER', 'L2_BLOCK_HEADER',
           'validate_skill']
