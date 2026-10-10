# -*- coding: utf-8 -*-
"""设备监控告警应用服务（INT-80 监控告警体系）。

职责：
- 状态事件落库（device_status_events）+ DEVICE_EVENTS 真实发布方
  （EventBus DEVICE_STATUS_CHANGED，INT-69 起不再双发裸字符串频道）
- 告警规则评估（离线时长/健康检查失败次数/CPU/内存/电池）→ 告警落库 →
  邮件通知（SMTP 配置化，未配置降级为仅落库）
- 告警确认流（active → acknowledged）
- 后台监控线程（周期健康检查 + 规则评估，server 启动时拉起）

指标方向约定（enum 化语义，见 AlarmMetricType）：
- offline_duration / health_check_failures / cpu / memory：值 >= 阈值触发
- battery：值 <= 阈值触发（低电量告警）
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Optional

from device_service.domain.repositories import (
    DeviceMonitorRepositoryInterface,
    DeviceRepositoryInterface,
)
from shared.config.query_constants import QueryConstants
from shared.models.common_enums import (
    AlarmMetricType,
    AlarmSeverity,
    AuditEvent,
    AuditLogCategory,
)
from shared.utils.log_handler import log_not_emit

logger = logging.getLogger(__name__)

# 监控线程默认轮询间隔（秒）；device_service 单实例内一个监控循环即可
_MONITOR_INTERVAL_SECONDS = 300


class DeviceMonitorService:
    """设备监控告警应用服务"""

    def __init__(self, monitor_repo: DeviceMonitorRepositoryInterface = None,
                 device_repo: DeviceRepositoryInterface = None):
        if monitor_repo is None:
            from device_service.infrastructure.persistence.device_monitor_repository import device_monitor_repository
            monitor_repo = device_monitor_repository
        if device_repo is None:
            from device_service.infrastructure.persistence.device_repository import device_repository
            device_repo = device_repository
        self.monitor_repo = monitor_repo
        self.device_repo = device_repo

    # ========== 状态事件（DEVICE_EVENTS 生产方） ==========

    def record_status_event(self, device_id: int, event_type: str,
                            from_status: str = None, to_status: str = None,
                            source: str = 'monitor', success: bool = True,
                            detail: dict = None) -> Optional[dict]:
        """状态事件落库并发布 DEVICE_EVENTS（降级：发布失败只打日志）。"""
        try:
            event = self.monitor_repo.record_status_event({
                'device_id': device_id,
                'event_type': event_type,
                'from_status': from_status,
                'to_status': to_status,
                'source': source,
                'success': success,
                'detail': detail,
            })
        except Exception:
            logger.warning("设备状态事件落库失败 device_id=%s", device_id, exc_info=True)
            return None

        self._publish_device_events(device_id, event_type, to_status, source, success, detail)
        return event

    @staticmethod
    def _publish_device_events(device_id, event_type, to_status, source, success, detail):
        """发布领域事件到 DEVICE_EVENTS 频道。"""
        payload = {
            'device_id': device_id,
            'event_type': event_type,
            'status': to_status,
            'source': source,
            'success': success,
            'detail': detail or {},
            'timestamp': datetime.now().isoformat(),
        }
        try:
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            EventBus().publish(EventChannel.DEVICE_EVENTS, EventType.DEVICE_STATUS_CHANGED, payload)
        except Exception:
            logger.debug("发布 DEVICE_STATUS_CHANGED 事件失败（降级忽略）", exc_info=True)

    def list_status_history(self, device_ids=None, event_type=None,
                            start_time=None, end_time=None,
                            page: int = 1, per_page: int = 50) -> dict:
        """状态历史趋势查询（读侧）。"""
        try:
            data = self.monitor_repo.list_status_events(
                device_ids=device_ids, event_type=event_type,
                start_time=start_time, end_time=end_time,
                page=int(page or 1), per_page=min(int(per_page or 50), 500),
            )
            return {'success': True, 'message': '查询成功', 'data': data, 'code': 200}
        except Exception as e:
            logger.exception("查询设备状态历史失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    # ========== 告警规则评估 ==========

    def evaluate_alarm_rules(self, devices: Optional[list] = None) -> list:
        """评估全部启用的告警规则，触发→落库→邮件。

        Args:
            devices: 设备快照 dict 列表（含 id/name/status/last_online_at）；
                     缺省时全量拉取。供监控线程与单测复用。

        Returns:
            本次新触发的告警 dict 列表
        """
        rules = self.monitor_repo.list_enabled_alarm_rules()
        if not rules:
            return []
        if devices is None:
            # 告警评估必须覆盖全部设备，单次全量拉取（UNLIMITED_PAGE_SIZE 为全量语义上限）
            result = self.device_repo.list_devices(
                page=1, per_page=QueryConstants.UNLIMITED_PAGE_SIZE)
            devices = result.get('items') or []
        if not devices:
            return []

        # 指标数据按设备一次聚合，规则×设备循环只读快照（消除逐设备 N+1 查询）
        device_ids = [d['id'] for d in devices]
        snapshots = {
            'failure_counts': self.monitor_repo.count_health_check_failures_batch(device_ids),
            'last_online_events': self.monitor_repo.get_last_online_events(device_ids),
            'latest_health': self.monitor_repo.get_latest_health_details(device_ids),
        }

        triggered = []
        for rule in rules:
            for device in devices:
                metric_value, context = self._collect_metric(rule, device, snapshots)
                if metric_value is None:
                    continue
                if not self._exceeds_threshold(rule['metric_type'], metric_value, float(rule['threshold_value'])):
                    continue
                if self.monitor_repo.has_unresolved_alarm(rule['id'], device['id']):
                    continue  # 未恢复告警去重：同规则+设备只报一次
                alarm = self._trigger_alarm(rule, device, metric_value, context)
                if alarm:
                    triggered.append(alarm)
        return triggered

    @staticmethod
    def _exceeds_threshold(metric_type: str, value: float, threshold: float) -> bool:
        if metric_type == AlarmMetricType.BATTERY.value:
            return value <= threshold  # 低电量：低于阈值告警
        return value >= threshold  # 离线时长/失败次数/CPU/内存：超过阈值告警

    def _collect_metric(self, rule: dict, device: dict, snapshots: dict) -> tuple:
        """采集规则指标当前值；无数据返回 (None, None) 不评估。

        指标数据取自 evaluate_alarm_rules 预聚合的按设备快照，不再逐设备查询。
        """
        metric = rule['metric_type']
        device_id = device['id']
        if metric == AlarmMetricType.OFFLINE_DURATION.value:
            if device.get('status') != 'offline':
                return None, None
            event = snapshots['last_online_events'].get(device_id)
            baseline = None
            if event and event.get('created_at'):
                try:
                    baseline = datetime.fromisoformat(event['created_at'])
                except (TypeError, ValueError):
                    baseline = None
            if baseline is None:
                # 无状态事件基线：回退 devices.last_online_at
                last_online = device.get('last_online_at')
                if isinstance(last_online, str):
                    try:
                        baseline = datetime.fromisoformat(last_online)
                    except (TypeError, ValueError):
                        baseline = None
                elif isinstance(last_online, datetime):
                    baseline = last_online
            if baseline is None:
                return None, None  # 从未在线的设备无离线时长语义
            seconds = max((datetime.now() - baseline).total_seconds(), 0)
            return seconds, {'since': baseline.isoformat()}

        if metric == AlarmMetricType.HEALTH_CHECK_FAILURES.value:
            return snapshots['failure_counts'].get(device_id, 0), None

        if metric in (AlarmMetricType.CPU.value, AlarmMetricType.MEMORY.value,
                      AlarmMetricType.BATTERY.value):
            detail = snapshots['latest_health'].get(device_id) or {}
            metrics = detail.get('metrics') or {}
            value = metrics.get(metric)
            if value is None:
                return None, None  # 驱动未上报该指标时不评估
            return float(value), None

        logger.warning("未知告警指标类型: %s (rule=%s)", metric, rule.get('id'))
        return None, None

    def _trigger_alarm(self, rule: dict, device: dict, metric_value: float, context: dict) -> Optional[dict]:
        """告警落库 + 邮件通知 + 审计日志。"""
        try:
            alarm = self.monitor_repo.create_alarm({
                'rule_id': rule['id'],
                'rule_name': rule['name'],
                'device_id': device['id'],
                'device_name': device.get('name'),
                'metric_type': rule['metric_type'],
                'severity': rule.get('severity') or AlarmSeverity.WARNING.value,
                'trigger_value': metric_value,
                'threshold_value': rule['threshold_value'],
                'content': self._alarm_content(rule, device, metric_value, context),
            })
        except Exception:
            logger.exception("告警落库失败 rule=%s device=%s", rule.get('id'), device.get('id'))
            return None

        self._log_alarm_triggered(alarm)
        if rule.get('notify_email'):
            self._send_alarm_email(alarm)
        return alarm

    @staticmethod
    def _alarm_content(rule: dict, device: dict, metric_value: float, context: dict) -> str:
        name = device.get('name') or f"设备{device.get('id')}"
        threshold = rule['threshold_value']
        metric = rule['metric_type']
        if metric == AlarmMetricType.OFFLINE_DURATION.value:
            return (f"设备「{name}」已离线 {metric_value / 60:.0f} 分钟"
                    f"（阈值 {threshold / 60:.0f} 分钟，自 {context.get('since', '')}）")
        if metric == AlarmMetricType.HEALTH_CHECK_FAILURES.value:
            return f"设备「{name}」健康检查连续失败 {int(metric_value)} 次（阈值 {int(threshold)} 次）"
        if metric == AlarmMetricType.BATTERY.value:
            return f"设备「{name}」电量 {metric_value:.0f}% 低于阈值 {threshold:.0f}%"
        return f"设备「{name}」{metric} 使用率 {metric_value:.1f}% 超过阈值 {threshold:.1f}%"

    @staticmethod
    def _log_alarm_triggered(alarm: dict) -> None:
        """告警触发审计（旁路）：AuditEvent.DEVICE_ALARM_TRIGGERED 落 logs（category=device）。

        device_service 内部触发无网关请求上下文，直接经 log_not_emit 写审计事件，
        payload 结构对齐 api_gateway write_device_audit（content 为含 event 键的 JSON）。
        """
        try:
            payload = {
                'event': AuditEvent.DEVICE_ALARM_TRIGGERED.value,
                'alarm_id': alarm.get('id'),
                'rule_id': alarm.get('rule_id'),
                'rule_name': alarm.get('rule_name'),
                'device_id': alarm.get('device_id'),
                'device_name': alarm.get('device_name'),
                'metric_type': alarm.get('metric_type'),
                'severity': alarm.get('severity'),
                'trigger_value': alarm.get('trigger_value'),
                'threshold_value': alarm.get('threshold_value'),
                'content': alarm.get('content'),
            }
            log_not_emit(
                'WARNING', 'DeviceMonitor',
                json.dumps(payload, ensure_ascii=False, default=str),
                category=AuditLogCategory.DEVICE.value, source='backend',
                device_id=alarm.get('device_id'),
            )
        except Exception:
            logger.debug("告警审计日志写入失败", exc_info=True)

    def _send_alarm_email(self, alarm: dict) -> None:
        """告警邮件通知（SMTP 配置化；未配置/失败降级为记录 email_error）。"""
        from shared.utils.email_sender import send_email
        severity = alarm.get('severity', 'warning')
        subject = f"【设备告警-{severity}】{alarm.get('device_name') or alarm.get('device_id')} {alarm.get('rule_name')}"
        body = (
            f"设备告警通知\n\n"
            f"级别: {severity}\n"
            f"设备: {alarm.get('device_name')} (ID: {alarm.get('device_id')})\n"
            f"规则: {alarm.get('rule_name')} (ID: {alarm.get('rule_id')})\n"
            f"指标: {alarm.get('metric_type')}\n"
            f"触发值: {alarm.get('trigger_value')} / 阈值: {alarm.get('threshold_value')}\n"
            f"内容: {alarm.get('content')}\n"
            f"时间: {alarm.get('triggered_at')}\n"
        )
        result = send_email(subject, body)
        try:
            self.monitor_repo.update_alarm_email(
                alarm['id'], result.success, '' if result.success else result.message)
        except Exception:
            logger.warning("告警邮件结果回写失败 alarm_id=%s", alarm.get('id'), exc_info=True)

    # ========== 告警确认流 ==========

    def acknowledge_alarm(self, alarm_id: int, acknowledged_by: str) -> dict:
        try:
            alarm = self.monitor_repo.acknowledge_alarm(alarm_id, acknowledged_by)
            if not alarm:
                return {'success': False, 'message': '告警不存在或已确认/恢复',
                        'data': None, 'code': 404}
            log_not_emit(
                'INFO', 'DeviceMonitor',
                f"告警已确认: alarm_id={alarm_id} by={acknowledged_by}",
                category='device', source='backend',
                device_id=alarm.get('device_id'),
            )
            return {'success': True, 'message': '告警已确认', 'data': alarm, 'code': 200}
        except Exception as e:
            logger.exception("确认告警失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_alarm_stats(self) -> dict:
        try:
            return {'success': True, 'message': '查询成功',
                    'data': self.monitor_repo.get_alarm_stats(), 'code': 200}
        except Exception as e:
            logger.exception("查询告警统计失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def list_alarms(self, status=None, severity=None, device_id=None,
                    page: int = 1, per_page: int = 50) -> dict:
        try:
            data = self.monitor_repo.list_alarms(
                status=status, severity=severity, device_id=device_id,
                page=int(page or 1), per_page=min(int(per_page or 50), 500))
            data['stats'] = self.monitor_repo.get_alarm_stats()
            return {'success': True, 'message': '查询成功', 'data': data, 'code': 200}
        except Exception as e:
            logger.exception("查询告警列表失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


device_monitor_service = DeviceMonitorService()


class DeviceMonitorThread:
    """设备监控守护线程：周期健康检查 + 告警规则评估。

    启动方式：device_service gRPC server 启动时调用 start()（幂等），
    与软删除清理线程同模式。健康检查复用 DeviceCommandService.health_check
    （其内部已走 record 状态事件链路），随后评估告警规则。
    """

    def __init__(self, interval_seconds: int = _MONITOR_INTERVAL_SECONDS):
        self.interval_seconds = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _loop(self):
        from device_service.application.commands.device_command_service import device_command_service
        while not self._stop_event.wait(timeout=self.interval_seconds):
            try:
                device_command_service.health_check()
            except Exception:
                logger.warning("[DeviceMonitor] 周期健康检查失败", exc_info=True)
            try:
                triggered = device_monitor_service.evaluate_alarm_rules()
                if triggered:
                    logger.info("[DeviceMonitor] 本轮触发 %s 条告警", len(triggered))
            except Exception:
                logger.warning("[DeviceMonitor] 告警规则评估失败", exc_info=True)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name='device-monitor', daemon=True)
        self._thread.start()
        logger.info("[DeviceMonitor] 监控线程已启动 (interval=%ss)", self.interval_seconds)

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


_monitor_thread: Optional[DeviceMonitorThread] = None
_monitor_thread_lock = threading.Lock()


def get_monitor_thread() -> DeviceMonitorThread:
    """获取监控线程单例（幂等启动）"""
    global _monitor_thread
    with _monitor_thread_lock:
        if _monitor_thread is None:
            _monitor_thread = DeviceMonitorThread()
        return _monitor_thread
