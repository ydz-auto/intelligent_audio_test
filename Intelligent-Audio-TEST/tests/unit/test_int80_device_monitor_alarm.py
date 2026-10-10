# -*- coding: utf-8 -*-
"""INT-80 专项：设备监控告警（规则评估 → 告警落库 → 邮件通知 → 确认流）。

覆盖（验收 2：告警规则触发→落库→邮件发送可验证）：
- offline_duration：离线超阈值触发（基线取状态事件，回退 last_online_at）
- health_check_failures：连续失败次数超阈值触发
- battery：低于阈值触发（方向性）、cpu：超过阈值触发；无上报数据不评估
- 告警去重：同规则+设备未恢复告警存在时不再重复触发
- 邮件：notify_email=True 时经 SMTP 发送（smtplib.SMTP_SSL monkeypatch mock），
  结果回写 email_sent / email_error；SMTP 未配置降级为 email_error 落库
- 确认流：active → acknowledged，重复确认 404
- 状态事件：record_status_event 落库并发布 DEVICE_STATUS_CHANGED + device_status
"""
import os
import json
from types import SimpleNamespace

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('SMTP_HOST', 'smtp.mock.local')  # 启用邮件渠道（连接被 mock 拦截）
os.environ.setdefault('ALERT_EMAIL_RECIPIENTS', 'oncall@example.com')

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from device_service.application.services.device_monitor_service import (
    DeviceMonitorService,
    DeviceMonitorThread,
)
from shared.models.common_enums import AlarmMetricType, AlarmSeverity


# ---------- 测试替身 ----------

class FakeMonitorRepo:
    def __init__(self):
        self.events = []
        self.rules = []
        self.alarms = []
        self._seq = 0

    # --- 状态事件 ---
    def record_status_event(self, data):
        self._seq += 1
        event = {'id': self._seq, 'created_at': datetime.now().isoformat(), **data}
        self.events.append(event)
        return dict(event)

    def list_status_events(self, device_ids=None, event_type=None, start_time=None,
                           end_time=None, page=1, per_page=50):
        items = [e for e in self.events
                 if (not device_ids or e['device_id'] in device_ids)
                 and (not event_type or e['event_type'] == event_type)]
        return {'items': items, 'total': len(items), 'page': page,
                'per_page': per_page, 'pages': 1}

    def count_health_check_failures(self, device_id):
        count = 0
        for event in reversed(self.events):
            if event['device_id'] != device_id:
                continue
            if event.get('event_type') != 'health_check':
                continue
            if event.get('success'):
                break
            count += 1
        return count

    def get_last_online_event(self, device_id):
        candidates = [e for e in self.events
                      if e['device_id'] == device_id and e.get('event_type') in ('online', 'offline')]
        return candidates[-1] if candidates else None

    def get_latest_health_detail(self, device_id):
        candidates = [e for e in self.events
                      if e['device_id'] == device_id and e.get('event_type') == 'health_check'
                      and e.get('detail', {}).get('metrics')]
        return candidates[-1]['detail'] if candidates else None

    # --- 告警规则 ---
    def list_enabled_alarm_rules(self):
        return [dict(r) for r in self.rules if r.get('enabled')]

    def create_alarm_rule(self, data):
        self._seq += 1
        rule = {'id': self._seq, **data}
        self.rules.append(rule)
        return dict(rule)

    def get_alarm_rule(self, rule_id):
        return next((dict(r) for r in self.rules if r['id'] == rule_id), None)

    # --- 告警记录 ---
    def create_alarm(self, data):
        self._seq += 1
        alarm = {'id': self._seq, 'status': 'active',
                 'triggered_at': datetime.now().isoformat(),
                 'acknowledged_at': None, 'acknowledged_by': None,
                 'email_sent': False, 'email_error': None, **data}
        self.alarms.append(alarm)
        return dict(alarm)

    def list_alarms(self, status=None, severity=None, device_id=None, page=1, per_page=50):
        items = [a for a in self.alarms
                 if (not status or a['status'] == status)
                 and (not device_id or a['device_id'] == device_id)]
        return {'items': items, 'total': len(items), 'page': page,
                'per_page': per_page, 'pages': 1, 'stats': self.get_alarm_stats()}

    def acknowledge_alarm(self, alarm_id, acknowledged_by):
        for alarm in self.alarms:
            if alarm['id'] == alarm_id and alarm['status'] == 'active':
                alarm['status'] = 'acknowledged'
                alarm['acknowledged_at'] = datetime.now().isoformat()
                alarm['acknowledged_by'] = acknowledged_by
                return dict(alarm)
        return None

    def get_alarm_stats(self):
        return {
            'active': sum(1 for a in self.alarms if a['status'] == 'active'),
            'acknowledged': sum(1 for a in self.alarms if a['status'] == 'acknowledged'),
            'resolved': 0,
            'total': len(self.alarms),
        }

    def has_unresolved_alarm(self, rule_id, device_id):
        return any(a['rule_id'] == rule_id and a['device_id'] == device_id
                   and a['status'] in ('active', 'acknowledged')
                   for a in self.alarms)

    def update_alarm_email(self, alarm_id, sent, error=''):
        for alarm in self.alarms:
            if alarm['id'] == alarm_id:
                alarm['email_sent'] = sent
                alarm['email_error'] = error or None


class FakeDeviceRepo:
    def __init__(self, devices):
        self._devices = devices

    def list_devices(self, page=1, per_page=10, **kwargs):
        return {'items': list(self._devices), 'total': len(self._devices),
                'page': page, 'per_page': per_page, 'pages': 1}


def _device(device_id=1, name='测试机', status='offline', last_online_at=None):
    return {'id': device_id, 'name': name, 'status': status,
            'last_online_at': last_online_at.isoformat() if isinstance(last_online_at, datetime) else last_online_at}


@pytest.fixture
def monitor_repo():
    return FakeMonitorRepo()


@pytest.fixture
def monitor(monitor_repo):
    return DeviceMonitorService(monitor_repo=monitor_repo, device_repo=FakeDeviceRepo([]))


class TestOfflineDurationRule:
    def test_triggers_when_offline_exceeds_threshold(self, monitor, monitor_repo):
        offline_since = datetime.now() - timedelta(hours=2)
        # 离线事件落库时刻 = 设备离线起点（fake repo 支持显式 created_at 覆盖）
        monitor_repo.record_status_event({
            'device_id': 1, 'event_type': 'offline', 'to_status': 'offline',
            'source': 'health_check', 'success': False, 'detail': None,
            'created_at': offline_since.isoformat(),
        })
        monitor_repo.create_alarm_rule({
            'name': '离线2小时', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 3600, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([_device(1, status='offline',
                                                          last_online_at=offline_since)])
        assert len(triggered) == 1
        alarm = triggered[0]
        assert alarm['metric_type'] == 'offline_duration'
        assert alarm['status'] == 'active'
        assert alarm['device_id'] == 1
        assert '离线' in alarm['content']

    def test_not_triggered_within_threshold(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '离线8小时', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 8 * 3600, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([
            _device(1, status='offline', last_online_at=datetime.now() - timedelta(hours=2))])
        assert triggered == []

    def test_not_triggered_when_online(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '离线1分钟', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 60, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([_device(1, status='online')])
        assert triggered == []


class TestOtherMetrics:
    def test_health_check_failures_threshold(self, monitor, monitor_repo):
        for _ in range(3):
            monitor_repo.record_status_event({
                'device_id': 1, 'event_type': 'health_check',
                'source': 'health_check', 'success': False, 'detail': None,
            })
        monitor_repo.create_alarm_rule({
            'name': '连败3次', 'metric_type': AlarmMetricType.HEALTH_CHECK_FAILURES.value,
            'threshold_value': 3, 'severity': 'critical', 'notify_email': False,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([_device(1, status='offline')])
        assert len(triggered) == 1
        assert triggered[0]['severity'] == 'critical'

    def test_battery_triggers_below_threshold(self, monitor, monitor_repo):
        monitor_repo.record_status_event({
            'device_id': 1, 'event_type': 'health_check', 'source': 'health_check',
            'success': True, 'detail': {'metrics': {'battery': 12}},
        })
        monitor_repo.create_alarm_rule({
            'name': '低电量', 'metric_type': AlarmMetricType.BATTERY.value,
            'threshold_value': 20, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([_device(1, status='online')])
        assert len(triggered) == 1

    def test_cpu_triggers_above_threshold(self, monitor, monitor_repo):
        monitor_repo.record_status_event({
            'device_id': 1, 'event_type': 'health_check', 'source': 'health_check',
            'success': True, 'detail': {'metrics': {'cpu': 96}},
        })
        monitor_repo.create_alarm_rule({
            'name': 'CPU高', 'metric_type': AlarmMetricType.CPU.value,
            'threshold_value': 90, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([_device(1, status='online')])
        assert len(triggered) == 1

    def test_no_reported_metric_skipped(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': 'CPU高', 'metric_type': AlarmMetricType.CPU.value,
            'threshold_value': 90, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        # 无健康检查明细 → 不评估不误报
        assert monitor.evaluate_alarm_rules([_device(1, status='online')]) == []

    def test_unknown_metric_type_skipped(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '怪指标', 'metric_type': 'galaxy_temperature',
            'threshold_value': 1, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        assert monitor.evaluate_alarm_rules([_device(1, status='online')]) == []


class TestDedupAndEmail:
    @pytest.fixture(autouse=True)
    def _smtp_env(self, monkeypatch):
        """显式固化 SMTP 配置：BaseConfig 类属性在首次 import 时烘焙，
        混合收集下 import 顺序不定，这里直接 patch 保证确定性。"""
        from shared.infrastructure.config import BaseConfig
        monkeypatch.setattr(BaseConfig, 'SMTP_HOST', 'smtp.mock.local', raising=False)
        monkeypatch.setattr(BaseConfig, 'ALERT_EMAIL_RECIPIENTS', 'oncall@example.com', raising=False)
        monkeypatch.setattr(BaseConfig, 'SMTP_FROM', 'alert@example.com', raising=False)
        monkeypatch.setattr(BaseConfig, 'SMTP_USER', '', raising=False)

    def test_duplicate_suppressed_until_acknowledged(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '离线1分钟', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 60, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        device = _device(1, status='offline', last_online_at=datetime.now() - timedelta(hours=3))
        first = monitor.evaluate_alarm_rules([dict(device)])
        assert len(first) == 1
        # active 未恢复 → 第二轮不重复
        assert monitor.evaluate_alarm_rules([dict(device)]) == []
        # 确认后仍未恢复 → 依旧不重复（确认≠恢复）
        monitor.acknowledge_alarm(first[0]['id'], '值班员')
        assert monitor.evaluate_alarm_rules([dict(device)]) == []

    @patch('shared.utils.email_sender.smtplib.SMTP_SSL')
    def test_email_sent_on_trigger_and_recorded(self, smtp_cls, monitor, monitor_repo):
        smtp_instance = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp_instance
        monitor_repo.create_alarm_rule({
            'name': '离线告警', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 60, 'severity': 'critical', 'notify_email': True,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([
            _device(1, status='offline', last_online_at=datetime.now() - timedelta(hours=5))])
        assert len(triggered) == 1
        # mock SMTP 收到发送调用，收件人来自配置
        assert smtp_instance.sendmail.called
        args = smtp_instance.sendmail.call_args
        assert 'oncall@example.com' in args[0][1]
        # 结果回写告警行
        alarm = monitor_repo.alarms[0]
        assert alarm['email_sent'] is True
        assert alarm['email_error'] is None

    @patch('shared.utils.email_sender.smtplib.SMTP_SSL', side_effect=OSError('connection refused'))
    def test_email_failure_recorded_not_raised(self, smtp_cls, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '离线告警', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 60, 'severity': 'critical', 'notify_email': True,
            'enabled': True,
        })
        triggered = monitor.evaluate_alarm_rules([
            _device(1, status='offline', last_online_at=datetime.now() - timedelta(hours=5))])
        # 邮件失败不阻塞告警产生
        assert len(triggered) == 1
        alarm = monitor_repo.alarms[0]
        assert alarm['email_sent'] is False
        assert 'connection refused' in (alarm['email_error'] or '')

    def test_email_disabled_rule_skips_send(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '离线告警', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 60, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        with patch('shared.utils.email_sender.smtplib.SMTP_SSL') as smtp_cls:
            triggered = monitor.evaluate_alarm_rules([
                _device(1, status='offline', last_online_at=datetime.now() - timedelta(hours=5))])
            assert len(triggered) == 1
            assert not smtp_cls.called


class TestAcknowledgeFlow:
    def test_acknowledge_active_alarm(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '离线告警', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 60, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        alarm = monitor.evaluate_alarm_rules([
            _device(1, status='offline', last_online_at=datetime.now() - timedelta(hours=2))])[0]
        result = monitor.acknowledge_alarm(alarm['id'], '值班员A')
        assert result['success'] is True
        assert result['data']['status'] == 'acknowledged'
        assert result['data']['acknowledged_by'] == '值班员A'

    def test_double_acknowledge_404(self, monitor, monitor_repo):
        monitor_repo.create_alarm_rule({
            'name': '离线告警', 'metric_type': AlarmMetricType.OFFLINE_DURATION.value,
            'threshold_value': 60, 'severity': 'warning', 'notify_email': False,
            'enabled': True,
        })
        alarm = monitor.evaluate_alarm_rules([
            _device(1, status='offline', last_online_at=datetime.now() - timedelta(hours=2))])[0]
        assert monitor.acknowledge_alarm(alarm['id'], 'a')['success'] is True
        assert monitor.acknowledge_alarm(alarm['id'], 'b')['code'] == 404


class TestStatusEventPublishing:
    def test_record_status_event_publishes_device_events(self, monitor, monitor_repo):
        published = {}
        with patch('shared.utils.redis_pubsub.EventBus') as bus_cls:
            bus = bus_cls.return_value
            event = monitor.record_status_event(
                device_id=1, event_type='online', from_status='offline',
                to_status='online', source='health_check', success=True)
            assert event is not None
            assert bus.publish.called
            channel_arg = bus.publish.call_args[0][0]
            event_type_arg = bus.publish.call_args[0][1]
            assert channel_arg.value == 'device_events'
            assert event_type_arg.value == 'device_status_changed'
            payload_arg = bus.publish.call_args[0][2]
            assert payload_arg['device_id'] == 1
            published['channel'] = channel_arg
        assert published['channel'].value == 'device_events'


class TestMonitorThread:
    def test_thread_idempotent_start(self):
        thread = DeviceMonitorThread(interval_seconds=3600)
        try:
            thread.start()
            first = thread._thread
            thread.start()
            assert thread._thread is first
        finally:
            thread.stop()
