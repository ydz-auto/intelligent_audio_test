# -*- coding: utf-8 -*-
"""文件系统 Skill 仓储（落地方案 §4.1 / §12.1）。

目录约定：``<root>/<skill-name>/SKILL.md`` 必需，``references/`` /
``scripts/`` / ``assets/`` 可选。根目录缺省为仓库顶层 ``skills/``，容器内由
部署挂载只读目录（INT-2456）。

单个文件的问题不改抛异常：解析失败写进 ``Skill.load_error``，由
application/skill_registry 统一判定严重度与取舍。

INT-2506：目录级失败（根目录不存在 / 不可读 / 为空、目录缺 ``SKILL.md``）
不再只打一行日志——每个都带原因码回传给 ``SkillRegistry``，保证「挂了空目录
或挂错路径导致 Skill 层整体消失」在 ``/skills`` 与 ``/health`` 上可见。
"""
import logging
import os
import stat as stat_module
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from agent_service.domain.enums import SkillIssueCode
from agent_service.domain.model.skill import (
    FIELD_ALLOWED_TOOLS, FIELD_BUDGETS, FIELD_DESCRIPTION, FIELD_NAME,
    FIELD_OWNER, FIELD_PERMISSIONS, FIELD_VERSION, SKILL_FILE_NAME, Skill,
    SkillMeta,
)
from agent_service.domain.model.skill_scan import (
    SkillScanIssue, SkillScanResult,
)
from agent_service.domain.ports.skill_repository import SkillRepository

logger = logging.getLogger(__name__)

FRONTMATTER_DELIMITER = '---'
REFERENCES_DIR = 'references'
SCRIPTS_DIR = 'scripts'
ASSETS_DIR = 'assets'


class FsSkillRepository(SkillRepository):
    def __init__(self, root: str):
        self._root = str(root or '')

    @property
    def root(self) -> str:
        return self._root

    def load_all(self) -> SkillScanResult:
        root_issue = self._check_root()
        if root_issue is not None:
            return SkillScanResult(issues=(root_issue,))

        try:
            entries = sorted(os.listdir(self._root))
        except OSError as exc:
            return SkillScanResult(issues=(self._unreadable_issue(exc),))

        if not entries:
            logger.warning('skills 目录为空：%s（未装载任何 Skill）', self._root)
            return SkillScanResult(issues=(SkillScanIssue(
                code=SkillIssueCode.SKILLS_ROOT_EMPTY, path=self._root,
                message='skills 根目录存在但没有任何条目（检查部署挂载）'),))

        skills: List[Skill] = []
        issues: List[SkillScanIssue] = []
        for entry in entries:
            directory = os.path.join(self._root, entry)
            if not os.path.isdir(directory):
                continue
            path = os.path.join(directory, SKILL_FILE_NAME)
            if not os.path.isfile(path):
                issues.append(SkillScanIssue(
                    code=SkillIssueCode.SKILL_FILE_MISSING, path=directory,
                    message=f'Skill 目录缺少 {SKILL_FILE_NAME}，已跳过'))
                continue
            skills.append(self._load_one(directory, path))
        return SkillScanResult(skills=tuple(skills), issues=tuple(issues))

    # ------------------------------------------------------------ internals

    def _check_root(self) -> Optional[SkillScanIssue]:
        """根目录可用性检查；不可用时返回原因码，不抛异常。"""
        if not self._root:
            return SkillScanIssue(
                code=SkillIssueCode.SKILLS_ROOT_MISSING, path='',
                message='未配置 skills 根目录')
        try:
            mode = os.stat(self._root).st_mode
        except FileNotFoundError:
            return SkillScanIssue(
                code=SkillIssueCode.SKILLS_ROOT_MISSING, path=self._root,
                message='skills 根目录不存在（检查部署挂载路径）')
        except OSError as exc:
            return self._unreadable_issue(exc)
        if not stat_module.S_ISDIR(mode):
            return SkillScanIssue(
                code=SkillIssueCode.SKILLS_ROOT_MISSING, path=self._root,
                message='skills 根路径不是目录')
        return None

    def _unreadable_issue(self, exc: OSError) -> SkillScanIssue:
        return SkillScanIssue(
            code=SkillIssueCode.SKILLS_ROOT_UNREADABLE, path=self._root,
            message=f'skills 根目录不可读：{exc}')

    def _load_one(self, directory: str, path: str) -> Skill:
        try:
            with open(path, encoding='utf-8-sig') as handle:
                raw = handle.read()
        except OSError as exc:
            return Skill(meta=SkillMeta(), body='', path=directory,
                         load_error=f'读取失败：{exc}')

        frontmatter, body = _split_frontmatter(raw)
        if frontmatter is None:
            return Skill(meta=SkillMeta(), body=raw, path=directory,
                         load_error=f'缺少 {FRONTMATTER_DELIMITER} frontmatter')
        try:
            data = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError as exc:
            return Skill(meta=SkillMeta(), body=body, path=directory,
                         load_error=f'frontmatter YAML 解析失败：{exc}')
        if not isinstance(data, Mapping):
            return Skill(meta=SkillMeta(), body=body, path=directory,
                         load_error='frontmatter 必须是映射（key: value）')

        meta = SkillMeta(
            name=_text(data.get(FIELD_NAME)),
            description=_text(data.get(FIELD_DESCRIPTION)),
            version=_text(data.get(FIELD_VERSION)),
            owner=_text(data.get(FIELD_OWNER)),
            allowed_tools=_text_list(data.get(FIELD_ALLOWED_TOOLS)),
            permissions=_text_list(data.get(FIELD_PERMISSIONS)),
            budgets=_budget_map(data.get(FIELD_BUDGETS)),
        )
        return Skill(
            meta=meta, body=body, path=directory,
            references=_list_files(directory, REFERENCES_DIR),
            scripts=_list_files(directory, SCRIPTS_DIR),
            assets=_list_files(directory, ASSETS_DIR),
        )


def _split_frontmatter(raw: str) -> Tuple[Optional[str], str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, raw
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            frontmatter = '\n'.join(lines[1:index])
            body = '\n'.join(lines[index + 1:]).lstrip('\n')
            return frontmatter, body
    return None, raw


def _text(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _text_list(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(',') if item.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _budget_map(value: Any) -> Dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    budgets: Dict[str, int] = {}
    for key, raw in value.items():
        try:
            budgets[str(key)] = int(raw)
        except (TypeError, ValueError):
            logger.warning('Skill budgets 字段 %s 不是整数：%r', key, raw)
    return budgets


def _list_files(directory: str, name: str) -> Tuple[str, ...]:
    """列出子目录内的相对路径（L3 由模型按正文指引读取）。"""
    base = os.path.join(directory, name)
    if not os.path.isdir(base):
        return ()
    files: List[str] = []
    for current, _dirs, filenames in os.walk(base):
        for filename in sorted(filenames):
            full = os.path.join(current, filename)
            files.append(os.path.relpath(full, directory).replace(os.sep, '/'))
    return tuple(sorted(files))


__all__ = ['FsSkillRepository', 'SKILL_FILE_NAME']
