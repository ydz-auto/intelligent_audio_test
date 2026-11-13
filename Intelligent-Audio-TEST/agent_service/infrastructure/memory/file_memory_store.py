# -*- coding: utf-8 -*-
"""文件式记忆树实现（INT-2490，方案 §8.6 / §8.6.1）。

数据模型就是文件树，不建表、不引向量库：

```text
<memory_root>/
  tenants/<tenant_id>/users/<owner_id>/
    user_profile.md
    projects/<project>/project_memory.md
    projects/<project>/<date>/topics.md
    sessions/                      # 目录预留（正文属 INT-2454 snapshot，不双写）
  .proposals/<tenant>/<owner>/<approval_id>.json   # 审批占位（不在用户树内）
  .audit/<tenant>.jsonl                            # 记忆审计（不含正文）
```

隔离：所有路径由 ``MemoryPaths`` 从身份构造；``project_id`` / ``approval_id``
是仅有的用户输入组件，均过白名单校验与软链 / 越界守卫。
"""
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from agent_service.domain.enums import (
    MemoryScope, MemorySection, MemoryWriteStatus,
)
from agent_service.domain.exceptions import (
    MemoryError, MemoryPathRejected, MemoryProposalConflict,
    MemoryProposalNotFound, MemorySensitiveRejected,
)
from agent_service.domain.model.memory import (
    PROJECT_MEMORY_FILE, PROJECT_MEMORY_HEADER, MemoryHit, MemoryMetadata,
    MemorySearchResult, MemoryWriteProposal, SUMMARY_HEADER,
    SUMMARY_PROJECT_BLOCK, SUMMARY_USER_BLOCK, TOPICS_FILE, TOPICS_HEADER,
    USER_PROFILE_FILE, USER_PROFILE_HEADER, render_entry, render_file,
    summary_lines,
)
from agent_service.domain.ports.memory import MemoryStorePort
from agent_service.domain.services.token_estimator import estimate_tokens
from agent_service.infrastructure.memory.paths import (
    PROJECTS_DIR, MemoryPaths, _is_link, safe_component,
)
from agent_service.infrastructure.memory.rg_search import RipgrepSearcher
from agent_service.infrastructure.memory.sensitive import (
    SensitiveRule, SensitiveScanner,
)

logger = logging.getLogger(__name__)

_INVALID_ARGUMENTS = 'MEMORY_INVALID_ARGUMENTS'
_MAX_CONTENT_CHARS = 4000


@dataclass(frozen=True)
class MemoryStoreSettings:
    """记忆文件树参数（全部来自 Config，不在代码里写死）。"""

    root: str
    skills_root: str = ''
    rg_binary: str = 'rg'
    rg_timeout_seconds: float = 5.0
    rg_max_file_bytes: int = 1024 * 1024
    search_default_limit: int = 10
    search_max_limit: int = 20
    max_query_chars: int = 200
    snippet_chars: int = 240
    summary_max_tokens: int = 600
    summary_max_projects: int = 5
    summary_lines_per_file: int = 20
    # 每用户磁盘上限（配置化）：本卡只回报用量，不实现自动清理（卡面边界）
    user_quota_bytes: int = 20 * 1024 * 1024
    sensitive_rules: Sequence[SensitiveRule] = field(default_factory=tuple)


def _sha256(text: str) -> str:
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def _mtime(path: Path) -> Optional[datetime]:
    try:
        stamp = path.stat().st_mtime
    except OSError:  # pragma: no cover - 文件刚被删除
        return None
    return datetime.fromtimestamp(stamp, timezone.utc).replace(tzinfo=None)


class FileMemoryStore(MemoryStorePort):
    def __init__(self, settings: MemoryStoreSettings, *,
                 searcher: Optional[RipgrepSearcher] = None):
        if not settings.root:
            raise ValueError('记忆根目录不能为空')
        self._settings = settings
        self._paths = MemoryPaths(
            Path(settings.root),
            skills_root=Path(settings.skills_root) if settings.skills_root else None)
        self._scanner = SensitiveScanner(settings.sensitive_rules)
        self._searcher = searcher or RipgrepSearcher(
            settings.rg_binary,
            timeout_seconds=settings.rg_timeout_seconds,
            snippet_chars=settings.snippet_chars,
            max_file_bytes=settings.rg_max_file_bytes)

    # ------------------------------------------------------------ 读：检索

    def search(self, *, tenant_id: str, owner_id: int, query: str,
               scope: MemoryScope, project_id: Optional[str] = None,
               limit: int = 10) -> MemorySearchResult:
        text = (query or '').strip()
        if not text:
            raise MemoryError('检索关键词不能为空', code=_INVALID_ARGUMENTS)
        if len(text) > self._settings.max_query_chars:
            raise MemoryError(
                f'检索关键词过长（上限 {self._settings.max_query_chars} 字符）',
                code=_INVALID_ARGUMENTS)
        capped = max(1, min(int(limit or self._settings.search_default_limit),
                            self._settings.search_max_limit))
        scope = MemoryScope(scope)
        base, prefix, glob = self._search_root(
            tenant_id=tenant_id, owner_id=owner_id, scope=scope,
            project_id=project_id)
        if base is None or not base.exists():
            return MemorySearchResult(scope=scope)
        matches = self._searcher.search(str(base), text, glob=glob)
        hits: List[MemoryHit] = []
        resolved_base = base.resolve()
        for match in matches:
            relative = self._relative(Path(match.path), resolved_base)
            if relative is None:
                continue
            path = f'{prefix}{relative}'
            hits.append(MemoryHit(
                path=path, snippet=match.snippet, score=max(1, match.matches),
                updated_at=_mtime(Path(match.path))))
        hits.sort(key=lambda hit: (
            -hit.score,
            -(hit.updated_at.timestamp() if hit.updated_at else 0.0),
            hit.path))
        return MemorySearchResult(
            scope=scope, hits=tuple(hits[:capped]),
            truncated=len(hits) > capped)

    def _search_root(self, *, tenant_id: str, owner_id: int,
                     scope: MemoryScope, project_id: Optional[str]):
        user_root = self._paths.user_root(tenant_id, owner_id)
        if scope is MemoryScope.USER:
            return user_root, '', None
        if scope is MemoryScope.PROJECT:
            if not project_id:
                raise MemoryPathRejected('PROJECT 范围必须提供 project_id')
            project = safe_component(project_id, 'project_id')
            base = self._paths.resolve_under(
                user_root, PROJECTS_DIR, project)
            return base, f'{PROJECTS_DIR}/{project}/', None
        if scope is MemoryScope.SKILL_REFERENCES:
            root = self._paths.skills_root
            if root is None or not root.exists():
                return None, '', None
            return root, '', '**/references/**'
        raise MemoryError(f'不支持的检索范围：{scope}', code=_INVALID_ARGUMENTS)

    @staticmethod
    def _relative(path: Path, base: Path) -> Optional[str]:
        try:
            return path.resolve().relative_to(base).as_posix()
        except (ValueError, OSError):  # pragma: no cover - 守卫兜底
            return None

    # ------------------------------------------------------------ 读：摘要 / 元数据

    def summary(self, *, tenant_id: str, owner_id: int,
                max_tokens: int) -> str:
        budget = min(
            int(max_tokens or self._settings.summary_max_tokens),
            self._settings.summary_max_tokens)
        user_root = self._paths.user_root(tenant_id, owner_id)
        if budget <= 0 or not user_root.exists():
            return ''
        lines: List[str] = [SUMMARY_HEADER]
        user_lines = self._file_lines(user_root, USER_PROFILE_FILE)
        if user_lines:
            lines.append(SUMMARY_USER_BLOCK)
            for line in user_lines:
                if not self._fits(lines + [line], budget):
                    break
                lines.append(line)
        projects = user_root / PROJECTS_DIR
        if projects.is_dir():
            count = 0
            for project_dir in sorted(p for p in projects.iterdir()
                                      if p.is_dir()):
                if count >= self._settings.summary_max_projects:
                    break
                project_lines = self._file_lines(
                    project_dir, PROJECT_MEMORY_FILE)
                if not project_lines:
                    continue
                if not self._fits(lines + [SUMMARY_PROJECT_BLOCK], budget):
                    break
                if SUMMARY_PROJECT_BLOCK not in lines:
                    lines.append(SUMMARY_PROJECT_BLOCK)
                for line in project_lines:
                    entry = f'- [{project_dir.name}] {line[2:]}'
                    if not self._fits(lines + [entry], budget):
                        break
                    lines.append(entry)
                count += 1
        if len(lines) <= 1:
            return ''
        return '\n'.join(lines)

    def _file_lines(self, base: Path, name: str) -> List[str]:
        try:
            content = self._paths.read_text_guarded(base, name)
        except MemoryPathRejected:
            return []
        if not content:
            return []
        return summary_lines(
            content, limit=self._settings.summary_lines_per_file)

    @staticmethod
    def _fits(lines: Sequence[str], budget: int) -> bool:
        return estimate_tokens('\n'.join(lines)) <= budget

    def metadata(self, *, tenant_id: str, owner_id: int) -> MemoryMetadata:
        user_root = self._paths.user_root(tenant_id, owner_id)
        meta = MemoryMetadata(
            quota_bytes=self._settings.user_quota_bytes, user_root=str(user_root))
        if not user_root.exists():
            return meta
        profile = user_root / USER_PROFILE_FILE
        profile_lines = 0
        total_bytes = 0
        latest: Optional[datetime] = None
        project_count = 0
        topic_count = 0
        for path in user_root.rglob('*'):
            if _is_link(path) or not path.is_file():
                continue
            stat = path.stat()
            total_bytes += stat.st_size
            stamp = _mtime(path)
            if stamp and (latest is None or stamp > latest):
                latest = stamp
            if path == profile:
                profile_lines = len(summary_lines(
                    path.read_text(encoding='utf-8', errors='replace'),
                    limit=10000))
            elif path.name == PROJECT_MEMORY_FILE and path.parent.parent.name == PROJECTS_DIR:
                project_count += 1
            elif path.name == TOPICS_FILE:
                topic_count += 1
        return replace(meta, user_profile_count=profile_lines,
                       project_count=project_count,
                       topic_file_count=topic_count,
                       total_bytes=total_bytes, updated_at=latest)

    def read_file(self, *, tenant_id: str, owner_id: int,
                  relative_path: str) -> str:
        components = [part for part in (relative_path or '').split('/') if part]
        if not components:
            raise MemoryPathRejected('读取路径不能为空')
        user_root = self._paths.user_root(tenant_id, owner_id)
        content = self._paths.read_text_guarded(user_root, *components)
        if content is None:
            raise MemoryPathRejected('目标文件不存在')
        return content

    # ------------------------------------------------------------ 写：审批占位

    def create_proposal(self, *, tenant_id: str, owner_id: int,
                        section: MemorySection, content: str,
                        project_id: Optional[str] = None,
                        reason: str = '') -> MemoryWriteProposal:
        section = MemorySection(section)
        text = (content or '').strip()
        if not text:
            raise MemoryError('记忆内容不能为空', code=_INVALID_ARGUMENTS)
        if len(text) > _MAX_CONTENT_CHARS:
            raise MemoryError(
                f'记忆内容过长（上限 {_MAX_CONTENT_CHARS} 字符）',
                code=_INVALID_ARGUMENTS)
        outcome = self._scanner.scan(text)
        if outcome.blocked:
            rules = '、'.join(sorted(set(outcome.rules)))
            raise MemorySensitiveRejected(
                f'内容含敏感信息（命中规则：{rules}），已拒绝写入')
        user_root = self._paths.ensure_user_tree(tenant_id, owner_id)
        components, heading = self._target(section, project_id)
        target = self._paths.resolve_under(user_root, *components)
        existing = self._read_optional(target)
        entry = render_entry(outcome.content)
        preview = render_file(heading, entry, existing=existing or '')
        proposal = MemoryWriteProposal(
            approval_id=uuid4().hex,
            tenant_id=safe_component(tenant_id, 'tenant_id'),
            owner_id=owner_id, section=section,
            path='/'.join(components), entry=entry, preview=preview,
            base_sha256=_sha256(existing) if existing is not None else None,
            content_sha256=_sha256(entry),
            reason=(reason or '').strip()[:500],
            project_id=(safe_component(project_id, 'project_id')
                        if project_id else None),
            sensitive=outcome.findings,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self._save_proposal(proposal)
        return proposal

    def _target(self, section: MemorySection,
                project_id: Optional[str]) -> Tuple[Tuple[str, ...], str]:
        if section is MemorySection.USER_PROFILE:
            return (USER_PROFILE_FILE,), USER_PROFILE_HEADER
        if not project_id:
            raise MemoryPathRejected(f'{section.value} 写入必须提供 project_id')
        project = safe_component(project_id, 'project_id')
        if section is MemorySection.PROJECT_MEMORY:
            return ((PROJECTS_DIR, project, PROJECT_MEMORY_FILE),
                    PROJECT_MEMORY_HEADER.format(project_id=project))
        date = datetime.now(timezone.utc).date().isoformat()
        return ((PROJECTS_DIR, project, date, TOPICS_FILE),
                TOPICS_HEADER.format(date=date))

    def _read_optional(self, target: Path) -> Optional[str]:
        if not target.exists():
            return None
        if not target.is_file():
            raise MemoryPathRejected('目标不是普通文件')
        return target.read_text(encoding='utf-8', errors='replace')

    def pending_proposals(self, *, tenant_id: str,
                          owner_id: int) -> Sequence[MemoryWriteProposal]:
        root = self._paths.proposal_root(tenant_id, owner_id)
        if not root.is_dir():
            return ()
        items: List[MemoryWriteProposal] = []
        for path in sorted(root.glob('*.json')):
            proposal = self._read_proposal_file(path)
            if proposal is not None \
                    and proposal.status is MemoryWriteStatus.PENDING:
                items.append(proposal)
        items.sort(key=lambda item: item.created_at or datetime.min)
        return tuple(items)

    def approve(self, *, tenant_id: str, owner_id: int,
                approval_id: str) -> MemoryWriteProposal:
        proposal = self._load_proposal(tenant_id, owner_id, approval_id)
        if proposal.status is not MemoryWriteStatus.PENDING:
            return proposal  # 幂等：已处理过的提案不产生第二次副作用
        user_root = self._paths.user_root(tenant_id, owner_id)
        components = tuple(proposal.path.split('/'))
        target = self._paths.resolve_under(user_root, *components)
        existing = self._read_optional(target)
        current = _sha256(existing) if existing is not None else None
        if current != proposal.base_sha256:
            raise MemoryProposalConflict(
                '目标文件已被其它写入改动，请重新提交记忆写入（未落盘）')
        self._paths.write_text_guarded(user_root, components, proposal.preview)
        return self._set_status(proposal, MemoryWriteStatus.APPROVED)

    def reject(self, *, tenant_id: str, owner_id: int,
               approval_id: str) -> MemoryWriteProposal:
        proposal = self._load_proposal(tenant_id, owner_id, approval_id)
        if proposal.status is not MemoryWriteStatus.PENDING:
            return proposal
        return self._set_status(proposal, MemoryWriteStatus.REJECTED)

    # ------------------------------------------------------------ 提案存储

    def _proposal_path(self, tenant_id: str, owner_id: int,
                       approval_id: str) -> Path:
        root = self._paths.proposal_root(tenant_id, owner_id)
        name = f'{safe_component(approval_id, "approval_id")}.json'
        return self._paths.resolve_under(root, name)

    def _save_proposal(self, proposal: MemoryWriteProposal) -> None:
        path = self._proposal_path(
            proposal.tenant_id, proposal.owner_id, proposal.approval_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._proposal_payload(proposal)
        tmp = path.with_name(f'.{path.name}.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding='utf-8', newline='\n')
        os.replace(str(tmp), str(path))

    def _load_proposal(self, tenant_id: str, owner_id: int,
                       approval_id: str) -> MemoryWriteProposal:
        path = self._proposal_path(tenant_id, owner_id, approval_id)
        proposal = self._read_proposal_file(path)
        if proposal is None:
            raise MemoryProposalNotFound('提案不存在或无权访问')
        return proposal

    def _read_proposal_file(self, path: Path) -> Optional[MemoryWriteProposal]:
        if not path.is_file() or _is_link(path):
            return None
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):  # pragma: no cover - 损坏的提案文件
            logger.warning('记忆提案文件损坏：%s', path.name)
            return None
        try:
            return MemoryWriteProposal(
                approval_id=str(payload['approval_id']),
                tenant_id=str(payload['tenant_id']),
                owner_id=int(payload['owner_id']),
                section=MemorySection(payload['section']),
                path=str(payload['path']),
                entry=str(payload.get('entry') or ''),
                preview=str(payload.get('preview') or ''),
                base_sha256=payload.get('base_sha256'),
                content_sha256=str(payload.get('content_sha256') or ''),
                reason=str(payload.get('reason') or ''),
                status=MemoryWriteStatus(payload.get('status', 'PENDING')),
                project_id=payload.get('project_id'),
                created_at=(datetime.fromisoformat(payload['created_at'])
                            if payload.get('created_at') else None),
            )
        except (KeyError, ValueError):
            logger.warning('记忆提案字段非法：%s', path.name)
            return None

    def _set_status(self, proposal: MemoryWriteProposal,
                    status: MemoryWriteStatus) -> MemoryWriteProposal:
        updated = replace(proposal, status=status)
        self._save_proposal(updated)
        return updated

    @staticmethod
    def _proposal_payload(proposal: MemoryWriteProposal) -> Dict[str, Any]:
        return {
            'approval_id': proposal.approval_id,
            'tenant_id': proposal.tenant_id,
            'owner_id': proposal.owner_id,
            'section': proposal.section.value,
            'path': proposal.path,
            'entry': proposal.entry,
            'preview': proposal.preview,
            'base_sha256': proposal.base_sha256,
            'content_sha256': proposal.content_sha256,
            'reason': proposal.reason,
            'status': proposal.status.value,
            'project_id': proposal.project_id,
            'created_at': (proposal.created_at.isoformat()
                           if proposal.created_at else None),
        }


__all__ = ['FileMemoryStore', 'MemoryStoreSettings']
