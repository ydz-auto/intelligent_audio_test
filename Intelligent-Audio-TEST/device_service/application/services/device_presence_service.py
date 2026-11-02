# -*- coding: utf-8 -*-
"""设备在线状态事件入账（application 层；设备热插拔实时态）。

链路：
驱动 ``watch_device_snapshots()``（Android：``adb track-devices -l`` 长连接；
HarmonyOS：``hdc list targets`` 短周期变更检测，hdc 3.2.0c 无原生 track 命令）
→ 本服务对已登记测试设备做全量快照对账
→ ``devices.status / last_online_at`` 落库
→ ``DeviceMonitorService.record_status_events`` 发布 ``DEVICE_EVENTS``
→ api_gateway SSE ``device_status_changed`` → 前端刷新设备列表。

不支持热插拔监听的系统不启线程，由 ``DeviceMonitorThread`` 的周期健康检查
兜底；网络类设备（HTTP/WS API、播放服务器）同样只能靠健康检查/心跳。
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from shared.config.query_constants import QueryConstants
from shared.models.common_enums import DeviceStatusEventType
from shared.utils.config_manager import config_manager
from shared.utils.query_utils import now_cst
from device_service.infrastructure.drivers.adb_track import is_device_online

logger = logging.getLogger(__name__)

# 需要实时监听的设备系统（与 DriverFactory 基础驱动键一致）
DEVICE_WATCH_SYSTEMS = ('Android', 'HarmonyOS')
# 断开后重连退避（秒），Redis/进程重启抖动用短退避，长时间不可用封顶
_RECONNECT_BASE_SECONDS = config_manager.get_value(
    'device_presence', 'reconnect_base_seconds', 2)
_RECONNECT_MAX_SECONDS = config_manager.get_value(
    'device_presence', 'reconnect_max_seconds', 30)
# 状态事件来源标记（区别于 health_check / operation / monitor）
_PRESENCE_EVENT_SOURCE = 'presence'


def _is_presence_enabled() -> bool:
    return bool(config_manager.get_value('device_presence', 'enabled', True))


def _belongs_to_system(device_system: Optional[str], watched_system: str) -> bool:
    """设备 system 与监听系统是否同一平台（DB 里常见 HarmonyOS 4.0 等写法）。"""
    device_key = (device_system or '').lower()
    watched_key = watched_system.lower()
    if not device_key or not watched_key:
        return False
    return device_key == watched_key or device_key in watched_key or watched_key in device_key


class DevicePresenceService:
    """设备热插拔事件消费：驱动快照流 → 状态入账 → DEVICE_EVENTS。"""

    def __init__(self, repo=None, monitor=None, factory=None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import device_repository
            repo = device_repository
        if monitor is None:
            from device_service.application.services.device_monitor_service import device_monitor_service
            monitor = device_monitor_service
        if factory is None:
            from device_service.infrastructure.drivers.driver_factory import device_driver_factory
            factory = device_driver_factory
        self.repo = repo
        self.monitor = monitor
        self.factory = factory
        self._threads = {}
        self._drivers = {}
        self._stop_event = threading.Event()

    # ========== 生命周期 ==========

    def start(self) -> None:
        """按系统拉起监听线程（幂等；不支持的系统跳过并保留轮询兜底）。"""
        if not _is_presence_enabled():
            logger.info("[DevicePresence] 配置关闭，跳过设备热插拔监听")
            return
        for system in DEVICE_WATCH_SYSTEMS:
            driver = self.factory.get_driver_by_system(system)
            if driver is None:
                logger.debug("[DevicePresence] 未找到 %s 基础驱动，跳过", system)
                continue
            if not driver.supports_device_watch():
                logger.info("[DevicePresence] %s 不支持设备热插拔监听，保留周期健康检查兜底", system)
                continue
            existing = self._threads.get(system)
            if existing is not None and existing.is_alive():
                continue
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._watch_loop, args=(system, driver),
                name=f'device-presence-{system.lower()}', daemon=True,
            )
            self._threads[system] = thread
            self._drivers[system] = driver
            thread.start()
            logger.info("[DevicePresence] %s 热插拔监听已启动", system)

    def stop(self) -> None:
        self._stop_event.set()
        # 阻塞式监听（adb track-devices 子进程）需要驱动侧主动释放
        for driver in self._drivers.values():
            driver.stop_device_watch()
        for thread in self._threads.values():
            thread.join(timeout=_RECONNECT_MAX_SECONDS)
        self._threads.clear()
        self._drivers.clear()

    # ========== 监听循环 ==========

    def _watch_loop(self, system: str, driver) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            try:
                for snapshot in driver.watch_device_snapshots(self._stop_event):
                    if self._stop_event.is_set():
                        break
                    attempt = 0
                    self.reconcile(system, snapshot)
            except Exception:
                logger.warning("[DevicePresence] %s 监听流异常", system, exc_info=True)
            if self._stop_event.is_set():
                break
            attempt += 1
            delay = min(_RECONNECT_BASE_SECONDS * (2 ** (attempt - 1)), _RECONNECT_MAX_SECONDS)
            logger.info("[DevicePresence] %s 监听流断开，%ss 后重连", system, delay)
            if self._stop_event.wait(delay):
                break

    # ========== 快照对账 ==========

    def reconcile(self, system: str, snapshot: dict) -> int:
        """把一次全量设备快照对账到本系统已登记测试设备，返回实际变更条数。"""
        devices = self._list_test_devices()
        if not devices:
            return 0
        online_at = now_cst()
        status_updates = []
        status_events = []
        for device in devices:
            if not _belongs_to_system(device.get('system'), system):
                continue
            serial = (device.get('serial_number') or '').strip()
            if not serial:
                continue
            desired = (
                DeviceStatusEventType.ONLINE.value
                if is_device_online(snapshot.get(serial, ''))
                else DeviceStatusEventType.OFFLINE.value
            )
            current = device.get('status')
            if current == desired:
                continue
            status_updates.append({
                'id': device['id'],
                'status': desired,
                'last_online_at': online_at if desired == DeviceStatusEventType.ONLINE.value else None,
            })
            status_events.append({
                'device_id': device['id'],
                'event_type': desired,
                'from_status': current,
                'to_status': desired,
                'source': _PRESENCE_EVENT_SOURCE,
                'success': desired == DeviceStatusEventType.ONLINE.value,
                'detail': {'serial_number': serial, 'system': system},
            })
        if status_updates:
            self.repo.update_device_statuses(status_updates)
            self.monitor.record_status_events(status_events)
            logger.info(
                "[DevicePresence] %s 快照对账：设备状态变更 %s 台", system, len(status_updates))
        return len(status_updates)

    def _list_test_devices(self) -> list:
        result = self.repo.list_devices(page=1, per_page=QueryConstants.UNLIMITED_PAGE_SIZE)
        if isinstance(result, dict):
            return result.get('items') or []
        return []


device_presence_service: Optional['DevicePresenceService'] = None
_presence_lock = threading.Lock()


def get_device_presence_service() -> 'DevicePresenceService':
    """获取设备热插拔监听单例（幂等；首次调用才装配仓储/驱动/监控依赖）。"""
    global device_presence_service
    with _presence_lock:
        if device_presence_service is None:
            device_presence_service = DevicePresenceService()
        return device_presence_service
