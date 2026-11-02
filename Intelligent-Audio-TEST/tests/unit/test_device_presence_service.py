# -*- coding: utf-8 -*-
"""设备热插拔事件入账单测（application 层；DevicePresenceService）。

覆盖：快照对账只改本系统设备、在线/离线/未授权归一、无变化不写库。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.application.services.device_presence_service import (  # noqa: E402
    DevicePresenceService,
    _belongs_to_system,
)


class FakeRepo:
    def __init__(self, devices):
        self._devices = devices
        self.status_updates = []

    def list_devices(self, page=1, per_page=10, **kwargs):
        return {'items': self._devices, 'total': len(self._devices)}

    def update_device_statuses(self, updates):
        self.status_updates.extend(updates)
        for device in self._devices:
            for update in updates:
                if update['id'] == device['id']:
                    device['status'] = update['status']
        return len(updates)


class FakeMonitor:
    def __init__(self):
        self.events = []

    def record_status_events(self, events):
        self.events.extend(events)
        return events


def build_service(devices):
    repo = FakeRepo(devices)
    monitor = FakeMonitor()
    service = DevicePresenceService(repo=repo, monitor=monitor, factory=object())
    return service, repo, monitor


def test_reconcile_marks_absent_device_offline_only_in_own_system():
    devices = [
        {'id': 1, 'system': 'Android', 'serial_number': 'SN1', 'status': 'online'},
        {'id': 2, 'system': 'Android', 'serial_number': 'SN2', 'status': 'online'},
        {'id': 3, 'system': 'HarmonyOS 4.0', 'serial_number': 'H1', 'status': 'online'},
    ]
    service, repo, monitor = build_service(devices)

    changed = service.reconcile('Android', {'SN1': 'device'})

    assert changed == 1
    assert repo.status_updates == [
        {'id': 2, 'status': 'offline', 'last_online_at': None},
    ]
    assert monitor.events[0]['device_id'] == 2
    assert monitor.events[0]['from_status'] == 'online'
    assert monitor.events[0]['to_status'] == 'offline'
    assert monitor.events[0]['source'] == 'presence'
    # HarmonyOS 设备不被 Android 快照误判
    assert devices[2]['status'] == 'online'


def test_reconcile_online_snapshot_restores_status():
    devices = [
        {'id': 1, 'system': 'Android', 'serial_number': 'SN1', 'status': 'offline'},
    ]
    service, repo, monitor = build_service(devices)

    changed = service.reconcile('Android', {'SN1': 'device'})

    assert changed == 1
    assert repo.status_updates[0]['status'] == 'online'
    assert repo.status_updates[0]['last_online_at'] is not None
    assert monitor.events[0]['success'] is True


def test_reconcile_unauthorized_is_offline():
    devices = [
        {'id': 1, 'system': 'Android', 'serial_number': 'SN1', 'status': 'online'},
    ]
    service, repo, _ = build_service(devices)

    assert service.reconcile('Android', {'SN1': 'unauthorized'}) == 1
    assert repo.status_updates[0]['status'] == 'offline'


def test_reconcile_without_change_writes_nothing():
    devices = [
        {'id': 1, 'system': 'Android', 'serial_number': 'SN1', 'status': 'online'},
    ]
    service, repo, monitor = build_service(devices)

    assert service.reconcile('Android', {'SN1': 'device'}) == 0
    assert repo.status_updates == []
    assert monitor.events == []


def test_system_match_tolerates_version_suffix():
    assert _belongs_to_system('HarmonyOS 4.0', 'HarmonyOS') is True
    assert _belongs_to_system('Android 14', 'Android') is True
    assert _belongs_to_system('HarmonyOS', 'Android') is False
    assert _belongs_to_system(None, 'Android') is False
