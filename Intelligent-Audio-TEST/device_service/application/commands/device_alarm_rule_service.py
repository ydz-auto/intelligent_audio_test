# -*- coding: utf-8 -*-
"""设备告警规则 Command 应用服务（写侧，INT-80）。"""
from __future__ import annotations

import logging

from device_service.domain.repositories import DeviceMonitorRepositoryInterface
from shared.models.common_enums import AlarmMetricType
from shared.utils.log_handler import log_not_emit

logger = logging.getLogger(__name__)

# 规则可编辑字段（枚举化白名单，拒绝任意字段透传）
_RULE_EDITABLE_FIELDS = {'name', 'metric_type', 'threshold_value', 'severity', 'notify_email', 'enabled'}


class DeviceAlarmRuleService:
    """设备告警规则应用服务（规则 CRUD 写侧）"""

    def __init__(self, repo: DeviceMonitorRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_monitor_repository import device_monitor_repository
            repo = device_monitor_repository
        self.repo = repo

    @staticmethod
    def _validate_metric(metric_type) -> Optional[str]:
        allowed = {t.value for t in AlarmMetricType}
        return metric_type if metric_type in allowed else None

    def create(self, data: dict) -> dict:
        try:
            name = str(data.get('name') or '').strip()
            if not name:
                return {'success': False, 'message': '规则名称不能为空', 'data': None, 'code': 400}
            metric = self._validate_metric(data.get('metric_type'))
            if not metric:
                return {'success': False, 'message': f"不支持的告警指标: {data.get('metric_type')}",
                        'data': None, 'code': 400}
            try:
                threshold = float(data['threshold_value'])
            except (KeyError, TypeError, ValueError):
                return {'success': False, 'message': 'threshold_value 必须为数值',
                        'data': None, 'code': 400}
            rule = self.repo.create_alarm_rule({
                'name': name,
                'metric_type': metric,
                'threshold_value': threshold,
                'severity': data.get('severity') or 'warning',
                'notify_email': bool(data.get('notify_email', True)),
                'enabled': bool(data.get('enabled', True)),
                'created_by_user_id': data.get('created_by_user_id'),
            })
            log_not_emit('INFO', 'DeviceAlarmRule',
                         f"创建告警规则: {name} metric={metric} threshold={threshold}",
                         category='device', source='backend')
            return {'success': True, 'message': '告警规则创建成功', 'data': rule, 'code': 201}
        except Exception as e:
            logger.exception("创建告警规则失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def update(self, rule_id: int, data: dict) -> dict:
        try:
            existing = self.repo.get_alarm_rule(rule_id)
            if not existing:
                return {'success': False, 'message': '未找到告警规则', 'data': None, 'code': 404}
            update_fields = {k: v for k, v in data.items()
                             if k in _RULE_EDITABLE_FIELDS and v is not None}
            if data.get('metric_type') is not None:
                metric = self._validate_metric(data['metric_type'])
                if not metric:
                    return {'success': False, 'message': f"不支持的告警指标: {data['metric_type']}",
                            'data': None, 'code': 400}
                # 以校验后的枚举值落库（metric_type 属可编辑字段，不接受白名单外的透传值）
                update_fields['metric_type'] = metric
            if not update_fields:
                return {'success': False, 'message': '无可更新字段', 'data': None, 'code': 400}
            rule = self.repo.update_alarm_rule(rule_id, update_fields)
            log_not_emit('INFO', 'DeviceAlarmRule',
                         f"更新告警规则: id={rule_id} 字段={list(update_fields)}",
                         category='device', source='backend')
            return {'success': True, 'message': '告警规则更新成功', 'data': rule, 'code': 200}
        except Exception as e:
            logger.exception("更新告警规则失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete(self, rule_id: int) -> dict:
        try:
            deleted = self.repo.delete_alarm_rule(rule_id)
            if not deleted:
                return {'success': False, 'message': '未找到告警规则', 'data': None, 'code': 404}
            log_not_emit('INFO', 'DeviceAlarmRule', f"删除告警规则: id={rule_id}",
                         category='device', source='backend')
            return {'success': True, 'message': '告警规则已删除', 'data': None, 'code': 200}
        except Exception as e:
            logger.exception("删除告警规则失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def list(self, page: int = 1, per_page: int = 50, metric_type: str = None,
             enabled: bool = None) -> dict:
        try:
            data = self.repo.list_alarm_rules(
                page=int(page or 1), per_page=min(int(per_page or 50), 500),
                metric_type=metric_type or None, enabled=enabled)
            return {'success': True, 'message': '查询成功', 'data': data, 'code': 200}
        except Exception as e:
            logger.exception("查询告警规则列表失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


device_alarm_rule_service = DeviceAlarmRuleService()
