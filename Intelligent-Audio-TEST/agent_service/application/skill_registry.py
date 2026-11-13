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

from agent_service.domain.enums import SkillIssueCode, SkillIssueSeverity
from agent_service.domain.exceptions import SkillValidationError
from agent_service.domain.model.skill import (
    REQUIRED_SECTIONS, WILDCARD_PERMISSION, Skill,
)
from agent_service.domain.ports.skill_repository import SkillRepository
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
        seen: Set[str] = set()
        scan = self._repository.load_all()
        for scan_issue in scan.issues:
            issues.append(SkillIssue(
                code=scan_issue.code,
                severity=SkillIssueSeverity.ERROR,
                skill='', path=scan_issue.path, message=scan_issue.message))
        for skill in scan.skills:
            found = self._validate(skill)
            fatal = [i for i in found if i.severity is SkillIssueSeverity.ERROR]
            if not fatal and skill.name in seen:
                found.append(SkillIssue(
                    code=SkillIssueCode.DUPLICATE_NAME,
                    severity=SkillIssueSeverity.ERROR,
                    skill=skill.name, path=skill.path,
                    message=f'Skill 名称重复：{skill.name}'))
                fatal = [i for i in found
                         if i.severity is SkillIssueSeverity.ERROR]
            issues.extend(found)
            if fatal:
                continue
            seen.add(skill.name)
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
        return self._skills

    @property
    def issues(self) -> Tuple[SkillIssue, ...]:
        return self._issues

    def issues_for(self, name: str) -> Tuple[SkillIssue, ...]:
        return tuple(i for i in self._issues if i.skill == name)

    # ------------------------------------------------------------ visibility

    def visible_for(self, permissions: Optional[Iterable[str]]
                    ) -> Tuple[Skill, ...]:
        """按用户权限过滤（§4.2 规则 7：OR 语义）。"""
        granted = self._granted(permissions)
        return tuple(s for s in self._skills if self._is_granted(s, granted))

    def get_visible(self, name: Optional[str],
                    permissions: Optional[Iterable[str]]) -> Optional[Skill]:
        if not name:
            return None
        skill = self.get(name)
        if skill is None:
            return None
        granted = self._granted(permissions)
        return skill if self._is_granted(skill, granted) else None

    def get(self, name: str) -> Optional[Skill]:
        for skill in self._skills:
            if skill.name == name:
                return skill
        return None

    # ------------------------------------------------------------ disclosure

    def l1_block(self, permissions: Optional[Iterable[str]] = None) -> str:
        """L1：全部可见 Skill 的 name + 单行 description。"""
        return self._render_l1(self.visible_for(permissions))

    def l2_block(self, skill: Skill) -> str:
        """L2：激活 Skill 的正文。"""
        header = L2_BLOCK_HEADER.format(name=skill.name)
        if skill.meta.version:
            header = f'{header}（v{skill.meta.version}）'
        return f'{header}\n\n{skill.body.strip()}'

    def system_section(self, permissions: Optional[Iterable[str]] = None,
                       active_skill: Optional[str] = None) -> str:
        """system 区段的 Skill 部分：L1 常驻 + （可选）激活 Skill 的 L2。"""
        blocks: List[str] = []
        l1 = self.l1_block(permissions)
        if l1:
            blocks.append(l1)
        if active_skill:
            skill = self.get_visible(active_skill, permissions)
            if skill is None:
                logger.warning('激活 Skill 不可用（未注册或权限不足）：%s',
                               active_skill)
            else:
                blocks.append(self.l2_block(skill))
        return '\n\n'.join(blocks)

    def l1_tokens(self, permissions: Optional[Iterable[str]] = None) -> int:
        return estimate_tokens(self.l1_block(permissions))

    @property
    def l1_budget_tokens(self) -> int:
        return self._l1_budget_tokens

    # ------------------------------------------------------------ internals

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
        found: List[SkillIssue] = []

        def add(code: SkillIssueCode, severity: SkillIssueSeverity,
                message: str) -> None:
            found.append(SkillIssue(code=code, severity=severity,
                                    skill=skill.name, path=skill.path,
                                    message=message))

        if skill.load_error:
            add(SkillIssueCode.INVALID_FRONTMATTER, SkillIssueSeverity.ERROR,
                skill.load_error)
            return found
        if not skill.name.strip():
            add(SkillIssueCode.MISSING_NAME, SkillIssueSeverity.ERROR,
                'frontmatter 缺少 name')
        elif skill.path.rstrip('/\\').split('\\')[-1].split('/')[-1] != skill.name:
            add(SkillIssueCode.DIRECTORY_NAME_MISMATCH,
                SkillIssueSeverity.WARNING,
                f'目录名与 frontmatter name 不一致：{skill.path}')
        if not skill.description.strip():
            add(SkillIssueCode.MISSING_DESCRIPTION, SkillIssueSeverity.ERROR,
                'frontmatter 缺少 description')
        if self._max_body_lines > 0 and skill.body_line_count > self._max_body_lines:
            add(SkillIssueCode.BODY_TOO_LONG, SkillIssueSeverity.ERROR,
                f'正文 {skill.body_line_count} 行，超过 '
                f'{self._max_body_lines} 行上限（超出内容拆 references/）')
        for section in self._required_sections:
            if not skill.has_section(section):
                add(SkillIssueCode.MISSING_REQUIRED_SECTION,
                    SkillIssueSeverity.ERROR, f'正文缺少 `## {section}` 一节')
        unknown = self._unknown_tools(skill)
        if unknown:
            add(SkillIssueCode.UNKNOWN_TOOL, SkillIssueSeverity.WARNING,
                'allowed-tools 引用未注册工具：' + '、'.join(sorted(unknown)))
        return found

    def _unknown_tools(self, skill: Skill) -> Set[str]:
        names = skill.meta.allowed_tools
        if not names or self._known_tools is None:
            return set()
        try:
            known = set(self._known_tools() or ())
        except Exception:  # noqa: BLE001 - 注册表读取失败不阻断装载
            logger.warning('读取工具注册表失败，跳过 allowed-tools 校验',
                           exc_info=True)
            return set()
        return {n for n in names if n not in known}

    def _check_l1_budget(self) -> Optional[SkillIssue]:
        if self._l1_budget_tokens <= 0:
            return None
        tokens = estimate_tokens(self._render_l1(self._skills))
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


__all__ = ['SkillIssue', 'SkillRegistry', 'L1_BLOCK_HEADER', 'L2_BLOCK_HEADER']
