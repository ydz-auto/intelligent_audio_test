# -*- coding: utf-8 -*-
"""文件式长期记忆领域对象（INT-2490，方案 §8.6 / §8.6.1）。

不建表、不走向量：文件树即数据模型。这里只定义纯领域结构，路径构造与
``rg`` 检索都在 infrastructure，审批占位与审计在 application。

隔离不变量（§8.6.1）：

- 路径一律由服务端从登录身份构造（tenant_id + owner_id），模型输入里没有
  任何路径字段；
- 检索结果只返回相对路径，不含绝对路径，也不回报「存在但无权」；
- 写入只能落到调用者自己的目录，且必须经审批后才落盘。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agent_service.domain.enums import (
    MemoryScope, MemorySection, MemoryWriteStatus, SensitiveRuleAction,
)
from shared.utils.time_utils import utcnow

# 记忆文件相对路径（相对 ``tenants/<tenant>/users/<owner>``）
USER_PROFILE_FILE = 'user_profile.md'
PROJECT_MEMORY_FILE = 'project_memory.md'
TOPICS_FILE = 'topics.md'

# 文件头（写入内容渲染规则的一部分：预演与落盘用同一份渲染结果）
USER_PROFILE_HEADER = '# 用户偏好'
PROJECT_MEMORY_HEADER = '# 项目记忆：{project_id}'
TOPICS_HEADER = '# 话题记录：{date}'
MEMORY_FILE_NOTE = ('> 由 memory_write 经审批写入的长期记忆；细节请用 '
                    'memory_search 按关键词检索，不要凭印象补全。')

# 注入摘要的标题（system 区段）
SUMMARY_HEADER = ('## 长期记忆摘要（仅用户偏好与项目规则；细节用 '
                  'memory_search 检索）')
SUMMARY_USER_BLOCK = '### 用户偏好'
SUMMARY_PROJECT_BLOCK = '### 项目规则'
SUMMARY_EMPTY = ''


@dataclass(frozen=True)
class SensitiveFinding:
    """一条敏感信息命中（只记规则名与掩码片段，不落明文）。"""

    rule: str
    action: SensitiveRuleAction
    masked: str

    def as_audit(self) -> Dict[str, str]:
        return {'rule': self.rule, 'action': self.action.value,
                'masked': self.masked}


@dataclass(frozen=True)
class MemoryHit:
    """一条检索命中（§8.6 接口草案 ``[{path, snippet, score, updated_at}]``）。"""

    path: str
    snippet: str
    score: int
    updated_at: Optional[datetime] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            'path': self.path,
            'snippet': self.snippet,
            'score': self.score,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True)
class MemorySearchResult:
    """检索结果；跨用户 / 跨租户恒为空且不带任何存在性提示。"""

    scope: MemoryScope
    hits: Tuple[MemoryHit, ...] = ()
    truncated: bool = False

    @property
    def count(self) -> int:
        return len(self.hits)

    def to_payload(self) -> Dict[str, Any]:
        return {
            'scope': self.scope.value,
            'count': self.count,
            'truncated': self.truncated,
            'items': [hit.to_payload() for hit in self.hits],
        }


@dataclass(frozen=True)
class MemoryWriteProposal:
    """审批占位提案：审批前不落盘；``preview`` 即批准后文件的完整内容。

    ``base_sha256`` 是提案时目标文件的摘要（文件不存在为 ``None``），批准
    时若文件已被其他提案改过则判冲突，绝不覆盖别人的写入。
    """

    approval_id: str
    tenant_id: str
    owner_id: int
    section: MemorySection
    path: str
    entry: str
    preview: str
    base_sha256: Optional[str]
    content_sha256: str
    reason: str = ''
    status: MemoryWriteStatus = MemoryWriteStatus.PENDING
    project_id: Optional[str] = None
    sensitive: Tuple[SensitiveFinding, ...] = field(default_factory=tuple)
    created_at: Optional[datetime] = None

    @property
    def artifact_ref(self) -> str:
        """提案的稳定引用（M2 审批服务接管后不变）。"""
        return f'memory://proposals/{self.approval_id}'

    def to_payload(self, *, include_preview: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'approval_id': self.approval_id,
            'artifact_ref': self.artifact_ref,
            'section': self.section.value,
            'path': self.path,
            'status': self.status.value,
            'project_id': self.project_id,
            'content_sha256': self.content_sha256,
            'reason': self.reason,
            'sensitive_redactions': [f.rule for f in self.sensitive],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_preview:
            payload['preview'] = self.preview
        return payload


@dataclass(frozen=True)
class MemoryMetadata:
    """管理端只读元数据：条数 + 更新时间，不含任何正文。"""

    user_profile_count: int = 0
    project_count: int = 0
    topic_file_count: int = 0
    total_bytes: int = 0
    quota_bytes: int = 0
    updated_at: Optional[datetime] = None
    user_root: str = ''

    def to_payload(self) -> Dict[str, Any]:
        return {
            'user_profile_count': self.user_profile_count,
            'project_count': self.project_count,
            'topic_file_count': self.topic_file_count,
            'total_bytes': self.total_bytes,
            'quota_bytes': self.quota_bytes,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True)
class MemoryAuditEvent:
    """一条记忆审计事件（§8.6：不落记忆正文）。"""

    action: str
    tool: str
    args_hash: str
    decision: str
    result_code: str
    tenant_id: str
    owner_id: int
    run_id: Optional[str] = None
    reason: str = ''
    rules: Tuple[str, ...] = ()
    created_at: Optional[datetime] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            'ts': (self.created_at or utcnow()).isoformat() + 'Z',
            'action': self.action,
            'tool': self.tool,
            'run_id': self.run_id,
            'tenant_id': self.tenant_id,
            'owner_id': self.owner_id,
            'args_hash': self.args_hash,
            'decision': self.decision,
            'result_code': self.result_code,
            'reason': self.reason,
            'rules': list(self.rules),
        }


def render_entry(content: str) -> str:
    """把一段内容渲染成记忆文件里的一条记录（多行缩进，保持确定性）。"""
    lines = [line.rstrip() for line in (content or '').strip().splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ''
    rendered = [f'- {lines[0]}']
    rendered.extend(f'  {line}' for line in lines[1:])
    return '\n'.join(rendered)


def render_file(heading: str, entry: str, *, existing: str = '') -> str:
    """渲染目标文件完整内容：已有正文原样保留，结尾追加一条新记录。"""
    body = (existing or '').rstrip()
    if not body:
        body = '\n\n'.join([heading, MEMORY_FILE_NOTE])
    return f'{body}\n{entry}\n'


def summary_lines(content: str, *, limit: int = 20) -> List[str]:
    """从记忆文件里抽摘要行：只取 ``- `` 记录，不展开细节。"""
    lines: List[str] = []
    for raw in (content or '').splitlines():
        line = raw.strip()
        if line.startswith('- '):
            lines.append(line)
            if len(lines) >= limit:
                break
    return lines


__all__ = [
    'MEMORY_FILE_NOTE', 'MemoryAuditEvent', 'MemoryHit', 'MemoryMetadata',
    'MemoryScope', 'MemorySearchResult', 'MemorySection', 'MemoryWriteProposal',
    'MemoryWriteStatus', 'PROJECT_MEMORY_FILE', 'PROJECT_MEMORY_HEADER',
    'SensitiveFinding', 'SensitiveRuleAction', 'SUMMARY_EMPTY',
    'SUMMARY_HEADER', 'SUMMARY_PROJECT_BLOCK', 'SUMMARY_USER_BLOCK',
    'TOPICS_FILE', 'TOPICS_HEADER', 'USER_PROFILE_FILE', 'USER_PROFILE_HEADER',
    'render_entry', 'render_file', 'summary_lines',
]
