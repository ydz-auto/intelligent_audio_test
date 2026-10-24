# -*- coding: utf-8 -*-
"""设备监控/告警仓储实现（INT-80）。

状态历史（device_status_events）+ 告警规则（device_alarm_rules）+
告警记录（device_alarms）的持久化。
"""
from __future__ import annotations

import json
from bisect import bisect_right
from datetime import date, datetime, time as dt_time, timedelta
from typing import Dict, List, Optional

from sqlalchemy import (
    Date, DateTime, Float, Integer, String, cast, func, literal, or_, select,
)
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.common_enums import (
    AlarmStatus,
    DeviceStatusEventSource,
    DeviceStatusEventType,
)
from shared.models.database import get_db_session
from shared.utils.query_utils import now_cst
from device_service.infrastructure.persistence.models import (
    Device,
    DeviceAlarm,
    DeviceAlarmRule,
    DeviceStatusEvent,
)
from device_service.domain.repositories import DeviceMonitorRepositoryInterface

# 状态重放只认 online/offline 事件（health_check / operation 的 to_status 不参与可用率）
_STATE_EVENT_TYPES = (
    DeviceStatusEventType.ONLINE.value,
    DeviceStatusEventType.OFFLINE.value,
)
# 计入 errors 的失败事件类型（契约 §1.2 括号口径：health_check 失败 + operation 失败）；
# online/offline 状态事件写入时 success=is_online，设备正常下线不是「错误」，其影响已由 availability 表达
_FAILURE_EVENT_TYPES = (
    DeviceStatusEventType.HEALTH_CHECK.value,
    DeviceStatusEventType.OPERATION.value,
)
# 非测试设备主体写入的事件来源（INT-1677）：device_status_events 被测试设备与
# 播放设备两个 id 空间共用，source 是主体判别位。凡新增非测试设备写入方，必须
# 登记进本集合，否则其事件会被统计到同号测试设备（契约 §0）。
_NON_TEST_DEVICE_EVENT_SOURCES = frozenset({
    DeviceStatusEventSource.PLAYBACK_OPERATION.value,
})


def _test_device_event_filter():
    """测试设备口径的事件过滤谓词（排除非测试设备主体写入的事件）。

    必须对 ``source IS NULL`` 宽容：SQL 的 ``NOT IN`` 遇 NULL 返回 NULL，会把历史
    NULL 行静默漏统计；仓储写入默认 'monitor' 不能当作历史数据兜底（契约 §1.1）。
    """
    return or_(
        DeviceStatusEvent.source.is_(None),
        DeviceStatusEvent.source.notin_(_NON_TEST_DEVICE_EVENT_SOURCES),
    )


def _event_to_dict(po: DeviceStatusEvent) -> dict:
    return {
        'id': po.id,
        'device_id': po.device_id,
        'event_type': po.event_type,
        'from_status': po.from_status,
        'to_status': po.to_status,
        'source': po.source,
        'success': po.success,
        'detail': po.detail,
        'created_at': po.created_at.isoformat() if po.created_at else None,
    }


def _rule_to_dict(po: DeviceAlarmRule) -> dict:
    return {
        'id': po.id,
        'name': po.name,
        'metric_type': po.metric_type,
        'threshold_value': po.threshold_value,
        'severity': po.severity,
        'notify_email': po.notify_email,
        'enabled': po.enabled,
        'created_by_user_id': po.created_by_user_id,
        'updated_by_user_id': po.updated_by_user_id,
        'created_at': po.created_at.isoformat() if po.created_at else None,
        'updated_at': po.updated_at.isoformat() if po.updated_at else None,
    }


def _alarm_to_dict(po: DeviceAlarm) -> dict:
    return {
        'id': po.id,
        'rule_id': po.rule_id,
        'rule_name': po.rule_name,
        'device_id': po.device_id,
        'device_name': po.device_name,
        'metric_type': po.metric_type,
        'severity': po.severity,
        'status': po.status,
        'trigger_value': po.trigger_value,
        'threshold_value': po.threshold_value,
        'content': po.content,
        'email_sent': po.email_sent,
        'email_error': po.email_error,
        'triggered_at': po.triggered_at.isoformat() if po.triggered_at else None,
        'acknowledged_at': po.acknowledged_at.isoformat() if po.acknowledged_at else None,
        'acknowledged_by': po.acknowledged_by,
        'resolved_at': po.resolved_at.isoformat() if po.resolved_at else None,
    }


# ==================== 监控统计聚合（INT-1578，纯函数便于单测） ====================

def _now_naive() -> datetime:
    """东八区当前时间（去时区，DB 列无时区）。"""
    return now_cst().replace(tzinfo=None)


def _iter_days(start_date: date, end_date: date):
    cursor = start_date
    while cursor <= end_date:
        yield cursor
        cursor += timedelta(days=1)


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_metric_value(value) -> Optional[float]:
    """指标值归一为 float；非数值（None/布尔/字符串/NaN）返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _mean_rounded(values: List[float]) -> Optional[float]:
    """算术平均，保留 1 位；无采点返回 None（不是 0）。"""
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _device_day_availability(state_events: List[dict], times: List[datetime],
                             day_start: datetime, day_end: datetime) -> Optional[float]:
    """单设备单日可用率（%），无可观测时长返回 None。

    契约 §1.2：日初状态取当日之前最近一条 online/offline 事件；日初无基线时
    该设备当日首条事件为观测起点（此前状态未知，不计入分母）。
    """
    if day_end <= day_start:
        return None

    prior_index = bisect_right(times, day_start) - 1
    in_day = state_events[prior_index + 1:bisect_right(times, day_end)]

    if prior_index >= 0:
        observed_start = day_start
        state = state_events[prior_index]['event_type']
    elif in_day:
        first = in_day[0]
        observed_start = max(first['created_at'], day_start)
        state = first['event_type']
        in_day = in_day[1:]
    else:
        return None

    online_seconds = 0.0
    cursor = observed_start
    for event in in_day:
        if state == DeviceStatusEventType.ONLINE.value:
            online_seconds += max((event['created_at'] - cursor).total_seconds(), 0.0)
        cursor = event['created_at']
        state = event['event_type']
    if state == DeviceStatusEventType.ONLINE.value:
        online_seconds += max((day_end - cursor).total_seconds(), 0.0)

    observed_seconds = (day_end - observed_start).total_seconds()
    if observed_seconds <= 0:
        return None
    return max(0.0, min(100.0, online_seconds / observed_seconds * 100.0))


_METRIC_KEYS = ('cpu', 'memory', 'battery')
# UNION ALL 行标记：daily=按日预聚合（SQL 侧 GROUP BY），state=参与可用率重放的状态事件
_ROW_DAILY = 'daily'
_ROW_STATE = 'state'


def _empty_daily_summary() -> dict:
    summary = {
        'health_check_samples': 0,
        'errors': 0,
        'operations': 0,
    }
    for key in _METRIC_KEYS:
        summary[f'{key}_sum'] = 0.0
        summary[f'{key}_count'] = 0
    return summary


def _summarize_events_by_day(events: List[dict], days: List[date]) -> Dict[date, dict]:
    """把事件明细按日汇总（无 SQL 预聚合时的参考实现 / 单测入口）。"""
    summaries = {day: _empty_daily_summary() for day in days}
    for event in events:
        event_day = event['created_at'].date() if event.get('created_at') else None
        bucket = summaries.get(event_day)
        if bucket is None:
            continue
        if (event.get('event_type') in _FAILURE_EVENT_TYPES
                and event.get('success') is False):
            bucket['errors'] += 1
        if str(event.get('to_status') or '').lower() == 'error':
            bucket['errors'] += 1
        if (event.get('event_type') == DeviceStatusEventType.OPERATION.value
                and bool(event.get('success'))):
            bucket['operations'] += 1
        if event.get('event_type') != DeviceStatusEventType.HEALTH_CHECK.value:
            continue
        bucket['health_check_samples'] += 1
        health_metrics = _as_dict(event.get('detail')).get('metrics')
        if not isinstance(health_metrics, dict):
            continue
        for key in _METRIC_KEYS:
            number = _as_metric_value(health_metrics.get(key))
            if number is not None:
                bucket[f'{key}_sum'] += number
                bucket[f'{key}_count'] += 1
    return summaries


def _summary_mean(summary: dict, key: str) -> Optional[float]:
    if f'{key}_avg' in summary:
        value = summary[f'{key}_avg']
        return None if value is None else round(float(value), 1)
    count = summary[f'{key}_count']
    return round(summary[f'{key}_sum'] / count, 1) if count else None


def _aggregate_daily_points(events: List[dict], days: List[date],
                            now: datetime,
                            daily_stats: Dict[date, dict] = None) -> List[dict]:
    """把区间事件按日聚合成统计点（区间内每一天都出点）。

    ``daily_stats`` 为 SQL 侧已按日预聚合的计数/指标和（``{date: summary}``）；
    传入时 ``events`` 只用于可用率重放（online/offline 事件），不再扫明细做计数，
    这样 90 天 × 10 设备的大区间不必把全部事件拉进内存。不传则按事件明细现算。
    """
    summaries = daily_stats if daily_stats is not None else _summarize_events_by_day(events, days)
    state_events_by_device: Dict[int, List[dict]] = {}

    for event in events:
        if event.get('event_type') in _STATE_EVENT_TYPES:
            state_events_by_device.setdefault(event['device_id'], []).append(event)

    device_times = {}
    for device_id, device_events in state_events_by_device.items():
        device_events.sort(key=lambda item: item['created_at'])
        device_times[device_id] = [item['created_at'] for item in device_events]

    points = []
    for day in days:
        day_start = datetime.combine(day, dt_time.min)
        day_end = min(day_start + timedelta(days=1), now)
        summary = summaries.get(day) or _empty_daily_summary()

        availability_values = []
        for device_id, device_events in state_events_by_device.items():
            value = _device_day_availability(
                device_events, device_times[device_id], day_start, day_end)
            if value is not None:
                availability_values.append(value)

        points.append({
            'date': day.isoformat(),
            'availability': _mean_rounded(availability_values),
            'cpu': _summary_mean(summary, 'cpu'),
            'memory': _summary_mean(summary, 'memory'),
            'battery': _summary_mean(summary, 'battery'),
            'errors': int(summary['errors']),
            'operations': int(summary['operations']),
            'health_check_samples': int(summary['health_check_samples']),
        })
    return points


# ==================== 按日预聚合 SQL（INT-1578：下推到数据库，避免全量事件入内存） ====================

def _dialect_name(session) -> str:
    bind = session.get_bind()
    return getattr(getattr(bind, 'dialect', None), 'name', '') or ''


def _day_bucket_expr(dialect_name: str):
    """``created_at`` → 日期分组维度（SQLite 返回 ``YYYY-MM-DD`` 文本，PostgreSQL 返回 date）。

    SQLite 的 DateTime 以 ``YYYY-MM-DD HH:MM:SS.ffffff`` 文本存储，``substr`` 取前 10 位
    比 ``strftime`` 快数倍（90 天 × 10 设备实测 0.8s → 0.4s）；PostgreSQL 直接 cast 成 date。
    """
    if dialect_name == 'sqlite':
        return func.substr(DeviceStatusEvent.created_at, 1, 10)
    return cast(DeviceStatusEvent.created_at, Date)


def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _event_flag_expressions():
    """逐行布尔标志（事件口径），在窄投影里算一次，外层聚合直接引用。

    ``event_type='health_check'`` 这类文本比较走排序规则（collation），一个聚合口径一条
    就要逐行比一次（本查询 6 条聚合里重复出现 7 次）；先算成布尔列，外层只剩布尔判断。
    实测 259k 行按日聚合中位 0.93s → 0.84s。
    """
    return {
        'is_health': (DeviceStatusEvent.event_type
                      == DeviceStatusEventType.HEALTH_CHECK.value).label('is_health'),
        'is_operation': (DeviceStatusEvent.event_type
                         == DeviceStatusEventType.OPERATION.value).label('is_operation'),
        'is_failed': DeviceStatusEvent.success.is_(False).label('is_failed'),
        'is_succeeded': DeviceStatusEvent.success.is_(True).label('is_succeeded'),
        'is_error_status': (func.lower(func.coalesce(DeviceStatusEvent.to_status, ''))
                            == 'error').label('is_error_status'),
    }


_FLAG_NAMES = ('is_health', 'is_operation', 'is_failed', 'is_succeeded', 'is_error_status')


def _daily_metric_sources(session, dialect_name: str, scope_ids: List[int],
                          range_start: datetime, range_end: datetime):
    """区间事件 → (day_bucket, 布尔标志, cpu, memory, battery) 窄投影。

    指标取值是这条 SQL 里最贵的一段（每行都要从 ``detail`` JSON 里取数），两库各用最省
    的写法，语义一致：取不到即 NULL（AVG 天然忽略，当日无采点 → NULL 而不是 0）。

    - SQLite：JSON1 ``json_extract`` 直接按路径取，无需嵌套。
    - PostgreSQL：``detail`` 是 json 列，``->`` 每次取值都要重新解析整行文本；实测
      259k 行 3 次解析 vs 1 次整行 json→jsonb 转换后 3 次 jsonb 取值，中位 2.12s → 1.24s。
      转型每行只做一次靠的是内层子查询的 ``OFFSET 0``：不加它优化器会把内层内联、把
      ``CAST(detail AS jsonb)`` 复制成三份。外层按日聚合走窄行（3 个 float8 + 标志位），
      优化器因此选 HashAggregate 而不是排序聚合（后者在 259k 行上会落盘）。
    """
    filters = (
        DeviceStatusEvent.device_id.in_(scope_ids),
        DeviceStatusEvent.created_at >= range_start,
        DeviceStatusEvent.created_at < range_end,
        _test_device_event_filter(),
    )
    day_bucket = _day_bucket_expr(dialect_name)
    flags = _event_flag_expressions()
    if dialect_name == 'sqlite':
        return session.query(
            day_bucket.label('day_bucket'),
            *[flags[name] for name in _FLAG_NAMES],
            func.json_extract(DeviceStatusEvent.detail, '$.metrics.cpu').label('cpu'),
            func.json_extract(DeviceStatusEvent.detail, '$.metrics.memory').label('memory'),
            func.json_extract(DeviceStatusEvent.detail, '$.metrics.battery').label('battery'),
        ).filter(*filters).subquery()

    narrowed = session.query(
        day_bucket.label('day_bucket'),
        *[flags[name] for name in _FLAG_NAMES],
        cast(DeviceStatusEvent.detail, JSONB).label('metrics_root'),
    ).filter(*filters).offset(0).subquery()
    return session.query(
        narrowed.c.day_bucket,
        *[narrowed.c[name] for name in _FLAG_NAMES],
        narrowed.c.metrics_root['metrics']['cpu'].astext.cast(Float).label('cpu'),
        narrowed.c.metrics_root['metrics']['memory'].astext.cast(Float).label('memory'),
        narrowed.c.metrics_root['metrics']['battery'].astext.cast(Float).label('battery'),
    ).subquery()


def _daily_stats_query(session, scope_ids: List[int],
                       range_start: datetime, range_end: datetime):
    """按日聚合 health_check 计数 / 指标均值 / 错误与操作计数（单条 SQL 的一支）。"""
    dialect = _dialect_name(session)
    source = _daily_metric_sources(session, dialect, scope_ids, range_start, range_end)
    health = source.c.is_health
    # 口径（契约 §1.2）：health_check/operation 的 success=false 事件数 + to_status=error 事件数
    # （两者并列相加，同一事件可重复计入）。online/offline 状态事件不计入 errors。
    errors = func.count().filter(
        (source.c.is_failed & (health | source.c.is_operation)) | source.c.is_error_status)

    def metric_avg(column):
        # AVG 天然忽略 NULL：当日无采点即 NULL（而不是 0）；同时省掉单独的 COUNT 表达式
        return func.avg(column).filter(health)

    return session.query(
        literal(_ROW_DAILY).label('row_kind'),
        source.c.day_bucket.label('day_bucket'),
        # 首支决定 UNION 结果列类型：NULL 必须显式 cast，否则状态事件行无类型处理器
        cast(literal(None), Integer).label('device_id'),
        cast(literal(None), String).label('event_type'),
        cast(literal(None), DateTime).label('created_at'),
        func.count().filter(health).label('health_check_samples'),
        errors.label('errors'),
        func.count().filter(source.c.is_operation & source.c.is_succeeded).label('operations'),
        metric_avg(source.c.cpu).label('cpu'),
        metric_avg(source.c.memory).label('memory'),
        metric_avg(source.c.battery).label('battery'),
    ).group_by(source.c.day_bucket)


def _state_rows_query(session, criteria):
    """状态事件支（区间内 online/offline + 各设备区间前基线），供可用率重放。

    排除谓词在函数内统一套用：区间状态支与基线支共用本函数，避免两处口径漂移。
    """
    return session.query(
        literal(_ROW_STATE).label('row_kind'),
        literal(None).label('day_bucket'),
        DeviceStatusEvent.device_id.label('device_id'),
        DeviceStatusEvent.event_type.label('event_type'),
        DeviceStatusEvent.created_at.label('created_at'),
        literal(0).label('health_check_samples'),
        literal(0).label('errors'),
        literal(0).label('operations'),
        cast(literal(None), Float).label('cpu'),
        cast(literal(None), Float).label('memory'),
        cast(literal(None), Float).label('battery'),
    ).filter(*criteria, _test_device_event_filter())


class DeviceMonitorRepository(DeviceMonitorRepositoryInterface):
    """设备监控/告警仓储"""
    # ========== 状态历史 ==========

    def record_status_event(self, data: dict) -> dict:
        session = get_db_session()
        po = DeviceStatusEvent(
            device_id=int(data['device_id']),
            event_type=data['event_type'],
            from_status=data.get('from_status'),
            to_status=data.get('to_status'),
            source=data.get('source') or 'monitor',
            success=data.get('success', True),
            detail=data.get('detail'),
        )
        session.add(po)
        session.commit()
        return _event_to_dict(po)

    def list_status_events(self, device_ids: List[int] = None, event_type: str = None,
                           start_time=None, end_time=None,
                           page: int = 1, per_page: int = 50) -> dict:
        """状态历史（两个端点共用）：只返回测试设备事件。

        播放设备控制事件（source=playback_operation）与测试设备共用 device_id 空间，
        必须排除；本期不提供播放侧历史查询参数（INT-1677）。
        """
        session = get_db_session()
        query = session.query(DeviceStatusEvent).filter(_test_device_event_filter())
        if device_ids:
            query = query.filter(DeviceStatusEvent.device_id.in_([int(d) for d in device_ids]))
        if event_type:
            query = query.filter(DeviceStatusEvent.event_type == event_type)
        if start_time:
            query = query.filter(DeviceStatusEvent.created_at >= start_time)
        if end_time:
            query = query.filter(DeviceStatusEvent.created_at <= end_time)
        pagination = query.order_by(DeviceStatusEvent.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
        return {
            'items': [_event_to_dict(e) for e in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def count_health_check_failures_batch(self, device_ids: List[int]) -> dict:
        """批量统计各设备最近一次成功健康检查之后的连续失败次数。

        单次查询取回全部设备的 health_check 事件（(device_id, created_at) 复合索引），
        内存内按设备回放计数，替代逐设备 N+1 查询。
        """
        if not device_ids:
            return {}
        session = get_db_session()
        rows = session.query(
            DeviceStatusEvent.device_id,
            DeviceStatusEvent.success,
        ).filter(
            DeviceStatusEvent.device_id.in_([int(d) for d in device_ids]),
            DeviceStatusEvent.event_type == DeviceStatusEventType.HEALTH_CHECK.value,
            # 防御性一致：播放侧当前不写 health_check，仍按同一谓词排除（INT-1677）
            _test_device_event_filter(),
        ).order_by(
            DeviceStatusEvent.device_id,
            DeviceStatusEvent.created_at,
            DeviceStatusEvent.id,  # created_at 并列时按自增 id 定序（追加写单调）
        ).all()
        counts = {int(d): 0 for d in device_ids}
        for device_id, success in rows:
            if success:
                counts[device_id] = 0  # 成功健康检查重置连续失败计数
            else:
                counts[device_id] = counts.get(device_id, 0) + 1
        return counts

    def get_last_online_events(self, device_ids: List[int]) -> dict:
        """批量查询各设备最后一次 online/offline 状态事件（供离线时长阈值计算）。

        事件表为追加写，max(id) 即最新事件（自增无并列，避免 created_at 同刻含糊）。
        """
        if not device_ids:
            return {}
        session = get_db_session()
        latest = session.query(
            DeviceStatusEvent.device_id,
            func.max(DeviceStatusEvent.id).label('max_id'),
        ).filter(
            DeviceStatusEvent.device_id.in_([int(d) for d in device_ids]),
            DeviceStatusEvent.event_type.in_(
                [DeviceStatusEventType.ONLINE.value, DeviceStatusEventType.OFFLINE.value]),
            # 防御性一致：播放侧当前不写 online/offline，仍按同一谓词排除（INT-1677）
            _test_device_event_filter(),
        ).group_by(DeviceStatusEvent.device_id).subquery()
        rows = session.query(DeviceStatusEvent).join(
            latest,
            DeviceStatusEvent.id == latest.c.max_id,
        ).all()
        return {po.device_id: _event_to_dict(po) for po in rows}

    def get_latest_health_details(self, device_ids: List[int]) -> dict:
        """批量查询各设备最近一次健康检查的 detail（含 cpu/memory/battery 上报数据时可得）。"""
        if not device_ids:
            return {}
        session = get_db_session()
        latest = session.query(
            DeviceStatusEvent.device_id,
            func.max(DeviceStatusEvent.id).label('max_id'),
        ).filter(
            DeviceStatusEvent.device_id.in_([int(d) for d in device_ids]),
            DeviceStatusEvent.event_type == DeviceStatusEventType.HEALTH_CHECK.value,
        ).group_by(DeviceStatusEvent.device_id).subquery()
        rows = session.query(DeviceStatusEvent).join(
            latest,
            DeviceStatusEvent.id == latest.c.max_id,
        ).all()
        return {
            po.device_id: dict(po.detail or {})
            for po in rows if po.detail
        }

    # ========== 监控统计（INT-1578） ==========

    def get_monitor_device_ids(self, device_ids: List[int] = None,
                               lab_id: int = None) -> List[int]:
        """统计范围内的测试设备 id（`devices` 表；播放/API 设备不在本表，天然不入统计）。"""
        session = get_db_session()
        query = session.query(Device.id).filter(Device.deleted.is_(False))
        if device_ids:
            query = query.filter(Device.id.in_([int(d) for d in device_ids]))
        if lab_id is not None:
            query = query.filter(Device.lab_id == int(lab_id))
        return [int(row[0]) for row in query.all()]

    def _load_stats_sources(self, device_ids: List[int],
                            range_start: datetime, range_end: datetime):
        """一次 SQL 取「按日预聚合 + 状态事件」，返回 (daily_stats, state_events)。

        三支以 UNION ALL 合并成一条语句（CQRS 查询侧只读，无副作用）：
        ① 区间内事件按日 GROUP BY（health_check 计数 / 指标和 / 错误与操作计数）；
        ② 区间内 online/offline 事件（可用率重放）；
        ③ 各设备区间前最近一条 online/offline 基线事件。
        明细不再入内存，10 设备 × 90 天区间只返回 ~90 行日汇总 + 少量状态事件。
        """
        session = get_db_session()
        baseline_ids = (
            select(func.max(DeviceStatusEvent.id))
            .where(
                DeviceStatusEvent.device_id.in_(device_ids),
                DeviceStatusEvent.event_type.in_(_STATE_EVENT_TYPES),
                DeviceStatusEvent.created_at < range_start,
                _test_device_event_filter(),
            )
            .group_by(DeviceStatusEvent.device_id)
        )
        daily_query = _daily_stats_query(session, device_ids, range_start, range_end)
        range_state_query = _state_rows_query(session, [
            DeviceStatusEvent.device_id.in_(device_ids),
            DeviceStatusEvent.event_type.in_(_STATE_EVENT_TYPES),
            DeviceStatusEvent.created_at >= range_start,
            DeviceStatusEvent.created_at < range_end,
        ])
        baseline_query = _state_rows_query(session, [
            DeviceStatusEvent.id.in_(baseline_ids),
            DeviceStatusEvent.event_type.in_(_STATE_EVENT_TYPES),
        ])

        daily_stats: Dict[date, dict] = {}
        state_events: List[dict] = []
        for row in daily_query.union_all(range_state_query, baseline_query).all():
            if row[0] == _ROW_DAILY:
                daily_stats[_as_date(row[1])] = {
                    'health_check_samples': int(row[5] or 0),
                    'errors': int(row[6] or 0),
                    'operations': int(row[7] or 0),
                    'cpu_avg': row[8],
                    'memory_avg': row[9],
                    'battery_avg': row[10],
                }
            else:
                state_events.append({
                    'device_id': row[2],
                    'event_type': row[3],
                    'created_at': row[4],
                })
        return daily_stats, state_events

    def aggregate_daily_stats(self, device_ids: List[int] = None, lab_id: int = None,
                              start_date: date = None, end_date: date = None,
                              now: datetime = None) -> dict:
        """按日聚合监控统计（一次 SQL 取日汇总 + 状态事件，内存只做可用率重放）。"""
        days = list(_iter_days(start_date, end_date))
        aggregate_now = now or _now_naive()
        scope_ids = self.get_monitor_device_ids(device_ids=device_ids, lab_id=lab_id)
        if not scope_ids:
            return {
                'device_count': 0,
                'points': _aggregate_daily_points([], days, aggregate_now),
            }

        range_start = datetime.combine(start_date, dt_time.min)
        range_end = datetime.combine(end_date, dt_time.min) + timedelta(days=1)
        daily_stats, state_events = self._load_stats_sources(
            scope_ids, range_start, range_end)
        return {
            'device_count': len(scope_ids),
            'points': _aggregate_daily_points(
                state_events, days, aggregate_now, daily_stats=daily_stats),
        }

    def update_alarm_email(self, alarm_id: int, sent: bool, error: str = '') -> None:
        """回写告警邮件发送结果"""
        session = get_db_session()
        po = session.query(DeviceAlarm).filter_by(id=alarm_id).first()
        if not po:
            return
        po.email_sent = sent
        po.email_error = error or None
        session.commit()

    # ========== 告警规则 ==========

    def create_alarm_rule(self, data: dict) -> dict:
        session = get_db_session()
        po = DeviceAlarmRule(
            name=data['name'],
            metric_type=data['metric_type'],
            threshold_value=float(data['threshold_value']),
            severity=data.get('severity') or 'warning',
            notify_email=data.get('notify_email', True),
            enabled=data.get('enabled', True),
            created_by_user_id=data.get('created_by_user_id'),
        )
        session.add(po)
        session.commit()
        return _rule_to_dict(po)

    def update_alarm_rule(self, rule_id: int, update_fields: dict) -> Optional[dict]:
        session = get_db_session()
        po = session.query(DeviceAlarmRule).filter_by(id=rule_id, deleted=False).first()
        if not po:
            return None
        for key, value in update_fields.items():
            if hasattr(po, key):
                setattr(po, key, value)
        po.updated_at = datetime.now()
        session.commit()
        return _rule_to_dict(po)

    def delete_alarm_rule(self, rule_id: int) -> bool:
        session = get_db_session()
        po = session.query(DeviceAlarmRule).filter_by(id=rule_id, deleted=False).first()
        if not po:
            return False
        po.deleted = True
        session.commit()
        return True

    def get_alarm_rule(self, rule_id: int) -> Optional[dict]:
        session = get_db_session()
        po = session.query(DeviceAlarmRule).filter_by(id=rule_id, deleted=False).first()
        return _rule_to_dict(po) if po else None

    def list_alarm_rules(self, page: int = 1, per_page: int = 50,
                         metric_type: str = None, enabled: bool = None) -> dict:
        session = get_db_session()
        query = session.query(DeviceAlarmRule).filter_by(deleted=False)
        if metric_type:
            query = query.filter(DeviceAlarmRule.metric_type == metric_type)
        if enabled is not None:
            query = query.filter(DeviceAlarmRule.enabled == enabled)
        pagination = query.order_by(DeviceAlarmRule.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
        return {
            'items': [_rule_to_dict(r) for r in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def list_enabled_alarm_rules(self) -> List[dict]:
        session = get_db_session()
        return [
            _rule_to_dict(r) for r in
            session.query(DeviceAlarmRule).filter_by(deleted=False, enabled=True).all()
        ]

    # ========== 告警记录 ==========

    def create_alarm(self, data: dict) -> dict:
        session = get_db_session()
        po = DeviceAlarm(
            rule_id=data.get('rule_id'),
            rule_name=data.get('rule_name'),
            device_id=int(data['device_id']),
            device_name=data.get('device_name'),
            metric_type=data['metric_type'],
            severity=data.get('severity') or 'warning',
            status=AlarmStatus.ACTIVE.value,
            trigger_value=data.get('trigger_value'),
            threshold_value=data.get('threshold_value'),
            content=data.get('content'),
            email_sent=False,
        )
        session.add(po)
        session.commit()
        return _alarm_to_dict(po)

    def list_alarms(self, status: str = None, severity: str = None, device_id: int = None,
                    page: int = 1, per_page: int = 50) -> dict:
        session = get_db_session()
        query = session.query(DeviceAlarm)
        if status:
            query = query.filter(DeviceAlarm.status == status)
        if severity:
            query = query.filter(DeviceAlarm.severity == severity)
        if device_id is not None:
            query = query.filter(DeviceAlarm.device_id == device_id)
        pagination = query.order_by(DeviceAlarm.triggered_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
        return {
            'items': [_alarm_to_dict(a) for a in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def acknowledge_alarm(self, alarm_id: int, acknowledged_by: str) -> Optional[dict]:
        """确认告警：active → acknowledged（已恢复/已确认的不可重复确认）"""
        session = get_db_session()
        po = session.query(DeviceAlarm).filter_by(id=alarm_id).first()
        if not po or po.status != AlarmStatus.ACTIVE.value:
            return None
        po.status = AlarmStatus.ACKNOWLEDGED.value
        po.acknowledged_at = datetime.now()
        po.acknowledged_by = acknowledged_by or ''
        session.commit()
        return _alarm_to_dict(po)

    def get_alarm_stats(self) -> dict:
        session = get_db_session()
        return {
            'active': session.query(DeviceAlarm).filter_by(status=AlarmStatus.ACTIVE.value).count(),
            'acknowledged': session.query(DeviceAlarm).filter_by(status=AlarmStatus.ACKNOWLEDGED.value).count(),
            'resolved': session.query(DeviceAlarm).filter_by(status=AlarmStatus.RESOLVED.value).count(),
            'total': session.query(DeviceAlarm).count(),
        }

    def has_unresolved_alarm(self, rule_id: int, device_id: int) -> bool:
        """同一规则+设备存在未恢复告警时去重，避免监控轮询重复告警"""
        session = get_db_session()
        return session.query(DeviceAlarm).filter(
            DeviceAlarm.rule_id == rule_id,
            DeviceAlarm.device_id == device_id,
            DeviceAlarm.status.in_([AlarmStatus.ACTIVE.value, AlarmStatus.ACKNOWLEDGED.value]),
        ).first() is not None


device_monitor_repository = DeviceMonitorRepository()
