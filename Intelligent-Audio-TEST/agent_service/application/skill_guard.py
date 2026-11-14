# -*- coding: utf-8 -*-
"""自定义 Skill 的安全检测（INT-2549 §4.4「不可信正文与注入检测」）。

职责：
- 结构 / 体积 / 路径：``SKILL.md`` ≤ 64 KB、单资源 ≤ 512 KB、整包 ≤ 5 MB、
  条目数与压缩比上限（zip bomb）、绝对路径 / ``..`` / 软链 / 外链拒绝；
- 内容：凭证（复用 ``shared/utils/secret_mask.has_secret`` 同一判据）、
  内网 / 回环地址、可执行二进制。内网 / 回环一律拒绝（INT-2612：字面量
  ``localhost`` 与 ``127.0.0.1``、``[::1]`` 同判）。``SKILL.md`` 正文、
  ``description``（会经 L1 进系统提示）与 frontmatter 自由文本、文本资源
  都按不可信内容判定；
- 注入：**规则化**启发式（规则表配置化，不做模型判定）。保存只做结构与内容
  校验；发布额外对正文 / 描述 / 文本资源做注入检测，命中即拒绝发布（草稿仍
  可保存）。

口径：规则化检测存在漏报，回执写「命中拒绝、未命中不等于安全」，不对外
宣称安全保证。
"""
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from agent_service.domain.enums import SkillIssueCode, SkillIssueSeverity
from agent_service.domain.model.skill import RESOURCE_DIRS
from shared.skill_package import normalize_entry_path, SkillPackageError
from shared.utils.secret_mask import has_secret

logger = logging.getLogger(__name__)

DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'config', 'skill_guard_rules.json')


@dataclass(frozen=True)
class GuardIssue:
    """一条安全检测问题（与 ``SkillIssue`` 同码表）。"""

    code: SkillIssueCode
    severity: SkillIssueSeverity
    field: str
    message: str


@dataclass(frozen=True)
class GuardLimits:
    """体积 / 条目上限（配置化，§4.4 逐项校验）。"""

    max_skill_bytes: int = 64 * 1024
    max_resource_bytes: int = 512 * 1024
    max_package_bytes: int = 5 * 1024 * 1024
    max_entries: int = 200
    max_compression_ratio: int = 100

    def to_package_limits(self):
        from shared.skill_package import SkillPackageLimits
        return SkillPackageLimits(
            max_entries=self.max_entries,
            max_skill_bytes=self.max_skill_bytes,
            max_resource_bytes=self.max_resource_bytes,
            max_total_bytes=self.max_package_bytes,
            max_compression_ratio=self.max_compression_ratio)


@dataclass(frozen=True)
class _InjectionRule:
    rule_id: str
    pattern: re.Pattern
    message: str


class SkillGuard:
    """规则化安全检测（规则表来自 JSON，便于后续扩充而不改代码）。"""

    def __init__(self, *, limits: Optional[GuardLimits] = None,
                 rules_path: Optional[str] = None):
        self._limits = limits or GuardLimits()
        self._rules_path = rules_path or DEFAULT_RULES_PATH
        self._injection_rules, self._internal_patterns = self._load_rules(
            self._rules_path)

    @property
    def limits(self) -> GuardLimits:
        return self._limits

    @property
    def injection_rule_count(self) -> int:
        return len(self._injection_rules)

    # ------------------------------------------------------------ 结构 / 体积

    def check_structure(self, *, skill_md: str,
                        resources: Optional[Dict[str, bytes]] = None
                        ) -> List[GuardIssue]:
        """保存前的结构 / 体积 / 路径校验（失败不落库）。"""
        found: List[GuardIssue] = []
        limits = self._limits
        encoded = (skill_md or '').encode('utf-8')
        if len(encoded) > limits.max_skill_bytes:
            found.append(GuardIssue(
                SkillIssueCode.BODY_TOO_LARGE, SkillIssueSeverity.ERROR,
                'body', f'SKILL.md {len(encoded)} 字节，超过 '
                        f'{limits.max_skill_bytes} 字节上限'))
        resources = resources or {}
        if len(resources) + 1 > limits.max_entries:
            found.append(GuardIssue(
                SkillIssueCode.TOO_MANY_ENTRIES, SkillIssueSeverity.ERROR,
                'resources', f'条目 {len(resources) + 1} 个，超过 '
                             f'{limits.max_entries} 个上限'))
        total = len(encoded)
        for path, payload in resources.items():
            normalized = self._check_resource_path(path, found)
            if normalized is None:
                continue
            if not isinstance(payload, (bytes, bytearray)):
                found.append(GuardIssue(
                    SkillIssueCode.BINARY_CONTENT, SkillIssueSeverity.ERROR,
                    f'resources.{path}', '资源内容必须是字节'))
                continue
            total += len(payload)
            if len(payload) > limits.max_resource_bytes:
                found.append(GuardIssue(
                    SkillIssueCode.RESOURCE_TOO_LARGE, SkillIssueSeverity.ERROR,
                    f'resources.{path}',
                    f'资源 {path} {len(payload)} 字节，超过单资源上限 '
                    f'{limits.max_resource_bytes}'))
            if b'\x00' in bytes(payload):
                found.append(GuardIssue(
                    SkillIssueCode.BINARY_CONTENT, SkillIssueSeverity.ERROR,
                    f'resources.{path}', f'资源 {path} 含可执行二进制内容'))
        if total > limits.max_package_bytes:
            found.append(GuardIssue(
                SkillIssueCode.PACKAGE_TOO_LARGE, SkillIssueSeverity.ERROR,
                'resources', f'整包 {total} 字节，超过上限 '
                             f'{limits.max_package_bytes}'))
        return found

    def _check_resource_path(self, path: str,
                             found: List[GuardIssue]) -> Optional[str]:
        """资源路径校验：只允许 references/ scripts/ assets/ 下的相对路径。"""
        if re.match(r'^\s*[a-zA-Z][a-zA-Z0-9+.-]*://', path or ''):
            found.append(GuardIssue(
                SkillIssueCode.EXTERNAL_LINK_REJECTED,
                SkillIssueSeverity.ERROR, f'resources.{path}',
                f'禁止外链资源：{path}'))
            return None
        try:
            normalized = normalize_entry_path(path)
        except SkillPackageError as exc:
            found.append(GuardIssue(
                SkillIssueCode.INVALID_PATH, SkillIssueSeverity.ERROR,
                f'resources.{path}', exc.message))
            return None
        if not any(normalized.startswith(f'{name}/') for name in RESOURCE_DIRS):
            found.append(GuardIssue(
                SkillIssueCode.INVALID_PATH, SkillIssueSeverity.ERROR,
                f'resources.{path}',
                f'资源只允许放在 {" / ".join(RESOURCE_DIRS)} 下：{path}'))
            return None
        return normalized

    # ------------------------------------------------------------ 凭证 / 内网 / 二进制

    def check_content(self, text: str, *, field: str) -> List[GuardIssue]:
        """凭证 / 内网地址检测（保存即拒绝）。"""
        found: List[GuardIssue] = []
        body = text or ''
        if has_secret(body):
            found.append(GuardIssue(
                SkillIssueCode.EMBEDDED_SECRET, SkillIssueSeverity.ERROR,
                field, '内容包含疑似凭证（API Key / Token / 密码），禁止落库'))
        for pattern in self._internal_patterns:
            match = pattern.search(body)
            if match:
                found.append(GuardIssue(
                    SkillIssueCode.INTERNAL_ADDRESS, SkillIssueSeverity.ERROR,
                    field, f'内容包含内网地址：{match.group(0)}'))
                break
        return found

    def check_binary_text(self, text: str, *, field: str) -> List[GuardIssue]:
        if text and '\x00' in text:
            return [GuardIssue(SkillIssueCode.BINARY_CONTENT,
                               SkillIssueSeverity.ERROR, field,
                               '正文含二进制内容')]
        return []

    # ------------------------------------------------------------ 注入（仅发布）

    def check_injection(self, body: str, *, field: str = 'body'
                        ) -> List[GuardIssue]:
        """规则化注入检测：命中即拒绝发布（草稿仍可保存）。

        ``field`` 标注命中位置：正文用 ``body``；``description`` 与文本资源
        也按不可信内容检测（描述会经 L1 进入系统提示，资源会进 L3 上下文）。
        """
        text = body or ''
        found: List[GuardIssue] = []
        for rule in self._injection_rules:
            match = rule.pattern.search(text)
            if match:
                found.append(GuardIssue(
                    SkillIssueCode.INJECTION_DETECTED, SkillIssueSeverity.ERROR,
                    field, f'{rule.message}（规则 {rule.rule_id}）'))
        return found

    # ------------------------------------------------------------ internals

    @staticmethod
    def _load_rules(path: str) -> Tuple[Tuple[_InjectionRule, ...],
                                        Tuple[re.Pattern, ...]]:
        data = {}
        try:
            with open(path, encoding='utf-8') as handle:
                data = json.load(handle) or {}
        except (OSError, ValueError):
            logger.warning('Skill 注入规则文件缺失或非法，使用内置最小规则集：%s',
                           path)
        injection = []
        for item in data.get('injection') or []:
            try:
                injection.append(_InjectionRule(
                    rule_id=str(item['id']),
                    pattern=re.compile(str(item['pattern']),
                                       re.IGNORECASE | re.MULTILINE),
                    message=str(item.get('message') or '命中注入规则')))
            except (KeyError, TypeError, re.error):
                logger.warning('跳过非法注入规则项：%r', item)
        if not injection:
            injection = list(_BUILTIN_INJECTION_RULES)
        internal = []
        for raw in data.get('internal_addresses') or []:
            try:
                internal.append(re.compile(str(raw), re.IGNORECASE))
            except re.error:
                logger.warning('跳过非法内网地址规则：%r', raw)
        if not internal:
            internal = list(_BUILTIN_INTERNAL_PATTERNS)
        return tuple(injection), tuple(internal)


_BUILTIN_INJECTION_RULES: Sequence[_InjectionRule] = (
    _InjectionRule(
        'ignore_previous_instructions',
        re.compile(r'(忽略|无视|跳过|ignore|disregard)[^\n]{0,20}'
                   r'(之前|以上|前面|上述|previous|prior|above)[^\n]{0,12}'
                   r'(指令|指示|规则|instruction|rule)', re.IGNORECASE),
        '试图覆盖系统指令'),
    _InjectionRule(
        'override_system_prompt',
        re.compile(r'(reveal|输出|打印|显示)[^\n]{0,12}'
                   r'(system prompt|系统提示词|系统指令)', re.IGNORECASE),
        '试图读取/覆盖系统提示词'),
    _InjectionRule(
        'bypass_permission',
        re.compile(r'(无需|跳过|绕过)[^\n]{0,10}(审批|确认|权限|approval|confirm)',
                   re.IGNORECASE),
        '试图绕过审批或权限'),
    _InjectionRule(
        'exfiltrate_secret',
        re.compile(r'(上传|发送|回传|upload|send)[^\n]{0,16}'
                   r'(密钥|凭证|token|api[_ -]?key|password)', re.IGNORECASE),
        '试图外传凭证'),
    _InjectionRule(
        'exfiltrate_secret_reversed',
        re.compile(r'(密钥|凭证|token|api[_ -]?key|password)[^\n]{0,16}'
                   r'(上传|发送|回传|upload|send)', re.IGNORECASE),
        '试图外传凭证'),
)

_BUILTIN_INTERNAL_PATTERNS: Sequence[re.Pattern] = (
    re.compile(r'\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    re.compile(r'\b192\.168\.\d{1,3}\.\d{1,3}\b'),
    re.compile(r'\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b'),
    re.compile(r'\b[a-z0-9-]+\.(?:internal|local|localdomain)\b', re.IGNORECASE),
    re.compile(r'\bhost\.docker\.internal\b', re.IGNORECASE),
    # 回环：localhost 与 127.0.0.1 / [::1] 同判（INT-2612）。
    # \b 前后都是非单词字符，可命中 http://localhost:15000 与裸 localhost。
    re.compile(r'\blocalhost\b', re.IGNORECASE),
    re.compile(r'\[::1\]'),
)


__all__ = ['GuardIssue', 'GuardLimits', 'SkillGuard']
