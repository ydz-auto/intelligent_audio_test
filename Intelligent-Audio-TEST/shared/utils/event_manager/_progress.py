# -*- coding: utf-8 -*-
"""任务进度 Socket 推送（task_progress 事件）

职责拆分：
- emit_progress：节流/缓存编排（唯一入口）
- _build_progress_from_grpc / _build_progress_from_po：两条数据源路径构造 TaskProgressPayload
- _finalize_and_emit：时间预估、变更检测、缓存与发射

payload 契约见 shared/schemas/socket_payloads.py（snake_case，
前端由 infrastructure/adapters/taskProgressAdapter.ts 统一转 camelCase）。
"""
import os
import re
import json
import time
import logging
from datetime import datetime
from typing import Optional, Tuple

from shared.models.database import get_db_session
from shared.models.common_enums import DeviceType
from shared.schemas.socket_payloads import (
    ProgressApiResource,
    ProgressCaseItem,
    ProgressCurrentCase,
    ProgressLogItem,
    RoundProgress,
    TaskProgressPayload,
)
from shared.utils.status_constants import (
    ACTIVE_EXECUTION_STATUSES,
    ExecutionStatus,
    EvaluationStatus,
    TaskCaseStatus,
    TaskStatus,
)
from shared.utils.status_utils import derive_task_dual_status, task_case_not_removed
from shared.utils.time_utils import UTC8

logger = logging.getLogger(__name__)

# 缓存策略：使用 shared.utils.task_data_cache 的 TTL 缓存减少 DB 往返。
# gRPC GetTaskProgress 现已返回完整进度数据（test_cases 列表/计数/api_resource_status），
# 优先走 gRPC 缓存；PO 直连仅用于 gRPC 不可用时的回退，以及内存态数据
#（execution_engine.round_progress_cache / load_balancer.url_status）。
from shared.utils.task_data_cache import get_task_progress_via_grpc

# 当前执行中用例的 step 默认值：按任务类型区分
STEP_PLAYING = 'playing'
STEP_EVALUATING = 'evaluating'

# 预计总时长防闪烁阈值：变化小于 10% 沿用缓存值
EXPECTED_TOTAL_SMOOTHING_RATIO = 0.1

# 时间预估兜底值（秒）
DEFAULT_EXPECTED_TOTAL_SECONDS = 60

# 进度事件「最近日志」条数上限（前端展示口径，两条取数路径共用）
RECENT_LOG_LIMIT = 20

# 业务日志尾部回读块大小（字节）：逐文件只回读末尾，凑够 20 条即止，
# 避免大任务（上万行文件）在每次进度推送时全量扫描日志文件
BUSINESS_LOG_TAIL_CHUNK_BYTES = 16 * 1024

# INT-133：不存在任务的进度推送抑制窗口（秒）。窗口内对同一 task_id 的
# 重复推送静默跳过（不查库、不打日志），过期后放行一轮重新核实；
# 仍在则再记一次 WARNING 并续期。经环境变量可覆盖。
MISSING_TASK_SUPPRESS_SECONDS = float(
    os.environ.get('PROGRESS_MISSING_TASK_SUPPRESS_SECONDS', '300'))

# 抑制登记内存上界（条目数）：事件 task_id 来自总线，属外部输入，
# 防遗留异常键堆积（同 INT-128 扫描缓存上界思路），超限淘汰最早登记。
MISSING_TASK_MAX_ENTRIES = 256


def _emit_task_progress_event(task_id, payload: dict, worker_instance_id=None):
    """经 EventBus TASK_EVENTS / task_progress 发布进度事件。

    各服务进程（含 task_service 自身）统一走总线，由 api_gateway 订阅后
    转发前端 Socket.IO；Redis 不可用时 EventBus.publish 内部降级不打断业务。
    """
    from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
    EventBus().publish(EventChannel.TASK_EVENTS, EventType.TASK_PROGRESS, {
        'event': 'task_progress',
        'task_id': str(task_id),
        'data': payload,
        'worker_instance_id': worker_instance_id,
    })


def _extract_task_id(task) -> str:
    """从各类任务表示（id/Task PO/dict/任意对象）中提取 task_id 字符串。"""
    if isinstance(task, (str, int)):
        return str(task)
    if isinstance(task, dict):
        return str(task.get('id') or '')
    if hasattr(task, '__class__') and task.__class__.__name__ == 'Task':
        try:
            return str(task.id)
        except Exception:
            pass
        try:
            from sqlalchemy.orm import object_state
            state = object_state(task)
            if state.persistent and state.identity:
                return str(state.identity[0])
        except Exception:
            pass
        match = re.search(r'\d+', str(task))
        if match:
            return match.group()
    try:
        return str(getattr(task, 'id', None) or '')
    except Exception:
        logger.debug("从任务对象获取 task_id 失败", exc_info=True)
        return ''


def _parse_dt(dt_value) -> Optional[datetime]:
    """ISO 字符串/datetime → datetime，空值返回 None。"""
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        try:
            return datetime.fromisoformat(dt_value)
        except ValueError:
            return None
    return dt_value


def _ts_ms(dt_value) -> int:
    """datetime/ISO字符串 → 毫秒时间戳（东八区），空值返回当前时间。"""
    dt = _parse_dt(dt_value)
    if dt is None:
        return int(time.time() * 1000)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC8)
    return int(dt.timestamp() * 1000)


def _to_utc8(dt_value):
    """naive datetime 补东八区时区。"""
    if dt_value is not None and dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=UTC8)
    return dt_value


def _compute_elapsed_seconds(started_at, completed_at, updated_at, status) -> float:
    """计算已用时长。

    已结束任务（completed_at 或终态时的 updated_at）使用结束时间作为参照，
    避免持续推送导致已用时长增长。
    """
    start = _to_utc8(started_at)
    if start is None:
        return 0.0
    end_reference = start
    if completed_at:
        end_reference = _to_utc8(completed_at)
    elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED) and updated_at:
        end_reference = _to_utc8(updated_at)
    return max(0.0, (end_reference - start).total_seconds())


def _collect_round_progress(round_progress_cache, task_case_id=None) -> Optional[RoundProgress]:
    """从内存态 round_progress_cache 提取多轮进度。

    gRPC 路径无法用 test_case_id 匹配 TaskCase.id，仅在缓存只有一个条目时
    补充到当前用例；PO 路径按 task_case_id 精确匹配。
    """
    if not round_progress_cache:
        return None
    if task_case_id is not None:
        rp = round_progress_cache.get(task_case_id)
        return RoundProgress(current=rp.get('current', 0), total=rp.get('total', 0)) if rp else None
    if len(round_progress_cache) == 1:
        rp = next(iter(round_progress_cache.values()))
        return RoundProgress(current=rp.get('current', 0), total=rp.get('total', 0))
    return None


def _current_concurrent_from_load_balancer(execution_engine) -> int:
    """从内存态 load_balancer 取所有 URL 的并发总和。"""
    if execution_engine is None:
        return 0
    load_balancer = getattr(execution_engine, 'load_balancer', None)
    if not load_balancer:
        return 0
    url_status = load_balancer.get_url_status()
    return sum(s.get('concurrent', 0) for s in url_status.values())


def _file_tail_records(file_path, want) -> list:
    """回读日志文件末尾的 JSON Lines 记录（文件内正序），最多 want 条。

    业务日志是追加写的 JSON Lines（写入侧整行落盘即刷盘），最新记录在文件
    尾部：从末尾按块回读、丢弃被截断的首行后逐行解析即可，块不足时按需
    翻倍直到凑够 want 条或读到文件头。

    返回 [(行起始字节偏移, 记录 dict)]。不整文件扫描：进度事件按推送频率
    触发，大任务（上万行）全量物化会拖慢执行线程。
    """
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return []
    chunk = BUSINESS_LOG_TAIL_CHUNK_BYTES
    while True:
        read_size = min(size, chunk)
        start = size - read_size
        try:
            with open(file_path, 'rb') as handle:
                handle.seek(start)
                data = handle.read(read_size)
        except OSError:
            return []
        line_start = start
        if line_start > 0:
            cut = data.find(b'\n')
            if cut < 0:
                data = b''
            else:
                # 首行可能从文件中间截断（非行首），丢弃到第一个换行符之后
                line_start += cut + 1
                data = data[cut + 1:]
        records = []
        offset = line_start
        for raw in data.split(b'\n'):
            current = offset
            offset += len(raw) + 1
            if not raw.strip():
                continue
            try:
                record = json.loads(raw.decode('utf-8', errors='replace'))
            except (ValueError, TypeError):
                continue
            if isinstance(record, dict):
                records.append((current, record))
        if len(records) >= want or start == 0:
            return records[-want:]
        chunk *= 4


def _stable_log_id(rel_path, offset) -> int:
    """文件条目稳定 int id（相对日志根路径 + 行起始偏移，替代 DB id）。

    与 BusinessLogReader 的条目 id 同为文件侧派生 id（无 DB 行）；同一记录
    在多次进度推送间稳定（前端列表 key 不抖动）。
    """
    import hashlib
    return int(hashlib.md5(f'{rel_path}:{offset}'.encode('utf-8')).hexdigest()[:12], 16)


def _build_logs_from_business_files(task_id_int) -> Optional[list]:
    """从业务日志文件读取最近日志（INT-1808 / INT-1793 D5）。

    INT-81 起业务日志写文件（logs/business/{task_id}/...），不再入 logs 表，
    因此新任务的最近日志必须读文件，否则进度事件「最近日志」恒空。

    返回 None 表示该任务在业务日志根下没有任何日志文件（目录不存在或无
    .log 文件，即 INT-81 之前的历史任务），由调用方回落 DB 读取；文件存在
    时以文件为准，读到空列表也不回落（避免把「本任务确实没有日志」误判为
    历史任务而重复读库）。

    取数：枚举任务下全部日志文件，逐文件只回读其最新 RECENT_LOG_LIMIT 条
    （任一文件最多贡献 20 条，故全局最新 20 条必在该并集中），按 time 倒序
    取前 20 再反转为正序——与 DB 路径输出顺序一致，level 统一小写。
    """
    from shared.logging import BusinessLogReader, get_log_settings

    reader = BusinessLogReader()
    files = reader.list_log_files(task_id=task_id_int)
    if not files:
        return None

    root_dir = get_log_settings().root_dir
    candidates = []  # (time, rel_path, offset, record)
    for file_path in files:
        rel_path = os.path.relpath(file_path, root_dir).replace(os.sep, '/')
        for offset, record in _file_tail_records(file_path, RECENT_LOG_LIMIT):
            candidates.append((record.get('time') or '', rel_path, offset, record))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [
        ProgressLogItem(
            id=_stable_log_id(rel_path, offset),
            level=(record.get('level') or 'info').lower(),
            message=record.get('content') or '',
            timestamp=_ts_ms(record.get('time')),
        )
        for _time, rel_path, offset, record in reversed(candidates[:RECENT_LOG_LIMIT])
    ]


def _build_logs_via_grpc(task_id_int) -> list:
    """通过 gRPC 查询最近日志并转为 ProgressLogItem 列表（历史任务回退路径）。"""
    try:
        from shared.clients.grpc_clients import list_logs
        log_resp = list_logs(task_id=task_id_int, page=1, per_page=RECENT_LOG_LIMIT)
        recent_log_items = log_resp.get('items', [])
    except Exception:
        recent_log_items = []
    return [
        ProgressLogItem(
            id=log_item.get('id', 0),
            level=(log_item.get('level') or 'info').lower(),
            message=log_item.get('content') or '',
            timestamp=_ts_ms(log_item.get('time')),
        )
        for log_item in reversed(recent_log_items)
    ]


def _build_recent_logs(task_id_int) -> list:
    """进度事件「最近日志」取数（INT-1808）：业务文件优先，历史任务回落 DB。

    DB 回退条件仅一种：任务在业务日志根下无任何日志文件（INT-81 之前的
    历史任务）。文件读取异常同样回落 DB 以保证进度事件不因日志读取失败
    而中断（新任务两侧都可能为空，降级后事件照常发射）。
    """
    try:
        file_logs = _build_logs_from_business_files(task_id_int)
    except Exception:
        logger.warning("业务日志文件读取失败，回落 DB 日志列表，task_id=%s",
                       task_id_int, exc_info=True)
        file_logs = None
    if file_logs is not None:
        return file_logs
    return _build_logs_via_grpc(task_id_int)


class _TaskProxy:
    """用于时间预估的 task 伪对象（只包含 calculate_time_estimate 需要的字段）。"""

    def __init__(self, task_id, task_status, total_cases, completed_cases,
                 failed_cases, started_at, completed_at, updated_at):
        self.id = task_id
        self.status = task_status
        self.total_cases = total_cases
        self.completed_cases = completed_cases
        self.failed_cases = failed_cases
        self.started_at = started_at
        self.completed_at = completed_at
        self.updated_at = updated_at


class ProgressMixin:
    # ────────────────────────── 入口与编排 ──────────────────────────

    def emit_progress(self, task, force=False, worker_instance_id=None):
        task_id = _extract_task_id(task)

        if not task_id:
            self._log(level='WARNING', content=f"无法获取任务ID，跳过进度更新", task_id=task_id)
            return

        current_time = time.time()

        # INT-133：不存在任务抑制窗口内的重复推送静默跳过（不查库不记日志），
        # 窗口过期放行一轮重新核实，仍不存在则由 _note_missing_task 续期
        missing_since = self._missing_tasks.get(task_id)
        if missing_since is not None:
            if current_time - missing_since < MISSING_TASK_SUPPRESS_SECONDS:
                return
            self._missing_tasks.pop(task_id, None)

        if not force and self._throttled(task_id, current_time):
            return

        self._last_progress_time[task_id] = current_time
        min_interval = min(self._min_update_interval, 0.1)

        local_db_session = None

        try:
            try:
                task_id_int = int(task_id) if isinstance(task_id, str) else task_id
            except (ValueError, TypeError):
                # INT-133：非整型任务键（如遗留/外部发布的 'task-1'）一次性
                # DEBUG 丢弃，不触发后续 gRPC/DB 查询，也不再向上抛断调用方
                self._log(level='DEBUG',
                          content=f"任务ID非整型，丢弃进度更新，task_id={task_id}",
                          task_id=task_id)
                return
            grpc_progress = get_task_progress_via_grpc(task_id_int)

            if grpc_progress is not None:
                self._missing_tasks.pop(task_id, None)
                self._log(level='DEBUG', content=f"使用 gRPC 进度数据，task_id={task_id}, force={force}", task_id=task_id)
                db_task, progress = self._build_progress_from_grpc(task_id, task_id_int, grpc_progress)
            else:
                # PO 回退路径：gRPC 不可用时直连 DB
                local_db_session = get_db_session()
                db_task, progress = self._build_progress_from_po(local_db_session, task_id, task_id_int)
                if db_task is None:
                    self._note_missing_task(task_id)
                    return
                self._missing_tasks.pop(task_id, None)
                self._log(level='DEBUG', content=f"使用 PO 回退路径生成进度数据，task_id={task_id}, force={force}", task_id=task_id)

            self._finalize_and_emit(
                task_id=task_id,
                db_task=db_task,
                progress=progress,
                min_interval=min_interval,
                force=force,
                current_time=current_time,
                worker_instance_id=worker_instance_id,
            )
        except Exception as e:
            self._log(level='ERROR', content=f"emit_progress 异常: {str(e)}", task_id=task_id, category='error')
            raise
        finally:
            if local_db_session is not None:
                local_db_session.close()

    def _note_missing_task(self, task_id):
        """登记不存在任务：首个周期 WARNING 留痕一次，之后在抑制窗口内静默。

        INT-133：事件源（订阅/循环）对已消失任务键的周期性推送只限流不收敛，
        此处以抑制窗口替代无限重试；任务重新出现时由 emit_progress 成功路径摘除登记。
        """
        if task_id in self._missing_tasks:
            return
        if len(self._missing_tasks) >= MISSING_TASK_MAX_ENTRIES:
            oldest = min(self._missing_tasks, key=self._missing_tasks.get)
            self._missing_tasks.pop(oldest, None)
        self._missing_tasks[task_id] = time.time()
        self._log(
            level='WARNING',
            content=(f"找不到任务，跳过进度更新，task_id={task_id}"
                     f"（{int(MISSING_TASK_SUPPRESS_SECONDS)}s 内抑制重复推送）"),
            task_id=task_id)

    def _throttled(self, task_id: str, current_time: float) -> bool:
        """初步节流：间隔不足直接跳过；缓存新鲜则直接重发缓存数据。"""
        last_time = self._last_progress_time.get(task_id, 0)
        if current_time - last_time < self._progress_throttle_interval:
            return True

        cached_progress = self._progress_cache.get(task_id)
        if cached_progress and current_time - cached_progress['timestamp'] < 0.1:
            try:
                _emit_task_progress_event(task_id, cached_progress['data'],
                                          worker_instance_id=cached_progress.get('worker_instance_id'))
                self._log(level='DEBUG', content=f"使用缓存发送进度更新，task_id={task_id}", task_id=task_id)
            except Exception as emit_error:
                self._log(level='WARNING', content=f"使用缓存发送进度更新失败: {str(emit_error)}", task_id=task_id)
            return True
        return False

    # ────────────────────────── gRPC 数据源路径 ──────────────────────────

    def _build_progress_from_grpc(self, task_id, task_id_int, grpc_progress) -> Tuple[_TaskProxy, TaskProgressPayload]:
        """gRPC 路径：使用远端进度数据构造 payload，无 PO 直连。"""
        # 差异#2 收尾：进度 payload 无 type 键，分支口径改用例级 device_types 集合（task.type 已废弃）
        device_types = grpc_progress.get('device_types') or []
        current_case = self._build_current_case_from_grpc(task_id, device_types, grpc_progress.get('current_case'))
        test_cases = self._build_test_cases_from_grpc(grpc_progress.get('test_cases', []))
        logs = _build_recent_logs(task_id_int)
        api_resources = self._build_api_resources_from_grpc(device_types, grpc_progress.get('api_resource_status', []))

        started_at = _parse_dt(grpc_progress.get('started_at'))
        completed_at = _parse_dt(grpc_progress.get('completed_at'))
        updated_at = _parse_dt(grpc_progress.get('updated_at'))
        task_status = grpc_progress.get('status', 'unknown')
        actual_total_cases = grpc_progress.get('actual_total_cases', grpc_progress.get('total_cases', 0))
        actual_completed_cases = grpc_progress.get('actual_completed_cases', grpc_progress.get('completed_cases', 0))

        self._log(level='DEBUG',
                  content=f"用例总数: {actual_total_cases}, 已完成: {actual_completed_cases}, 进行中: {grpc_progress.get('in_progress_count', 0)}",
                  task_id=task_id)

        progress = TaskProgressPayload(
            task_id=str(task_id_int),
            status=task_status,
            # INT-301：任务级执行/评估双状态（评估推进只落评估侧，前端实时更新双徽章）
            execution_status=grpc_progress.get('execution_status', '') or '',
            evaluation_status=grpc_progress.get('evaluation_status', '') or '',
            total_progress=self._calc_progress_percentage(actual_completed_cases, actual_total_cases),
            completed_count=actual_completed_cases,
            in_progress_count=grpc_progress.get('in_progress_count', 0),
            execution_failed_count=grpc_progress.get('execution_failed_count', 0),
            evaluation_failed_count=grpc_progress.get('evaluation_failed_count', 0),
            total_count=actual_total_cases,
            current_case=current_case,
            test_cases=test_cases,
            logs=logs,
            api_resources=api_resources,
            used_time=self._format_duration(
                _compute_elapsed_seconds(started_at, completed_at, updated_at, task_status)
            ) if started_at else "0分钟",
        )

        db_task = _TaskProxy(
            task_id=task_id_int,
            task_status=task_status,
            total_cases=actual_total_cases,
            completed_cases=actual_completed_cases,
            failed_cases=grpc_progress.get('failed_cases', 0),
            started_at=started_at,
            completed_at=completed_at,
            updated_at=updated_at,
        )
        return db_task, progress

    def _build_current_case_from_grpc(self, task_id, device_types, cc) -> Optional[ProgressCurrentCase]:
        """构造当前执行用例（内存态 step 缺省按被测设备类型推断）。"""
        if not cc:
            self._log(level='DEBUG', content=f"没有正在执行的用例", task_id=task_id)
            return None
        return ProgressCurrentCase(
            case_id=str(cc.get('case_id', cc.get('caseId', ''))),
            name=cc.get('name', '未知用例'),
            step=cc.get('step', STEP_PLAYING if set(device_types or []) == {DeviceType.PHYSICAL.value} else STEP_EVALUATING),
            start_time=_ts_ms(cc.get('started_at')),
        )

    def _build_test_cases_from_grpc(self, raw_test_cases) -> list:
        """构造用例进度列表，并补充内存态多轮进度。"""
        rpc_cache = getattr(self.execution_engine, 'round_progress_cache', {}) if self.execution_engine is not None else {}
        items = []
        for tc in raw_test_cases:
            items.append(ProgressCaseItem(
                id=str(tc.get('id', '')),
                status=tc.get('status', ''),
                execution_status=tc.get('execution_status', tc.get('executionStatus', '')),
                evaluation_status=tc.get('evaluation_status', tc.get('evaluationStatus', '')),
                duration=tc.get('duration', 0),
                error_message=tc.get('error_message') or tc.get('errorMessage') or '',
                round_progress=_collect_round_progress(rpc_cache) if items == [] else None,
            ))
        return items

    def _build_api_resources_from_grpc(self, device_types, raw_api_status) -> list:
        """构造 API 资源状态：gRPC 提供排队/耗时，并发量从内存态 load_balancer 补充。

        差异#2 收尾：分支依据由 task.type 改为 device_types 含 API 类被测设备
        （与 PO 回退路径 TaskCase.device_type 口径一致）。
        """
        api_types = (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value)
        if not any(dt in api_types for dt in (device_types or [])):
            return []
        current_concurrent = _current_concurrent_from_load_balancer(self.execution_engine)
        return [
            ProgressApiResource(
                id=api_info.get('id', ''),
                name=api_info.get('name', ''),
                current_concurrent=current_concurrent,
                queue_length=api_info.get('pending_cases', 0),
                avg_response_time=api_info.get('avg_response_time', 0),
                max_concurrent=api_info.get('default_max_process', 5),
            )
            for api_info in raw_api_status
        ]

    # ────────────────────────── PO 回退数据源路径 ──────────────────────────

    def _build_progress_from_po(self, session, task_id, task_id_int) -> Tuple[Optional[object], TaskProgressPayload]:
        """PO 回退路径：直连 DB 构造 payload（gRPC 不可用时）。"""
        from task_service.infrastructure.persistence.models import Task, TaskCase, TestCase

        db_task = session.get(Task, task_id_int)
        if not db_task:
            return None, TaskProgressPayload(task_id=str(task_id_int), status='unknown')

        current_case = self._build_current_case_from_po(session, task_id, db_task, TaskCase, TestCase)
        test_cases = self._build_test_cases_from_po(session, db_task, TaskCase)
        logs = _build_recent_logs(db_task.id)
        api_resources = self._build_api_resources_from_po(session, db_task)
        # INT-305：移除留痕行不计数（与列表/详情剔除口径一致）
        not_removed = task_case_not_removed(TaskCase)
        in_progress_count = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            not_removed,
            (TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)) | (TaskCase.evaluation_status == EvaluationStatus.RUNNING) |
            (TaskCase.evaluation_status == EvaluationStatus.CALCULATING)
        ).count()

        actual_total_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            not_removed,
        ).count()
        if actual_total_cases != db_task.total_cases:
            db_task.total_cases = actual_total_cases
            session.commit()
        actual_completed_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            not_removed,
            TaskCase.execution_status == ExecutionStatus.COMPLETED,
            TaskCase.status == TaskCaseStatus.COMPLETED
        ).count()

        execution_failed_count = sum(
            1 for tc in test_cases if tc.execution_status == ExecutionStatus.FAILED
        )
        evaluation_failed_count = sum(
            1 for tc in test_cases if tc.evaluation_status == EvaluationStatus.FAILED
        )

        # INT-301：PO 回退路径双状态（与 gRPC 路径同源——Task.status + 用例聚合）
        task_execution_status, task_evaluation_status = derive_task_dual_status(
            db_task.status,
            has_exec_active=any(tc.execution_status in ACTIVE_EXECUTION_STATUSES for tc in test_cases),
            has_exec_failed=execution_failed_count > 0,
            has_exec_stopped=any(tc.execution_status == ExecutionStatus.STOPPED for tc in test_cases),
            exec_all_terminal=bool(test_cases) and all(
                tc.execution_status in ('completed', 'failed', 'stopped') for tc in test_cases),
            has_eval_in_progress=any(tc.evaluation_status in ('queued', 'running', 'calculating')
                                     for tc in test_cases),
            has_eval_failed=evaluation_failed_count > 0,
            has_eval_completed=any(tc.evaluation_status == EvaluationStatus.COMPLETED for tc in test_cases),
        )

        progress = TaskProgressPayload(
            task_id=str(db_task.id),
            status=db_task.status,
            execution_status=task_execution_status,
            evaluation_status=task_evaluation_status,
            total_progress=self._calc_progress_percentage(actual_completed_cases, actual_total_cases),
            completed_count=actual_completed_cases,
            in_progress_count=in_progress_count,
            execution_failed_count=execution_failed_count,
            evaluation_failed_count=evaluation_failed_count,
            total_count=actual_total_cases,
            current_case=current_case,
            test_cases=test_cases,
            logs=logs,
            api_resources=api_resources,
            used_time=self._format_duration(
                _compute_elapsed_seconds(db_task.started_at, db_task.completed_at, db_task.updated_at, db_task.status)
            ) if db_task.started_at else "0分钟",
        )
        return db_task, progress

    def _build_current_case_from_po(self, session, task_id, db_task, TaskCase, TestCase) -> Optional[ProgressCurrentCase]:
        """构造当前执行用例（PO 直查 RUNNING 状态的 TaskCase）。"""
        current_tc = session.query(TaskCase).filter_by(
            task_id=db_task.id, execution_status=ExecutionStatus.RUNNING
        ).first()
        if not current_tc:
            self._log(level='DEBUG', content=f"没有正在执行的用例", task_id=task_id)
            return None
        case_info = session.get(TestCase, current_tc.test_case_id)
        # 差异#2 收尾：物理用例执行展示 playing，其余 evaluating（device_type 取代 task.type）
        step = (STEP_PLAYING
                if (current_tc.device_type or 'physical') == 'physical'
                else STEP_EVALUATING)
        current_case = ProgressCurrentCase(
            case_id=str(current_tc.test_case_id),
            name=case_info.name if case_info else "未知用例",
            step=step,
            start_time=_ts_ms(current_tc.started_at),
        )
        self._log(level='DEBUG',
                  content=f"当前执行用例: {current_case.name} (ID: {current_case.case_id})",
                  task_id=task_id)
        return current_case

    def _build_test_cases_from_po(self, session, db_task, TaskCase) -> list:
        """构造用例进度列表（含执行时长与内存态多轮进度）。"""
        rpc_cache = getattr(self.execution_engine, 'round_progress_cache', {}) if self.execution_engine is not None else {}
        # INT-305：移除留痕行（error_message = '用例已被移除'）剔除
        all_task_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            task_case_not_removed(TaskCase),
        ).all()
        items = []
        for tc in all_task_cases:
            items.append(ProgressCaseItem(
                id=str(tc.test_case_id),
                status=tc.status,
                execution_status=tc.execution_status,
                evaluation_status=tc.evaluation_status,
                duration=self._calc_case_duration(tc),
                error_message=tc.error_message or '',
                round_progress=_collect_round_progress(rpc_cache, task_case_id=tc.id),
            ))
        return items

    @staticmethod
    def _calc_case_duration(tc) -> int:
        """用例执行时长（秒）：completed_at - started_at。"""
        if not (tc.started_at and tc.completed_at):
            return 0
        started_at = _to_utc8(tc.started_at)
        completed_at = _to_utc8(tc.completed_at)
        return int((completed_at - started_at).total_seconds())

    def _build_api_resources_from_po(self, session, db_task) -> list:
        """构造 API 资源状态（PO 回退：按 load_balancer 每个 URL 一条）。

        差异#2 收尾：仅含 API 类被测设备用例的任务收集（device_type 取代 task.type）。
        """
        from shared.models.common_enums import DeviceType
        from task_service.infrastructure.persistence.models import TaskCase
        api_types = (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value)
        has_api_case = session.query(TaskCase.id).filter(
            TaskCase.task_id == db_task.id,
            TaskCase.device_type.in_(api_types),
        ).first() is not None
        if not has_api_case:
            return []

        from task_service.infrastructure.persistence.models import TaskAPI, TestResult
        from api_test_service.infrastructure.persistence.models import API

        task_api = session.query(TaskAPI).filter_by(task_id=db_task.id).first()
        if not task_api:
            return []
        api = session.get(API, task_api.api_id)
        if not api:
            return []

        api_executor = getattr(self.execution_engine, 'api_executors', {}).get(str(db_task.id)) if self.execution_engine is not None else None
        load_balancer = getattr(self.execution_engine, 'load_balancer', None) if self.execution_engine is not None else None
        if not (api_executor and load_balancer):
            return []

        pending_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            TaskCase.execution_status == ExecutionStatus.PENDING
        ).count()
        avg_response_time = self._calc_avg_response_time(session, db_task, TestResult)

        return [
            ProgressApiResource(
                id=str(api.id),
                name=api.name,
                current_concurrent=status.get('concurrent', 0),
                queue_length=pending_cases,
                avg_response_time=avg_response_time,
                max_concurrent=api.default_max_process if hasattr(api, 'default_max_process') else 5,
            )
            for url, status in load_balancer.get_url_status().items()
        ]

    @staticmethod
    def _calc_avg_response_time(session, db_task, TestResult) -> int:
        """已完成用例的平均响应时间（毫秒）。"""
        completed_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            TaskCase.execution_status == ExecutionStatus.COMPLETED
        ).count()
        if completed_cases <= 0:
            return 0
        completed_results = session.query(TestResult).filter(
            TestResult.task_id == db_task.id,
            TestResult.execution_status == ExecutionStatus.COMPLETED
        ).all()
        total_response_time = sum(result.response_time for result in completed_results if result.response_time)
        if total_response_time <= 0 or not completed_results:
            return 0
        return round(total_response_time / len(completed_results))

    # ────────────────────────── 收尾：预估/变更检测/发射 ──────────────────────────

    def _finalize_and_emit(self, task_id, db_task, progress, min_interval, force, current_time, worker_instance_id=None):
        """时间预估、防闪烁平滑、变更检测、缓存与最终发射。"""
        elapsed_seconds, expected_total_seconds, expected_complete_time_str = \
            self._compute_time_estimate(task_id, db_task)

        progress.expected_complete_time = expected_complete_time_str
        progress.expected_total_time = self._format_duration(expected_total_seconds)
        progress.used_time = self._format_duration(elapsed_seconds)

        if self._should_skip_update(task_id, db_task, progress, min_interval, force, current_time):
            return

        self._cache_progress(task_id, db_task, progress, current_time, worker_instance_id=worker_instance_id)
        self._emit(task_id, progress, worker_instance_id=worker_instance_id)

    def _compute_time_estimate(self, task_id, db_task):
        """计算已用时长与预计总时长（带防闪烁平滑）。"""
        elapsed_seconds = _compute_elapsed_seconds(
            db_task.started_at, db_task.completed_at, db_task.updated_at, db_task.status
        )
        expected_total_seconds = DEFAULT_EXPECTED_TOTAL_SECONDS
        expected_complete_time_str = ''

        if db_task.started_at:
            self._log(level='DEBUG', content=f"任务 {task_id}: 开始计算时间预估，已用时间={elapsed_seconds:.2f}秒", task_id=task_id)
            estimate_result = self.calculate_time_estimate(db_task)
            expected_total_seconds = estimate_result.get('expected_total_time', DEFAULT_EXPECTED_TOTAL_SECONDS)
            expected_complete_time_str = estimate_result.get('expected_complete_time', '')
            self._log(level='DEBUG', content=f"任务 {task_id}: calculate_time_estimate返回，预计总时长={expected_total_seconds}秒", task_id=task_id)

        expected_total_seconds = self._smooth_expected_total(task_id, expected_total_seconds)
        return elapsed_seconds, expected_total_seconds, expected_complete_time_str

    def _smooth_expected_total(self, task_id, expected_total_seconds) -> int:
        """预计总时长防闪烁：变化小于阈值时沿用缓存值。"""
        last_expected_total = self._last_progress.get(task_id, {}).get('expected_total')
        if last_expected_total is not None:
            expected_diff_ratio = abs(expected_total_seconds - last_expected_total) / (last_expected_total or 1)
            if expected_diff_ratio < EXPECTED_TOTAL_SMOOTHING_RATIO:
                self._log(level='DEBUG', content=f"任务 {task_id}: 使用缓存的预计总时长={last_expected_total}秒", task_id=task_id)
                return last_expected_total
        if task_id not in self._last_progress:
            self._last_progress[task_id] = {}
        self._last_progress[task_id]['expected_total'] = expected_total_seconds
        return expected_total_seconds

    def _should_skip_update(self, task_id, db_task, progress, min_interval, force, current_time) -> bool:
        """变更检测：状态/完成数/当前用例/最小间隔均无变化时跳过发射。

        INT-301：评估状态（evaluation_status）变化独立触发发射——重新评估
        提交/进行中 Task.status 会经 reevaluate_queued/reevaluating/running
        流转本可触发，但评估收敛（用例级 evaluation_status → 终态而任务仍
        running）仅体现在评估侧，必须单独检测防止双徽章评估侧滞后。
        """
        last_progress_info = self._last_progress.get(task_id, {})
        last_time = last_progress_info.get('time', 0)
        last_completed = last_progress_info.get('completed', -1)
        last_status = last_progress_info.get('status', '')
        last_current_case = last_progress_info.get('current_case')
        last_evaluation_status = last_progress_info.get('evaluation_status', '')

        reasons = []
        if force:
            reasons.append("强制更新进度")
        elif min_interval <= 0:
            reasons.append("最小更新间隔为0")
        elif db_task.status == TaskStatus.RUNNING and last_status != TaskStatus.RUNNING:
            reasons.append("任务开始执行")
        elif db_task.status == TaskStatus.COMPLETED and last_status != TaskStatus.COMPLETED:
            reasons.append("任务完成")
        elif db_task.status == TaskStatus.FAILED and last_status != TaskStatus.FAILED:
            reasons.append("任务失败")
        elif progress.evaluation_status and progress.evaluation_status != last_evaluation_status:
            reasons.append(f"评估状态变化, last={last_evaluation_status}, current={progress.evaluation_status}")
        elif current_time - last_time >= min_interval:
            reasons.append(f"达到最小更新间隔, elapsed={current_time - last_time:.3f}s")
        elif db_task.completed_cases != last_completed:
            reasons.append(f"完成用例数变化, last={last_completed}, current={db_task.completed_cases}")
        elif progress.current_case != last_current_case:
            reasons.append("当前执行用例变化")

        if not reasons:
            self._log(level='DEBUG',
                      content=f"跳过进度更新（节流），task_id={task_id}, last_time={last_time}, last_completed={last_completed}, last_status={last_status}",
                      task_id=task_id)
            return True

        self._log(level='DEBUG', content=f"{reasons[0]}，更新进度，task_id={task_id}", task_id=task_id)
        return False

    def _cache_progress(self, task_id, db_task, progress, current_time, worker_instance_id=None):
        """记录上次发射状态与 payload 缓存。"""
        self._last_progress[task_id] = {
            'time': current_time,
            'completed': db_task.completed_cases,
            'status': db_task.status,
            'current_case': progress.current_case,
            'evaluation_status': progress.evaluation_status,
        }
        self._progress_cache[task_id] = {
            'data': progress.model_dump(),
            'timestamp': current_time,
            'worker_instance_id': worker_instance_id,
        }

    def _emit(self, task_id, progress, worker_instance_id=None):
        """发射 task_progress 事件（snake_case payload，经 EventBus TASK_EVENTS 发布）。"""
        payload = progress.model_dump()
        try:
            _emit_task_progress_event(task_id, payload, worker_instance_id=worker_instance_id)
            self._log(level='DEBUG',
                      content=f"成功发送 task_progress 事件，task_id={task_id}, progress={progress.total_progress}%",
                      task_id=task_id)
        except Exception as emit_error:
            self._log(level='ERROR', content=f"发送 task_progress 事件失败: {str(emit_error)}", task_id=task_id)
            raise

    @staticmethod
    def _calc_progress_percentage(completed, total) -> float:
        """完成度百分比（上限 100）。"""
        percentage = round(completed / total * 100, 2) if total > 0 else 0
        return min(percentage, 100.0)
