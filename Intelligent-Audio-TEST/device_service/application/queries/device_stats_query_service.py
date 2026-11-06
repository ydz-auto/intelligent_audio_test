# -*- coding: utf-8 -*-
"""设备监控统计查询应用服务（INT-1578）。

CQRS 查询侧：只读 ``device_status_events``（+ 设备范围来自 ``devices``），零副作用。
口径见《设备监控统计与播放设备控制接口契约》§1。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional

from device_service.domain.repositories import DeviceMonitorRepositoryInterface

logger = logging.getLogger(__name__)

# 契约 §1.1：区间跨度 ≤ 90 天（含首尾），超出 400
MONITOR_STATS_MAX_RANGE_DAYS = 90
# 本期仅日粒度（其它值 400）
MONITOR_STATS_GRANULARITY_DAY = 'day'
_DATE_FORMAT = '%Y-%m-%d'


class DeviceStatsQueryService:
    """设备监控统计查询服务（历史监控 → 统计分析四图）"""

    def __init__(self, monitor_repo: DeviceMonitorRepositoryInterface = None):
        if monitor_repo is None:
            from device_service.infrastructure.persistence.device_monitor_repository import (
                device_monitor_repository,
            )
            monitor_repo = device_monitor_repository
        self.monitor_repo = monitor_repo

    def get_monitor_stats(self, params: dict) -> dict:
        """按日聚合监控统计。

        Args:
            params: {device_ids?: [int], lab_id?: int, start_date: 'YYYY-MM-DD',
                     end_date: 'YYYY-MM-DD', granularity?: 'day'}

        Returns:
            {success, message, data, code} 信封；data 为
            {granularity, start_date, end_date, device_count, points[]}
        """
        try:
            query = self._parse_params(params or {})
        except ValueError as exc:
            return {'success': False, 'message': str(exc), 'data': None, 'code': 400}

        try:
            result = self.monitor_repo.aggregate_daily_stats(
                device_ids=query['device_ids'],
                lab_id=query['lab_id'],
                start_date=query['start_date'],
                end_date=query['end_date'],
            )
        except Exception as exc:
            logger.exception("设备监控统计聚合失败")
            return {'success': False, 'message': str(exc), 'data': None, 'code': 400}

        data = {
            'granularity': MONITOR_STATS_GRANULARITY_DAY,
            'start_date': query['start_date'].isoformat(),
            'end_date': query['end_date'].isoformat(),
            'device_count': int(result.get('device_count') or 0),
            'points': result.get('points') or [],
        }
        return {'success': True, 'message': 'ok', 'data': data, 'code': 200}

    # ---------- 参数校验（网关已校验一次，服务侧防御性复校） ----------

    @staticmethod
    def _parse_params(params: dict) -> dict:
        start_date = _parse_date(params.get('start_date'), 'start_date')
        end_date = _parse_date(params.get('end_date'), 'end_date')

        if end_date < start_date:
            raise ValueError('结束日期不能早于开始日期')
        if (end_date - start_date).days + 1 > MONITOR_STATS_MAX_RANGE_DAYS:
            raise ValueError(f'统计区间不得超过 {MONITOR_STATS_MAX_RANGE_DAYS} 天')

        granularity = str(params.get('granularity') or MONITOR_STATS_GRANULARITY_DAY).strip().lower()
        if granularity != MONITOR_STATS_GRANULARITY_DAY:
            raise ValueError(f'统计粒度仅支持 {MONITOR_STATS_GRANULARITY_DAY}')

        return {
            'start_date': start_date,
            'end_date': end_date,
            'granularity': granularity,
            'device_ids': _parse_device_ids(params.get('device_ids')),
            'lab_id': _parse_optional_int(params.get('lab_id'), 'lab_id'),
        }


def _parse_date(value, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if not text:
        raise ValueError(f'{field} 不能为空')
    try:
        return datetime.strptime(text, _DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f'{field} 格式应为 YYYY-MM-DD') from None


def _parse_device_ids(value) -> Optional[List[int]]:
    """兼容 list / '1,2,3' / '1' 三种形态；空值表示不限。"""
    if value is None:
        return None
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(',') if part.strip()]
    elif isinstance(value, (list, tuple, set)):
        parts = list(value)
    else:
        parts = [value]
    if not parts:
        return None
    device_ids = []
    for part in parts:
        try:
            device_ids.append(int(part))
        except (TypeError, ValueError):
            raise ValueError('device_ids 应为逗号分隔的整数') from None
    return device_ids or None


def _parse_optional_int(value, field: str) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} 应为整数') from None


device_stats_query_service = DeviceStatsQueryService()
