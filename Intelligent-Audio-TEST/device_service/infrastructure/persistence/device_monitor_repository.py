# -*- coding: utf-8 -*-
"""设备监控/告警仓储实现（INT-80）。

状态历史（device_status_events）+ 告警规则（device_alarm_rules）+
告警记录（device_alarms）的持久化。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import func

from shared.models.common_enums import AlarmStatus, DeviceStatusEventType
from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import (
    DeviceAlarm,
    DeviceAlarmRule,
    DeviceStatusEvent,
)
from device_service.domain.repositories import DeviceMonitorRepositoryInterface


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
        session = get_db_session()
        query = session.query(DeviceStatusEvent)
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
