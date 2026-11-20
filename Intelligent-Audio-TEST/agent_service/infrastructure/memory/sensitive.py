# -*- coding: utf-8 -*-
"""敏感信息扫描（INT-2490，§8.6 第 6 条）。

规则配置化：``agent_service/config/memory_sensitive_rules.json``（可用
``AGENT_MEMORY_SENSITIVE_RULES`` 覆盖路径）。每条规则：

- ``name``：规则名（进审计，不落命中明文）；
- ``pattern``：Python 正则；
- ``action``：``block`` 整笔拒绝 / ``redact`` 脱敏后放行。

扫描结论只回规则名与掩码片段；命中明文一律不返回、不落日志、不进审计。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from agent_service.domain.enums import SensitiveRuleAction
from agent_service.domain.model.memory import SensitiveFinding

logger = logging.getLogger(__name__)

REDACTED_TOKEN = '[已脱敏]'
_RULE_NAME = re.compile(r'^[a-z][a-z0-9_]{0,63}$')


@dataclass(frozen=True)
class SensitiveRule:
    name: str
    pattern: str
    action: SensitiveRuleAction

    def compile(self) -> 're.Pattern':
        return re.compile(self.pattern)


@dataclass(frozen=True)
class ScanOutcome:
    """扫描结论：``blocked`` 为真时不得生成提案。"""

    blocked: bool
    content: str
    findings: Tuple[SensitiveFinding, ...] = field(default_factory=tuple)

    @property
    def rules(self) -> Tuple[str, ...]:
        return tuple(f.rule for f in self.findings)


def _mask(matched: str) -> str:
    """命中片段只留长度信息，任何明文都不进结论。"""
    return f'***({len(matched)} chars)'


class SensitiveScanner:
    def __init__(self, rules: Sequence[SensitiveRule]):
        compiled: List[Tuple[SensitiveRule, 're.Pattern']] = []
        for rule in rules:
            if not _RULE_NAME.match(rule.name):
                raise ValueError(f'敏感信息规则名非法：{rule.name!r}')
            compiled.append((rule, rule.compile()))
        self._compiled = tuple(compiled)

    @property
    def rules(self) -> Tuple[SensitiveRule, ...]:
        return tuple(rule for rule, _ in self._compiled)

    def scan(self, content: str) -> ScanOutcome:
        text = content or ''
        findings: List[SensitiveFinding] = []
        blocked = False
        for rule, pattern in self._compiled:
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            findings.append(SensitiveFinding(
                rule=rule.name, action=rule.action,
                masked=_mask(matches[0].group(0))))
            if rule.action is SensitiveRuleAction.BLOCK:
                blocked = True
            else:
                text = pattern.sub(REDACTED_TOKEN, text)
        return ScanOutcome(blocked=blocked, content=text,
                           findings=tuple(findings))


def load_sensitive_rules(path: str) -> Tuple[SensitiveRule, ...]:
    """读取规则文件；缺失 / 非法直接抛错（记忆写入不能无扫描放行）。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f'敏感信息规则文件不存在：{file_path}')
    payload = json.loads(file_path.read_text(encoding='utf-8'))
    raw_rules = payload.get('rules') if isinstance(payload, dict) else None
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError(f'敏感信息规则为空：{file_path}')
    rules: List[SensitiveRule] = []
    for item in raw_rules:
        try:
            rules.append(SensitiveRule(
                name=str(item['name']),
                pattern=str(item['pattern']),
                action=SensitiveRuleAction(str(item['action'])),
            ))
        except (KeyError, ValueError) as exc:
            raise ValueError(f'敏感信息规则非法：{item}（{exc}）')
    return tuple(rules)


__all__ = [
    'REDACTED_TOKEN', 'ScanOutcome', 'SensitiveRule', 'SensitiveScanner',
    'load_sensitive_rules',
]
