# -*- coding: utf-8 -*-
"""长期记忆应用服务（INT-2490，方案 §8.6 / §8.6.1）。

职责：

1. **工具语义**：``memory_search``（READ）与 ``memory_write``（WRITE，提案）
   的入参收敛、结果结构与错误码映射；
2. **审计**：每次检索 / 写入（含拒绝与审批决议）追加一条 JSONL，只写
   ``run_id / tool / args_hash / decision / result_code``，**不落记忆正文**；
3. **会话注入**：会话开始的摘要只含用户偏好与项目规则，token 受配置上限
   约束（细节交 ``memory_search``）；
4. **管理端**：只读元数据 + break-glass 读取（带权限校验与审计）。

审批边界：``memory_write`` 的正文**不入库**（§8.6 / §10 审计不落正文），
因此不并入 INT-2466 的 ``agent_approval`` 通用审批表（那张表要求 proposal
落库）；它继续使用文件式提案：``propose_write`` 只生成提案不落盘，审批
动作经由本服务的 ``approve`` / ``reject``（REST 见
``/api/v1/agent/memory/proposals``）。业务写工具的通用审批链见
``application/approval_service.py``。
"""
import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from agent_service.domain.enums import MemoryScope, MemorySection
from agent_service.domain.exceptions import (
    MemoryError, MemoryPathRejected, MemoryPermissionDenied,
    MemoryProposalConflict, MemoryProposalNotFound, MemorySensitiveRejected,
)
from agent_service.domain.model.memory import MemoryAuditEvent
from agent_service.domain.ports.memory import MemoryStorePort
from agent_service.domain.services.token_estimator import estimate_tokens
from shared.constants.permissions import WILDCARD_PERMISSION
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)

# 工具结果错误码（方案 §6.1 固定的九个取值；记忆细分码只进审计）
PERMISSION_DENIED = 'PERMISSION_DENIED'
INVALID_ARGUMENTS = 'INVALID_ARGUMENTS'
TOOL_NOT_ENABLED = 'TOOL_NOT_ENABLED'
NOT_FOUND = 'NOT_FOUND'
APPROVAL_REQUIRED = 'APPROVAL_REQUIRED'
UPSTREAM_UNAVAILABLE = 'UPSTREAM_UNAVAILABLE'
UPSTREAM_ERROR = 'UPSTREAM_ERROR'

# 记忆细分码 → 工具结果错误码
_MEMORY_ERROR_CODES: Dict[str, str] = {
    'MEMORY_PATH_REJECTED': INVALID_ARGUMENTS,
    'MEMORY_SENSITIVE_CONTENT': INVALID_ARGUMENTS,
    'MEMORY_INVALID_ARGUMENTS': INVALID_ARGUMENTS,
    'MEMORY_PROPOSAL_NOT_FOUND': NOT_FOUND,
    'MEMORY_WRITE_CONFLICT': INVALID_ARGUMENTS,
    'MEMORY_BACKEND_UNAVAILABLE': UPSTREAM_UNAVAILABLE,
    'MEMORY_PERMISSION_DENIED': PERMISSION_DENIED,
    'MEMORY_ERROR': UPSTREAM_ERROR,
}

# break-glass 读取权限码（RBAC 尚无 memory 域：当前无人持有 = fail-closed）
BREAK_GLASS_PERMISSION = 'memory:break_glass'

MEMORY_SEARCH_TOOL = 'memory_search'
MEMORY_WRITE_TOOL = 'memory_write'


def tool_error_code(code: str) -> str:
    """记忆细分码 → 固定工具错误码集合。"""
    return _MEMORY_ERROR_CODES.get(code, UPSTREAM_ERROR)


def _args_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class MemoryServiceSettings:
    inject_max_tokens: int = 600
    search_default_limit: int = 10


class MemoryService:
    """工具 / REST 共用的记忆门面（审计 + 审批占位）。"""

    def __init__(self, store: MemoryStorePort, *,
                 settings: Optional[MemoryServiceSettings] = None,
                 audit_path: Optional[str] = None):
        self._store = store
        self._settings = settings or MemoryServiceSettings()
        self._audit_path = audit_path
        self._audit_lock = threading.Lock()

    # ------------------------------------------------------------ 工具：读

    def search(self, *, tenant_id: str, owner_id: int,
               run_id: Optional[str] = None, query: str = '',
               scope: str = MemoryScope.USER.value,
               project_id: Optional[str] = None,
               limit: Optional[int] = None) -> Dict[str, Any]:
        try:
            parsed_scope = MemoryScope(str(scope).strip().upper())
        except ValueError:
            raise MemoryError(f'不支持的检索范围：{scope}',
                              code='MEMORY_INVALID_ARGUMENTS')
        args_hash = _args_hash({'query': query, 'scope': parsed_scope.value,
                                'project_id': project_id})
        try:
            result = self._store.search(
                tenant_id=tenant_id, owner_id=owner_id, query=query,
                scope=parsed_scope, project_id=project_id,
                limit=(limit if limit is not None
                       else self._settings.search_default_limit))
        except MemoryError as exc:
            self._audit(tenant_id, owner_id, run_id, 'memory_search',
                        MEMORY_SEARCH_TOOL, args_hash, 'deny', exc.code,
                        reason=str(exc)[:200])
            raise
        self._audit(tenant_id, owner_id, run_id, 'memory_search',
                    MEMORY_SEARCH_TOOL, args_hash, 'allow', 'OK')
        return result.to_payload()

    # ------------------------------------------------------------ 工具：写（提案）

    def propose_write(self, *, tenant_id: str, owner_id: int,
                      run_id: Optional[str] = None, section: str = '',
                      content: str = '', project_id: Optional[str] = None,
                      reason: str = '') -> Dict[str, Any]:
        args_hash = _args_hash({
            'section': section, 'content_sha256': hashlib.sha256(
                (content or '').encode('utf-8')).hexdigest(),
            'project_id': project_id, 'reason': reason,
        })
        try:
            parsed_section = MemorySection(str(section).strip().upper())
        except ValueError:
            exc = MemoryError(f'不支持的写入区段：{section}',
                              code='MEMORY_INVALID_ARGUMENTS')
            self._audit(tenant_id, owner_id, run_id, 'memory_write',
                        MEMORY_WRITE_TOOL, args_hash, 'deny', exc.code,
                        reason=str(exc)[:200])
            raise exc
        try:
            proposal = self._store.create_proposal(
                tenant_id=tenant_id, owner_id=owner_id,
                section=parsed_section,
                content=content, project_id=project_id, reason=reason)
        except MemoryError as exc:
            decision = ('deny' if isinstance(
                exc, (MemorySensitiveRejected, MemoryPathRejected)) else 'error')
            self._audit(tenant_id, owner_id, run_id, 'memory_write',
                        MEMORY_WRITE_TOOL, args_hash, decision, exc.code,
                        reason=str(exc)[:200])
            raise
        self._audit(tenant_id, owner_id, run_id, 'memory_write',
                    MEMORY_WRITE_TOOL, args_hash, APPROVAL_REQUIRED.lower(),
                    APPROVAL_REQUIRED,
                    rules=tuple(f.rule for f in proposal.sensitive))
        return proposal.to_payload(include_preview=False)

    # ------------------------------------------------------------ 会话注入

    def system_summary(self, *, tenant_id: str, owner_id: int) -> str:
        """会话开始注入：只含偏好与项目规则摘要，受 token 上限约束。"""
        try:
            summary = self._store.summary(
                tenant_id=tenant_id, owner_id=owner_id,
                max_tokens=self._settings.inject_max_tokens)
        except Exception:  # noqa: BLE001 - 注入失败不能拖垮模型 Loop
            logger.warning('长期记忆摘要读取失败（本次不注入）', exc_info=True)
            return ''
        if not summary:
            return ''
        if estimate_tokens(summary) > self._settings.inject_max_tokens:
            # 双保险：实现层已按预算裁剪；这里再兜底一次，绝不超上限注入。
            logger.error('长期记忆摘要超过注入上限，已丢弃')
            return ''
        return summary

    # ------------------------------------------------------------ 管理端 / 审批占位

    def metadata(self, *, tenant_id: str, owner_id: int) -> Dict[str, Any]:
        return self._store.metadata(
            tenant_id=tenant_id, owner_id=owner_id).to_payload()

    def list_proposals(self, *, tenant_id: str,
                       owner_id: int) -> list:
        return [proposal.to_payload(include_preview=True)
                for proposal in self._store.pending_proposals(
                    tenant_id=tenant_id, owner_id=owner_id)]

    def approve(self, *, tenant_id: str, owner_id: int,
                approval_id: str,
                run_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            proposal = self._store.approve(
                tenant_id=tenant_id, owner_id=owner_id,
                approval_id=approval_id)
        except (MemoryProposalNotFound, MemoryProposalConflict) as exc:
            self._audit(tenant_id, owner_id, run_id, 'memory_write',
                        MEMORY_WRITE_TOOL,
                        _args_hash({'approval_id': approval_id}), 'deny',
                        exc.code, reason=str(exc)[:200])
            raise
        self._audit(tenant_id, owner_id, run_id, 'memory_write',
                    MEMORY_WRITE_TOOL,
                    _args_hash({'approval_id': approval_id}), 'allow', 'OK',
                    reason=f'approved:{proposal.path}')
        return proposal.to_payload(include_preview=True)

    def reject(self, *, tenant_id: str, owner_id: int, approval_id: str,
               run_id: Optional[str] = None) -> Dict[str, Any]:
        proposal = self._store.reject(
            tenant_id=tenant_id, owner_id=owner_id, approval_id=approval_id)
        self._audit(tenant_id, owner_id, run_id, 'memory_write',
                    MEMORY_WRITE_TOOL,
                    _args_hash({'approval_id': approval_id}), 'deny',
                    'MEMORY_WRITE_REJECTED',
                    reason=f'rejected:{proposal.path}')
        return proposal.to_payload(include_preview=False)

    def break_glass_read(self, *, tenant_id: str, owner_id: int,
                         relative_path: str, actor_id: int,
                         permissions: Sequence[str] = ()) -> Dict[str, Any]:
        """break-glass 读取：必须持有专用权限，且读取本身留审计。"""
        granted = set(permissions or ())
        if WILDCARD_PERMISSION not in granted \
                and BREAK_GLASS_PERMISSION not in granted:
            self._audit(tenant_id, owner_id, None, 'memory_break_glass',
                        'memory_break_glass',
                        _args_hash({'path': relative_path}), 'deny',
                        'MEMORY_PERMISSION_DENIED')
            raise MemoryPermissionDenied('无权读取长期记忆正文')
        content = self._store.read_file(
            tenant_id=tenant_id, owner_id=owner_id,
            relative_path=relative_path)
        self._audit(tenant_id, owner_id, None, 'memory_break_glass',
                    'memory_break_glass', _args_hash({'path': relative_path}),
                    'allow', 'OK', reason=f'actor:{actor_id}')
        return {'path': relative_path, 'content': content}

    # ------------------------------------------------------------ 审计

    def _audit(self, tenant_id: str, owner_id: int, run_id: Optional[str],
               action: str, tool: str, args_hash: str, decision: str,
               result_code: str, *, reason: str = '',
               rules: Tuple[str, ...] = ()) -> None:
        event = MemoryAuditEvent(
            action=action, tool=tool, args_hash=args_hash,
            decision=decision, result_code=result_code,
            tenant_id=tenant_id, owner_id=owner_id,
            run_id=run_id, reason=reason, rules=tuple(rules),
            created_at=utcnow())
        line = json.dumps(event.to_payload(), ensure_ascii=False)
        try:
            self._append_audit(tenant_id, line)
        except OSError:
            logger.exception('记忆审计写入失败 action=%s code=%s',
                             action, result_code)
            if action == 'memory_write' and result_code == 'OK':
                # 「写后落审计」是硬要求：落盘成功但不能留审计 → 显式失败。
                raise MemoryError('记忆审计不可用，写入结果无法审计',
                                  code='MEMORY_AUDIT_UNAVAILABLE')

    def _append_audit(self, tenant_id: str, line: str) -> None:
        if not self._audit_path:
            return
        from pathlib import Path

        # 文件名只保留安全字符：tenant_id 来自身份头，不能让它拼出路径
        name = re.sub(r'[^A-Za-z0-9._-]', '_', str(tenant_id or ''))[:64]
        path = Path(self._audit_path) / f'{name or "_"}.jsonl'
        with self._audit_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'a', encoding='utf-8', newline='\n') as handle:
                handle.write(line + '\n')


__all__ = [
    'APPROVAL_REQUIRED', 'BREAK_GLASS_PERMISSION', 'INVALID_ARGUMENTS',
    'MEMORY_SEARCH_TOOL', 'MEMORY_WRITE_TOOL', 'MemoryService',
    'MemoryServiceSettings', 'NOT_FOUND', 'PERMISSION_DENIED',
    'TOOL_NOT_ENABLED', 'UPSTREAM_ERROR', 'UPSTREAM_UNAVAILABLE',
    'tool_error_code',
]
