# -*- coding: utf-8 -*-
"""设备 UI 探索编排（INT-2492，方案 §6.6「UI 探索会话」/ §6.7）。

职责边界：

- **本模块**：探索会话状态（设备租约 / 预算 / 首个动作审批后的计划放行 /
  动作与页面轨迹）、安全停止（登录 / 验证码 / 破坏性动作）、``ui_trace.json``
  落产物表（``agent_artifact``，kind = ``UI_TRACE``）。所有口径（枚举、裁剪、
  diff、预算、trace 结构）来自 ``shared.agent_tools.ui_exploration``。
- **设备端口**（``UiDevicePort`` / ``DeviceLeasePort``）：读树 / 执行动作 / 租约；
  设备通道未接时端口为 ``None``，工具返回明确的 ``EXPLORATION_UNAVAILABLE``，
  不伪造空树、不静默成功。
- **ToolGateway**：权限 / 参数 Schema / 审批门禁 / 审计仍在网关；本模块只在
  网关放行之后执行副作用。

审批口径（卡面）：``ui_action`` 是本 run 内首个动作时走通用写审批；审批通过
后的**同一探索计划**（同 run + 同设备）后续动作自动放行（``plan_approved``），
直到预算 / 安全停止或 run 结束。``dry_run`` 不下发设备动作、不产生副作用，
因此不进入审批。
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence

from agent_service.domain.model.entities import AgentArtifact
from agent_service.domain.ports.artifact_store import ArtifactStore
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.domain.ports.ui_device import (
    DeviceLeasePort, UiDeviceError, UiDevicePort,
)
from agent_service.domain.repositories import ArtifactRepository
from shared.agent_tools import ui_exploration as ux
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)

EXPLORATION_UNAVAILABLE = 'EXPLORATION_UNAVAILABLE'
DEVICE_NOT_LEASED = 'DEVICE_NOT_LEASED'
DEVICE_UNAVAILABLE = 'DEVICE_UNAVAILABLE'
INVALID_ARGUMENTS = 'INVALID_ARGUMENTS'
BUDGET_EXCEEDED = 'BUDGET_EXCEEDED'
DESTRUCTIVE_BLOCKED = 'DESTRUCTIVE_BLOCKED'
LOGIN_REQUIRED = 'LOGIN_REQUIRED'
CAPTCHA = 'CAPTCHA'
EXPLORATION_STOPPED = 'EXPLORATION_STOPPED'

#: 停止原因 → 工具错误码（DONE 不是错误）
_STOP_ERROR_CODES: Dict[ux.ExplorationStopReason, str] = {
    ux.ExplorationStopReason.BUDGET: BUDGET_EXCEEDED,
    ux.ExplorationStopReason.DESTRUCTIVE_BLOCKED: DESTRUCTIVE_BLOCKED,
    ux.ExplorationStopReason.LOGIN_REQUIRED: LOGIN_REQUIRED,
    ux.ExplorationStopReason.CAPTCHA: CAPTCHA,
    ux.ExplorationStopReason.USER_CANCEL: EXPLORATION_STOPPED,
}

#: 停止后交回用户的说明（模型据此直接向用户交代，不重试绕过）
_STOP_MESSAGES: Dict[ux.ExplorationStopReason, str] = {
    ux.ExplorationStopReason.BUDGET: '探索预算用尽（动作数 / 时长到达上限），'
                                     '已停止并交回；请确认后再开始新的探索计划。',
    ux.ExplorationStopReason.DESTRUCTIVE_BLOCKED: '目标动作属于破坏性操作'
                                                  '（卸载 / 重启 / 支付 / 删账号等），平台一律拒绝。',
    ux.ExplorationStopReason.LOGIN_REQUIRED: '当前页面需要登录 / 实名验证，'
                                             '已停止探索并交回用户接管，不尝试绕过。',
    ux.ExplorationStopReason.CAPTCHA: '当前页面出现验证码 / 人机验证，'
                                      '已停止探索并交回用户接管，不尝试绕过。',
    ux.ExplorationStopReason.USER_CANCEL: '探索已结束。',
}

#: run 终态 → 探索停止原因（取消不能再记成 DONE；失败原因走 trace 的
#: ``run_status`` / ``run_error``，不硬塞进 Enum 之外的值）
_STOP_REASON_BY_RUN_STATUS: Dict[str, ux.ExplorationStopReason] = {
    'CANCELLED': ux.ExplorationStopReason.USER_CANCEL,
    'BUDGET_EXCEEDED': ux.ExplorationStopReason.BUDGET,
}

#: trace 里保存的 run 失败原因长度上限（异常栈可能很长，截断保留关键信息）
_RUN_ERROR_MAX_CHARS = 500

#: 会话已被其他线程停止 / run 已收口时，等待锁的调用方拿到的说明
_SESSION_CLOSED_MESSAGE = ('探索会话已结束（已被停止或 run 已收口），'
                           '请重新开始新的探索计划。')


class ExplorationError(RuntimeError):
    """探索失败：``code`` 直接作为工具错误码，``message`` 回灌模型。"""

    def __init__(self, code: str, message: str, *,
                 payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


@dataclass
class _Session:
    run_id: str
    session_id: str
    device_id: int
    platform: str
    lease: Any
    #: 同一 (run, device) 的探索调用串行化（预算判定 + 自增、轨迹 / 产物登记
    #: 都在这个临界区内）。同一轮工具调用会被编排器并行下发（默认 8 路），
    #: 没有这把锁时预算硬上限与「一次探索一条 ui_trace 产物」都会被绕过。
    lock: Any = field(default_factory=threading.RLock, repr=False,
                      compare=False)
    #: 设备租约的获取方式（DISTRIBUTED / SINGLE_INSTANCE / DEGRADED / UNKNOWN）
    #: 与是否降级放行：Redis 不可用时底层锁会放行，必须留痕（P3-2）。
    lease_mode: str = 'UNKNOWN'
    lease_degraded: bool = False
    started_monotonic: float = field(default_factory=time.monotonic)
    actions: int = 0
    action_log: List[Dict[str, Any]] = field(default_factory=list)
    pages: List[Dict[str, Any]] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    snapshot_id: str = ''
    coverage: Dict[str, Any] = field(default_factory=dict)
    approved: bool = False
    approval_id: Optional[str] = None
    stop_reason: Optional[ux.ExplorationStopReason] = None
    artifact_uri: Optional[str] = None
    artifact_id: Optional[str] = None
    #: run 收口时的终态与失败原因（写进 trace，取消 / 失败也要留痕）
    run_status: Optional[str] = None
    run_error: Optional[str] = None
    #: 最近一次轨迹的校验报告（工具结果回灌，产物不合格不静默成功）
    trace_report: Optional[Dict[str, Any]] = None

    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_monotonic)

    def elapsed_ms(self) -> int:
        return int(self.elapsed_seconds() * 1000)


class _CreationLock:
    """按 ``(run, device)`` 的一次性建会话锁（引用计数，用完即删）。

    同一时刻可能有多个并发首次调用：只允许一个线程去抢设备租约并登记会话，
    其余线程等它建好后复用同一会话——否则第二个调用会因租约已被占而误报
    ``DEVICE_NOT_LEASED``，或（注入 fake 时）覆盖旧会话泄漏租约。
    """

    __slots__ = ('lock', 'users')

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.users = 0


class ExplorationService:
    """探索会话编排（进程内状态；设备租约与产物落库为跨进程事实）。

    并发口径：编排器会把同一轮的多个工具调用并行下发（默认 8 路），因此
    一切会话状态都只在**该会话自己的锁**里读写——``ui_tree`` / ``ui_action``
    的整个流程、预算检查 + 动作自增、``ui_trace`` 与 ``agent_artifact`` 的
    登记都串行执行；``_sessions`` 字典本身由 ``_sessions_lock`` 保护，
    建会话则按 ``(run, device)`` 再加一把一次性创建锁（避免两个并发首次
    调用各自抢租约导致误报 ``DEVICE_NOT_LEASED`` / 泄漏租约）。
    """

    def __init__(self, *, devices: Optional[UiDevicePort],
                 leases: DeviceLeasePort,
                 artifacts: Optional[ArtifactRepository] = None,
                 store: Optional[ArtifactStore] = None,
                 budget: Optional[ux.ExplorationBudget] = None):
        self._devices = devices
        self._leases = leases
        self._artifacts = artifacts
        self._store = store
        self._budget = budget or ux.ExplorationBudget()
        self._sessions: Dict[tuple, _Session] = {}
        self._sessions_lock = threading.RLock()
        #: (run, device) → 一次性建会话锁（带引用计数，用完即删，不随 run 累积）
        self._creating: Dict[tuple, '_CreationLock'] = {}

    # ------------------------------------------------------------ 状态查询

    @property
    def available(self) -> bool:
        """设备通道是否已接入（未接入时 ui_tree / ui_action 显式报不可用）。"""
        return self._devices is not None

    def plan_approved(self, run_id: str, device_id: Any) -> bool:
        """同一探索计划（同 run + 同设备）是否已审批通过首个动作。"""
        key = self._key(run_id, device_id)
        with self._sessions_lock:
            session = self._sessions.get(key)
        if session is None:
            return False
        with session.lock:
            return bool(session.approved and session.stop_reason is None)

    def mark_approved(self, run_id: str, device_id: Any,
                      approval_id: Optional[str]) -> None:
        """首个动作审批通过：后续同计划动作自动放行（由网关在放行路径调用）。"""
        key = self._key(run_id, device_id)
        with self._sessions_lock:
            session = self._sessions.get(key)
        if session is None:
            return
        with session.lock:
            session.approved = True
            session.approval_id = approval_id

    def close_run(self, run_id: str, *, status: Any = None,
                  error: Optional[str] = None) -> None:
        """run 收口：结束会话、释放租约、落最后一版轨迹（不掩盖 run 状态）。

        ``status`` 取 run 的终态（``RunStatus`` 或字符串）：取消记
        ``USER_CANCEL``，预算超限记 ``BUDGET``；失败时把失败原因写进
        ``trace.run_status`` / ``trace.run_error``。都不传时保持原口径
        （``DONE``），便于旧调用方。

        每个会话在自己的锁里收尾：并发的 ``ui_action`` 要么先完成自己的
        一步，要么在拿到锁后发现会话已停止而明确失败，不会与收尾交叉写
        ``ui_trace`` / ``agent_artifact``。
        """
        run_status, reason = self._close_status(status)
        with self._sessions_lock:
            sessions = [(key, session)
                        for key, session in self._sessions.items()
                        if session.run_id == run_id]
        for key, session in sessions:
            with session.lock:
                if not self._is_registered(key, session):
                    continue
                try:
                    session.run_status = run_status
                    session.run_error = (str(error)[:_RUN_ERROR_MAX_CHARS]
                                         if error else None)
                    self._finalize(session, session.stop_reason or reason)
                finally:
                    self._drop_session(session)

    @staticmethod
    def _close_status(status: Any
                      ) -> tuple[Optional[str], ux.ExplorationStopReason]:
        if status is None:
            return None, ux.ExplorationStopReason.DONE
        value = str(getattr(status, 'value', status)).upper()
        reason = _STOP_REASON_BY_RUN_STATUS.get(value,
                                                ux.ExplorationStopReason.DONE)
        return value, reason

    # ------------------------------------------------------------ ui_tree

    def ui_tree(self, arguments: Dict[str, Any],
                context: ToolInvocationContext) -> Dict[str, Any]:
        """读取裁剪 UI 树（≤200 节点）+ 截图引用 + 与上次快照 diff。

        整个读取在会话锁内执行：并发调用会按 (run, device) 串行，快照 /
        diff 基准不会被两个线程同时轮转（否则 diff 基准会错乱）。
        """
        self._require_available()
        device_id = self._require_device_id(arguments)
        max_nodes = self._max_nodes(arguments.get('max_nodes'))
        include_screenshot = bool(arguments.get('include_screenshot', True))
        diff_with_last = bool(arguments.get('diff_with_last', True))
        with self._locked_session(context, device_id) as session:
            self._refuse_if_stopped(session)

            nodes, coverage = self._dump(session, max_nodes)
            cropped, stats = ux.crop_nodes(nodes, max_nodes)
            image_ref = None
            if include_screenshot:
                image_ref = self._screenshot(session)
                if image_ref:
                    session.screenshots.append(image_ref)
            # diff 的基准是「上一次快照」：session 里保留的就是上一版树与它的 id
            previous_id = session.snapshot_id or None
            diff = None
            if diff_with_last and session.nodes:
                diff = ux.diff_trees(session.nodes, cropped)
            self._rotate_snapshot(session, cropped, coverage)

            blocked = ux.detect_blocked_page(nodes)
            stop_reason = ux.stop_reason_for_page(blocked)
            payload: Dict[str, Any] = {
                'device_id': device_id,
                'platform': session.platform,
                'snapshot_id': session.snapshot_id,
                'node_count': stats['node_count'],
                'total_nodes': stats['total_nodes'],
                'truncated': stats['truncated'],
                'max_nodes': stats['max_nodes'],
                'nodes': ux.nodes_for_response(cropped),
                'screenshot_ref': image_ref,
                'diff_from_snapshot_id': previous_id,
                'diff': diff,
                'coverage': coverage,
                'stop_reason': stop_reason.value if stop_reason else None,
                'lease_mode': session.lease_mode,
                'lease_degraded': session.lease_degraded,
            }
            if blocked is not None:
                payload['blocked_page'] = blocked.value
                reason = stop_reason or ux.ExplorationStopReason.LOGIN_REQUIRED
                self._finalize(session, reason)
                self._drop_session(session)
                payload['message'] = _STOP_MESSAGES.get(reason)
            return payload

    # ------------------------------------------------------------ ui_action

    def ui_action(self, arguments: Dict[str, Any],
                  context: ToolInvocationContext,
                  approval_id: Optional[str] = None) -> Dict[str, Any]:
        """执行一个 UI 动作 → 新树 diff + 轨迹；首个动作后同计划自动放行。

        整个动作（预算判定 + 设备下发 + 动作编号自增 + 轨迹 / 产物登记）在
        会话锁内完成：同一 (run, device) 的并发调用串行执行，预算按「已实际
        下发动作数」原子判定，``ui_trace`` 的 index 严格递增且只登记一条
        ``agent_artifact``（INT-2492 终审 P2-1）。
        """
        self._require_available()
        device_id = self._require_device_id(arguments)
        action_type, params = self._action_arguments(arguments)
        # dry_run / validate 都是「不下发设备动作」：前者是预演，后者只做
        # 目标 / 安全 / 预算校验（写工具统一支持 dry_run / validate=true）。
        validate_only = bool(arguments.get('validate', False))
        dry_run = bool(arguments.get('dry_run', False)) or validate_only
        with self._locked_session(context, device_id) as session:
            self._refuse_if_stopped(session)

            # 预算：第 31 个动作 / 超 5 分钟前先停，不产生设备动作
            stop = self._budget.check_next(session.actions,
                                           session.elapsed_seconds())
            if stop is not None:
                self._stop(session, stop)

            # 首个动作前还没有快照：先读一页树作为定位与 diff 的基准
            # （目标元素必须在最近一次快照里存在，不能凭空定位）。
            if not session.nodes:
                nodes, coverage = self._dump(session, ux.DEFAULT_TREE_NODES)
                cropped, _stats = ux.crop_nodes(nodes, ux.DEFAULT_TREE_NODES)
                self._rotate_snapshot(session, cropped, coverage)

            # 已经停在登录 / 验证码 / 实名 / 支付页：直接交回，不在这些页面上做动作
            blocked = ux.detect_blocked_page(session.nodes)
            blocked_stop = ux.stop_reason_for_page(blocked)
            if blocked_stop is not None:
                self._stop(session, blocked_stop,
                           extra={'blocked_page': blocked.value})

            target = self._resolve_target(session, arguments.get('target'))
            if action_type.needs_target and target is None:
                raise ExplorationError(
                    INVALID_ARGUMENTS,
                    f'{action_type.value} 需要 target（id / resource_id / text），'
                    '且必须在最近一次 ui_tree 快照里能找到该元素')

            destructive = ux.detect_destructive(
                action_type.value, target, params)
            if destructive:
                self._stop(session,
                           ux.ExplorationStopReason.DESTRUCTIVE_BLOCKED,
                           extra={'matched_keyword': destructive,
                                  'action_type': action_type.value,
                                  'dry_run': dry_run})

            if dry_run:
                # 预演：不下发设备动作、不取新快照、**不落轨迹产物**（预演不是一次
                # 真实动作，登记成 UI_TRACE 会让 run 的产物列表出现一条 0 动作、
                # 校验不通过的轨迹）。返回「预计变化」= 当前树无变化，并显式标注
                # projected，避免模型把预演当成已生效。
                return {
                    'device_id': device_id,
                    'platform': session.platform,
                    'action_type': action_type.value,
                    'dry_run': True,
                    'validate_only': validate_only,
                    'applied': False,
                    'projected': True,
                    'trace_ref': None,
                    'trace_recorded': False,
                    'action_index': session.actions,
                    'tree_diff': {
                        'projected': True,
                        'counts': {'added': 0, 'removed': 0, 'changed': 0,
                                   'unchanged': len(session.nodes),
                                   'previous': len(session.nodes),
                                   'current': len(session.nodes)},
                        'notes': ['dry_run 未下发设备动作：页面不会变化，'
                                  '预计 diff 只在目标可见时给出（当前树不变）'],
                    },
                    'stop_reason': ux.ExplorationStopReason.DONE.value,
                    'lease_mode': session.lease_mode,
                    'lease_degraded': session.lease_degraded,
                    'budget': self._budget.as_dict(
                        session.actions, session.elapsed_seconds()),
                }

            performed = self._perform(session, action_type, target, params)
            session.actions += 1
            image_ref = self._screenshot(session)
            if image_ref:
                session.screenshots.append(image_ref)
            action = ux.build_action_record(
                index=session.actions, action_type=action_type.value,
                params=params, node=target, at_ms=session.elapsed_ms(),
                dry_run=False, applied=bool(performed.get('applied', True)),
                image_ref=image_ref)
            session.action_log.append(action)

            new_nodes, coverage = self._dump(session, ux.DEFAULT_TREE_NODES)
            cropped, _stats = ux.crop_nodes(new_nodes, ux.DEFAULT_TREE_NODES)
            diff = ux.diff_trees(session.nodes, cropped)
            self._rotate_snapshot(session, cropped, coverage)
            session.pages.append(ux.build_page_record(
                snapshot_id=session.snapshot_id, nodes=cropped,
                captured_ms=session.elapsed_ms(), screenshot_ref=image_ref))
            trace_ref = self._write_trace(session)

            blocked = ux.detect_blocked_page(new_nodes)
            stop_reason = ux.stop_reason_for_page(blocked)
            payload: Dict[str, Any] = {
                'device_id': device_id,
                'platform': session.platform,
                'action_type': action_type.value,
                'dry_run': False,
                'applied': bool(performed.get('applied', True)),
                'trace_ref': trace_ref,
                'action_index': session.actions,
                'snapshot_id': session.snapshot_id,
                'tree_diff': diff,
                'stop_reason': (stop_reason or
                                ux.ExplorationStopReason.DONE).value,
                'trace_validation': self._trace_summary(session),
                'lease_mode': session.lease_mode,
                'lease_degraded': session.lease_degraded,
                'budget': self._budget.as_dict(
                    session.actions, session.elapsed_seconds()),
            }
            if blocked is not None and stop_reason is not None:
                payload['blocked_page'] = blocked.value
                payload['message'] = _STOP_MESSAGES.get(stop_reason)
                self._finalize(session, stop_reason)
                self._drop_session(session)
                payload['trace_ref'] = trace_ref
            elif context.approval is not None or approval_id:
                # 首个已审批动作：同一探索计划内后续自动放行
                # （RLock：同线程内再进会话锁，安全）
                self.mark_approved(context.run_id, device_id,
                                   approval_id or context.approval.approval_id)
            return payload

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _key(run_id: str, device_id: Any) -> tuple:
        try:
            normalized = int(device_id)
        except (TypeError, ValueError):
            normalized = str(device_id)
        return (str(run_id), normalized)

    def _require_available(self) -> None:
        if self._devices is None:
            raise ExplorationError(
                EXPLORATION_UNAVAILABLE,
                '设备 UI 通道未接入：无法读取 UI 树 / 执行 UI 动作。'
                '请先完成设备 UI 探索通道（设备服务 ui_tree / ui_action 适配），'
                '本工具不返回伪造的树。')

    @staticmethod
    def _require_device_id(arguments: Dict[str, Any]) -> int:
        value = arguments.get('device_id')
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ExplorationError(INVALID_ARGUMENTS,
                                   f'device_id 必须是正整数：{value}')
        return value

    @staticmethod
    def _max_nodes(value: Any) -> int:
        if value is None:
            return ux.DEFAULT_TREE_NODES
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExplorationError(INVALID_ARGUMENTS,
                                   f'max_nodes 必须是整数：{value}')
        if value <= 0:
            raise ExplorationError(INVALID_ARGUMENTS,
                                   f'max_nodes 必须为正：{value}')
        return min(value, ux.MAX_TREE_NODES)

    @staticmethod
    def _action_arguments(arguments: Dict[str, Any]
                          ) -> tuple[ux.UiActionType, Dict[str, Any]]:
        raw = arguments.get('action_type') or arguments.get('action')
        try:
            action_type = ux.UiActionType(str(raw or '').strip().upper())
        except ValueError:
            raise ExplorationError(
                INVALID_ARGUMENTS,
                f'action_type 必须是 {" / ".join(a.value for a in ux.UiActionType)} '
                f'之一（收到 {raw!r}）')
        params = arguments.get('params') if isinstance(
            arguments.get('params'), dict) else {}
        params = {key: value for key, value in params.items() if value is not None}
        if action_type is ux.UiActionType.INPUT_TEXT and not str(
                params.get('text') or '').strip():
            raise ExplorationError(INVALID_ARGUMENTS,
                                   'INPUT_TEXT 需要 params.text（要输入的文本）')
        if action_type is ux.UiActionType.SWIPE:
            for name in ('to_x', 'to_y'):
                if params.get(name) is None:
                    raise ExplorationError(INVALID_ARGUMENTS,
                                           f'SWIPE 需要 params.{name}')
        duration = params.get('duration_ms')
        if duration is not None and (isinstance(duration, bool)
                                     or not isinstance(duration, int)
                                     or duration < 0):
            raise ExplorationError(INVALID_ARGUMENTS,
                                   f'params.duration_ms 必须是非负整数：{duration}')
        return action_type, params

    def _session(self, context: ToolInvocationContext,
                 device_id: int) -> _Session:
        key = self._key(context.run_id, device_id)
        with self._sessions_lock:
            session = self._sessions.get(key)
        if session is not None:
            return session

        entry = self._acquire_creation_lock(key)
        try:
            with entry.lock:
                with self._sessions_lock:
                    session = self._sessions.get(key)
                if session is not None:
                    return session
                session = self._create_session(context, device_id)
                with self._sessions_lock:
                    self._sessions[key] = session
                return session
        finally:
            self._release_creation_lock(key, entry)

    def _acquire_creation_lock(self, key: tuple) -> _CreationLock:
        with self._sessions_lock:
            entry = self._creating.get(key)
            if entry is None:
                entry = _CreationLock()
                self._creating[key] = entry
            entry.users += 1
            return entry

    def _release_creation_lock(self, key: tuple, entry: _CreationLock) -> None:
        with self._sessions_lock:
            entry.users -= 1
            if entry.users <= 0 and self._creating.get(key) is entry:
                self._creating.pop(key, None)

    def _create_session(self, context: ToolInvocationContext,
                        device_id: int) -> _Session:
        lease = self._leases.acquire(device_id, holder=context.run_id)
        if lease is None:
            raise ExplorationError(
                DEVICE_NOT_LEASED,
                f'设备 {device_id} 未租用或正被其他任务 / 用例占用：'
                '探索前必须先租用并锁定设备。')
        try:
            platform = str(self._devices.platform(device_id) or 'ANDROID')
        except UiDeviceError as exc:
            self._leases.release(lease)
            raise ExplorationError(DEVICE_UNAVAILABLE, str(exc)) from exc
        lease_mode, lease_degraded = self._lease_metadata(lease)
        if lease_degraded:
            logger.warning(
                '设备 %s 的租约在 Redis 不可用时降级放行（未真正锁定）：'
                '可能与其他任务 / 用例冲突', device_id)
        return _Session(run_id=context.run_id,
                        session_id=context.session_id,
                        device_id=device_id, platform=platform,
                        lease=lease, lease_mode=lease_mode,
                        lease_degraded=lease_degraded)

    @staticmethod
    def _lease_metadata(lease: Any) -> tuple[str, bool]:
        """读取租约句柄上的获取方式 / 降级标记（适配器提供；缺失按未降级）。"""
        if isinstance(lease, dict):
            mode = lease.get('lease_mode')
            degraded = lease.get('degraded')
        else:
            mode = getattr(lease, 'lease_mode', None)
            degraded = getattr(lease, 'degraded', None)
        value = str(mode or 'UNKNOWN').upper()
        return value, bool(degraded) or value == 'DEGRADED'

    @contextmanager
    def _locked_session(self, context: ToolInvocationContext,
                        device_id: int) -> Iterator[_Session]:
        """取会话并独占它：同一 (run, device) 的探索调用由此串行化。"""
        session = self._session(context, device_id)
        key = self._key(context.run_id, device_id)
        with session.lock:
            if not self._is_registered(key, session):
                # 等待期间会话已被别的线程停止 / run 已收口：明确失败，不
                # 在一个已经释放租约的会话上继续下发动作（若会话带着停止
                # 原因，回灌同一个错误码，模型看到的仍是真实原因）。
                if session.stop_reason is not None:
                    self._refuse_if_stopped(session)
                raise ExplorationError(EXPLORATION_STOPPED,
                                       _SESSION_CLOSED_MESSAGE,
                                       payload={'stop_reason': 'USER_CANCEL'})
            yield session

    def _is_registered(self, key: tuple, session: _Session) -> bool:
        with self._sessions_lock:
            return self._sessions.get(key) is session

    def _drop_session(self, session: _Session) -> None:
        key = self._key(session.run_id, session.device_id)
        with self._sessions_lock:
            if self._sessions.get(key) is session:
                self._sessions.pop(key, None)

    @staticmethod
    def _refuse_if_stopped(session: _Session) -> None:
        if session.stop_reason is not None:
            raise ExplorationError(
                _STOP_ERROR_CODES.get(session.stop_reason,
                                      EXPLORATION_STOPPED),
                _STOP_MESSAGES.get(session.stop_reason,
                                   '探索已停止，请重新开始新的探索计划。'),
                payload={'stop_reason': session.stop_reason.value})

    def _dump(self, session: _Session, max_nodes: int
              ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            result = self._devices.dump_nodes(session.device_id,
                                              max_nodes=max_nodes)
        except UiDeviceError as exc:
            raise ExplorationError(DEVICE_UNAVAILABLE, str(exc)) from exc
        nodes = [node for node in (result.get('nodes') or ())
                 if isinstance(node, dict)]
        if not nodes:
            raise ExplorationError(DEVICE_UNAVAILABLE,
                                   '设备返回空 UI 树：无法确认页面元素，'
                                   '不返回伪造节点。')
        coverage = result.get('coverage') or ux.coverage_notes(
            nodes, session.platform)
        return nodes, coverage

    def _perform(self, session: _Session, action_type: ux.UiActionType,
                 node: Optional[Dict[str, Any]],
                 params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._devices.perform(
                session.device_id, action_type.value,
                node=node, params=params) or {}
        except UiDeviceError as exc:
            raise ExplorationError(DEVICE_UNAVAILABLE, str(exc)) from exc

    def _screenshot(self, session: _Session) -> Optional[str]:
        try:
            ref = self._devices.screenshot(session.device_id,
                                           label=f'a{session.actions}')
        except UiDeviceError as exc:  # 截图失败不阻断动作，但留日志
            logger.warning('探索截图失败 device=%s: %s', session.device_id, exc)
            return None
        return str(ref) if ref else None

    def _rotate_snapshot(self, session: _Session,
                         nodes: Sequence[Dict[str, Any]],
                         coverage: Dict[str, Any]) -> None:
        """把新读到的树设为「上一次快照」（下一轮 diff 的基准）。"""
        session.nodes = list(nodes)
        session.coverage = coverage or {}
        session.snapshot_id = uuid.uuid4().hex

    @staticmethod
    def _resolve_target(session: _Session,
                        target: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(target, dict):
            return None
        wanted_id = target.get('id')
        wanted_rid = target.get('resource_id')
        wanted_text = target.get('text')
        for node in session.nodes:
            if wanted_id is not None and str(node.get('id')) == str(wanted_id):
                return node
            if wanted_rid and node.get('resource_id') == wanted_rid:
                return node
            if wanted_text and node.get('text') == wanted_text:
                return node
        return None

    # ------------------------------------------------------------ 停止 / 产物

    def _stop(self, session: _Session, reason: ux.ExplorationStopReason,
              *, extra: Optional[Dict[str, Any]] = None) -> None:
        """安全 / 预算停止：落轨迹、释放租约，抛带 stop_reason 的失败负载。"""
        trace_ref = self._finalize(session, reason)
        self._drop_session(session)
        payload = {
            'device_id': session.device_id,
            'platform': session.platform,
            'action_index': session.actions,
            'trace_ref': trace_ref,
            'stop_reason': reason.value,
            'trace_validation': self._trace_summary(session),
            'message': _STOP_MESSAGES.get(reason, reason.value),
            'lease_mode': session.lease_mode,
            'lease_degraded': session.lease_degraded,
            'budget': self._budget.as_dict(
                session.actions, session.elapsed_seconds()),
            'ok': False,
        }
        if extra:
            payload.update(extra)
        raise ExplorationError(_STOP_ERROR_CODES.get(reason, EXPLORATION_STOPPED),
                               _STOP_MESSAGES.get(reason, reason.value),
                               payload=payload)

    @staticmethod
    def _trace_summary(session: _Session) -> Optional[Dict[str, Any]]:
        """轨迹校验摘要（模型 / 测试从中看到 ok、体积与裁剪情况）。"""
        report = session.trace_report
        if not report:
            return None
        return {
            'ok': report.get('ok'),
            'bytes': report.get('bytes'),
            'actions': report.get('actions'),
            'pages': report.get('pages'),
            'trimmed': report.get('trimmed'),
        }

    def _write_trace(self, session: _Session,
                     reason: Optional[ux.ExplorationStopReason] = None
                     ) -> Optional[str]:
        """把当前轨迹写成 ``ui_trace.json`` 并登记 ``agent_artifact``（幂等）。

        每一步都会覆盖写同一个 URI，因此**登记必须跟着最终内容走**：首版
        ``add``、之后 ``update`` 同一行的 size / 元数据；否则
        ``agent_artifact`` 记录的会是首版字节数与 sha256，而 URI 上已是
        最终（更大）的内容（INT-2492 打回 P2-1）。超过 4MB 的轨迹先裁剪
        （截节点文本 / 丢最旧页），裁剪后仍超限则以 ``ok=False`` 登记，
        不静默注册成合格产物。
        """
        if self._store is None or self._artifacts is None:
            return None
        if not session.action_log:
            # 只预演 / 只读树（没有任何真实动作）时不产出轨迹：0 动作的
            # ui_trace 过不了结构校验，登记上去只会污染 run 的产物列表。
            return None
        stop = reason or session.stop_reason or ux.ExplorationStopReason.DONE
        trace = ux.build_ui_trace(
            device_id=session.device_id, platform=session.platform,
            run_id=session.run_id, session_id=session.session_id,
            actions=session.action_log, pages=session.pages,
            screenshots=session.screenshots,
            started_ms=0, finished_ms=session.elapsed_ms(),
            stop_reason=stop, coverage=session.coverage,
            run_status=session.run_status, run_error=session.run_error,
            lease_mode=session.lease_mode,
            lease_degraded=session.lease_degraded)
        trace, trimmed = ux.fit_trace_to_bytes(trace)
        text = json.dumps(trace, ensure_ascii=False, sort_keys=True)
        raw = text.encode('utf-8')
        size = len(raw)
        report = ux.validation_report(trace, trace_bytes=size)
        if trimmed:
            report['trimmed'] = trimmed
        session.trace_report = report
        if not report['ok']:
            logger.error('ui_trace 产物校验未通过 run=%s device=%s: %s',
                         session.run_id, session.device_id,
                         [check.get('detail') for check in report['checks']
                          if not check.get('ok')])
        object_name = (f'{ux.UI_TRACE_FILENAME.split(".")[0]}_'
                       f'{session.device_id}.json')
        try:
            uri = self._store.put(
                text, run_id=session.run_id, name=object_name,
                content_type='application/json')
        except Exception as exc:  # noqa: BLE001 - 产物落盘失败不伪造引用
            logger.warning('ui_trace 落对象存储失败 run=%s device=%s: %s',
                           session.run_id, session.device_id, exc)
            return None
        session.artifact_uri = uri
        metadata = {
            'artifact_kind': ux.ARTIFACT_KIND_UI_TRACE,
            # 同一 run 多设备各写各的对象；包内固定名见 package_filename
            'filename': object_name,
            'package_filename': ux.UI_TRACE_FILENAME,
            'device_id': session.device_id,
            'platform': session.platform,
            'lease_mode': session.lease_mode,
            'lease_degraded': session.lease_degraded,
            'stop_reason': stop.value,
            'run_status': session.run_status,
            'run_error': session.run_error,
            'valid': bool(report['ok']),
            'source_trace': {
                'uri': uri,
                # 落盘内容的真实 hash（校验 artifact 与 URI 内容一致）
                'sha256': hashlib.sha256(raw).hexdigest(),
                # 驱动提案用的规范化 hash（与 driver_propose 的 ui_trace 口径相同）
                'canonical_sha256': report['sha256'],
                'actions': report['actions'],
                'pages': report['pages'],
                'screenshots': report['screenshots'],
            },
            'validation_report': report,
            'created_at': utcnow().isoformat(),
        }
        if session.artifact_id is None:
            # 幂等登记：同一 run + 同一 URI 已有行时复用（覆盖写同一个对象，
            # 不该出现第二行）。会话锁已经保证同进程内只有一个写者，这里再
            # 兜一层「add 已提交但返回前抛异常」与跨进程重启的重复。
            session.artifact_id = self._find_artifact_id(
                session.run_id, uri)
        if session.artifact_id is None:
            artifact = AgentArtifact(
                id=str(uuid.uuid4()), run_id=session.run_id,
                kind=ux.ARTIFACT_KIND_UI_TRACE, uri=uri, size=size,
                metadata=metadata)
            try:
                stored = self._artifacts.add(artifact)
                session.artifact_id = stored.id
            except Exception as exc:  # noqa: BLE001 - 登记失败显式留痕
                logger.warning('ui_trace 登记 agent_artifact 失败 run=%s: %s',
                               session.run_id, exc)
        else:
            try:
                self._artifacts.update(session.artifact_id, size=size,
                                       metadata=metadata, uri=uri)
            except Exception as exc:  # noqa: BLE001 - 更新失败显式留痕
                logger.warning('ui_trace 更新 agent_artifact 失败 run=%s: %s',
                               session.run_id, exc)
        return uri

    def _find_artifact_id(self, run_id: str, uri: str) -> Optional[str]:
        """按 run + URI 找已登记的 ``UI_TRACE`` 产物（查不到 / 查询失败返回 None）。"""
        if self._artifacts is None:
            return None
        try:
            artifacts = self._artifacts.list_by_run(run_id)
        except Exception as exc:  # noqa: BLE001 - 查询失败退回正常登记
            logger.warning('查询 agent_artifact 失败 run=%s: %s', run_id, exc)
            return None
        for artifact in artifacts or ():
            if (getattr(artifact, 'kind', None) == ux.ARTIFACT_KIND_UI_TRACE
                    and getattr(artifact, 'uri', None) == uri):
                return getattr(artifact, 'id', None)
        return None

    def _finalize(self, session: _Session,
                  reason: ux.ExplorationStopReason) -> Optional[str]:
        session.stop_reason = reason
        trace_ref = self._write_trace(session, reason)
        lease, session.lease = session.lease, None
        if lease is not None:
            try:
                self._leases.release(lease)
            except Exception:  # noqa: BLE001 - 释放失败由租约 TTL 兜底
                logger.warning('释放设备租约失败 device=%s', session.device_id,
                               exc_info=True)
        return trace_ref


__all__ = [
    'BUDGET_EXCEEDED', 'CAPTCHA', 'DESTRUCTIVE_BLOCKED', 'DEVICE_NOT_LEASED',
    'DEVICE_UNAVAILABLE', 'EXPLORATION_STOPPED', 'EXPLORATION_UNAVAILABLE',
    'ExplorationError', 'ExplorationService', 'INVALID_ARGUMENTS',
    'LOGIN_REQUIRED',
]
