# -*- coding: utf-8 -*-
"""INT-2258 设备批量健康检查性能修复的验收单测。

覆盖卡内验收：
1. 同一 system 的驱动只做一次全量 scan（10 台设备按不同 system 个数调用）；
2. 不再有人为随机等待（进程内 time.sleep 零调用、10 台设备耗时远低于旧的最短 5s）；
3. 状态更新与状态事件按批提交，commit 次数 ≤ 批次阈值，而不是每设备多次；
4. 既有状态事件字段不减少（health_check / 状态变更两条腿、字段口径不变）。
"""
import math
import os
import time
from unittest.mock import patch

# BaseConfig 类属性首次 import 即校验 OSS 配置；本模块不触网，占位即可
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.application.commands import device_command_service as command_module
from device_service.application.commands.device_command_service import DeviceCommandService

_BATCH_SIZE = command_module._HEALTH_CHECK_BATCH_SIZE


class _CountingDriver:
    """按 system 记录扫描次数；scan() 模拟一次全量设备扫描。"""

    def __init__(self, system, online_serials):
        self.system = system
        self.online_serials = set(online_serials)
        self._mock_mode = True  # 健康检查扫描期间应被临时置为 False
        self.scan_calls = 0

    def scan(self):
        self.scan_calls += 1
        assert self._mock_mode is False
        return [{'serial': serial} for serial in self.online_serials]


class _BatchRepo:
    """健康检查只用到读设备 + 批量写状态；记录每次批量写（= 一次事务）。"""

    def __init__(self, devices):
        self._devices = devices
        self.update_calls = []

    def list_devices(self, page=1, per_page=100):
        return {'items': [dict(device) for device in self._devices]}

    def get_device(self, device_id):
        for device in self._devices:
            if device['id'] == device_id:
                class _Device:
                    def to_dict(self):
                        return dict(device)
                return _Device()
        return None

    def update_device_status(self, device_id, status, last_online_at=None):
        raise AssertionError('批量健康检查不应逐条提交状态')

    def update_device_statuses(self, updates):
        self.update_calls.append([dict(update) for update in updates])
        return len(updates)


class _BatchMonitor:
    """记录批量落库调用（= 一次事务）；逐条接口被调用即视为回退。"""

    def __init__(self):
        self.batch_calls = []
        self.events = []

    def record_status_event(self, **kwargs):
        raise AssertionError('批量健康检查不应逐条提交状态事件')

    def record_status_events(self, events):
        self.batch_calls.append([dict(event) for event in events])
        self.events.extend(dict(event) for event in events)
        return list(events)


def _device(device_id, system, serial_number, status='offline'):
    return {
        'id': device_id,
        'name': f'INT2258设备{device_id}',
        'model': 'M',
        'system': system,
        'serial_number': serial_number,
        'status': status,
    }


def _run_health_check(devices, drivers, device_ids=None):
    """在驱动工厂/监控服务被替身的隔离环境里跑一次健康检查。"""
    repo = _BatchRepo(devices)
    monitor = _BatchMonitor()
    service = DeviceCommandService(repo=repo)

    def _get_driver_by_system(system):
        return drivers.get((system or '').strip().lower())

    with patch(
        'device_service.infrastructure.drivers.driver_factory.device_driver_factory'
    ) as factory, patch(
        'device_service.application.services.device_monitor_service.device_monitor_service',
        monitor,
    ), patch.object(
        DeviceCommandService, '_collect_health_metrics', staticmethod(lambda device_data: {}),
    ):
        factory.get_driver_by_system.side_effect = _get_driver_by_system
        return service.health_check(device_ids), repo, monitor


class TestScanReuse:
    def test_scan_called_once_per_system_for_ten_devices(self):
        """10 台设备、2 个 system：每个驱动只扫描一次（旧实现是每台一次共 10 次）。"""
        devices = [
            _device(1, 'Android', 'A-ONLINE-1'),
            _device(2, 'Android', 'A-ONLINE-2'),
            _device(3, 'Android', 'A-OFFLINE-1'),
            _device(4, 'Android', 'A-OFFLINE-2'),
            _device(5, 'Android', 'A-OFFLINE-3'),
            _device(6, 'Android', 'A-OFFLINE-4'),
            _device(7, 'HarmonyOS', 'H-ONLINE-1'),
            _device(8, 'HarmonyOS', 'H-ONLINE-2'),
            _device(9, 'HarmonyOS', 'H-OFFLINE-1'),
            _device(10, 'HarmonyOS', 'H-OFFLINE-2'),
        ]
        android = _CountingDriver('Android', ['A-ONLINE-1', 'A-ONLINE-2'])
        harmony = _CountingDriver('HarmonyOS', ['H-ONLINE-1', 'H-ONLINE-2'])

        result, _, _ = _run_health_check(devices, {'android': android, 'harmonyos': harmony})

        assert android.scan_calls == 1
        assert harmony.scan_calls == 1
        statuses = {item['id']: item['status'] for item in result['data']}
        assert statuses == {
            1: 'online', 2: 'online',
            3: 'offline', 4: 'offline', 5: 'offline', 6: 'offline',
            7: 'online', 8: 'online', 9: 'offline', 10: 'offline',
        }
        assert result['message'] == '成功完成 10 个设备的健康检查'

    def test_same_driver_instance_scanned_once_for_system_aliases(self):
        """同一驱动实例覆盖多个 system 写法（大小写/别名）时也只扫描一次。"""
        devices = [
            _device(1, 'HarmonyOS', 'H-1'),
            _device(2, 'harmonyos', 'H-2'),
            _device(3, 'harmony', 'H-3'),
        ]
        harmony = _CountingDriver('HarmonyOS', ['H-1', 'H-2', 'H-3'])

        result, _, _ = _run_health_check(
            devices,
            {'harmonyos': harmony, 'harmony': harmony},
        )

        assert harmony.scan_calls == 1
        assert all(item['status'] == 'online' for item in result['data'])

    def test_scan_exception_only_affects_that_system(self):
        devices = [
            _device(1, 'Android', 'A-1'),
            _device(2, 'HarmonyOS', 'H-1'),
        ]

        class _BrokenAndroid(_CountingDriver):
            def scan(self):
                self.scan_calls += 1
                raise RuntimeError('adb not found')

        android = _BrokenAndroid('Android', [])
        harmony = _CountingDriver('HarmonyOS', ['H-1'])

        result, _, _ = _run_health_check(
            devices, {'android': android, 'harmonyos': harmony})

        statuses = {item['id']: item['status'] for item in result['data']}
        assert statuses == {1: 'offline', 2: 'online'}
        assert result['success'] is True

    def test_device_without_serial_is_offline(self):
        devices = [_device(1, 'Android', None)]
        android = _CountingDriver('Android', [])

        result, _, _ = _run_health_check(devices, {'android': android})

        assert result['data'][0]['status'] == 'offline'


class TestNoArtificialDelay:
    def test_ten_devices_check_without_sleep(self):
        """旧实现每台 0.5~2s 随机等待（10 台 ≥5s）；现在不允许任何 sleep 调用。"""
        devices = [
            _device(index, 'Android' if index <= 5 else 'HarmonyOS', f'S-{index}')
            for index in range(1, 11)
        ]
        android = _CountingDriver('Android', [f'S-{index}' for index in range(1, 6)])
        harmony = _CountingDriver('HarmonyOS', [f'S-{index}' for index in range(6, 11)])

        with patch('time.sleep') as sleep_mock:
            started = time.perf_counter()
            result, _, _ = _run_health_check(
                devices, {'android': android, 'harmonyos': harmony})
            elapsed = time.perf_counter() - started

        assert sleep_mock.call_count == 0
        assert elapsed < 1.0, f'10 台设备健康检查耗时 {elapsed:.2f}s，疑似仍有等待'
        assert len(result['data']) == 10


class TestBatchedCommits:
    def test_commits_bounded_by_batch_threshold(self):
        """120 台设备 → 3 批：状态 3 次提交 + 事件 3 次提交，远少于逐台提交。"""
        devices = [_device(index, 'Android', f'S-{index}') for index in range(1, 121)]
        android = _CountingDriver('Android', [f'S-{index}' for index in range(0, 0)])

        result, repo, monitor = _run_health_check(devices, {'android': android})

        expected_batches = math.ceil(len(devices) / _BATCH_SIZE)
        assert len(result['data']) == len(devices)
        assert len(repo.update_calls) == expected_batches
        assert len(monitor.batch_calls) == expected_batches
        # 每批更新的设备数不超过批次阈值
        assert all(len(call) <= _BATCH_SIZE for call in repo.update_calls)
        # 总提交次数 <= 每设备至少一次状态提交 + 至少一条事件提交的下界
        assert len(repo.update_calls) + len(monitor.batch_calls) <= len(devices) * 2

    def test_ten_devices_single_batch(self):
        devices = [_device(index, 'Android', f'S-{index}') for index in range(1, 11)]
        android = _CountingDriver('Android', [])

        _, repo, monitor = _run_health_check(devices, {'android': android})

        assert len(repo.update_calls) == 1
        assert len(monitor.batch_calls) == 1


class TestStatusEventFieldsPreserved:
    def test_status_change_writes_health_check_and_transition_events(self):
        devices = [_device(1, 'Android', 'A-1', status='offline')]
        android = _CountingDriver('Android', ['A-1'])

        _, repo, monitor = _run_health_check(devices, {'android': android})

        event_types = [event['event_type'] for event in monitor.events]
        assert event_types == ['health_check', 'online']  # 状态变更追加一条，字段不减少
        health_event = monitor.events[0]
        assert health_event == {
            'device_id': 1,
            'event_type': 'health_check',
            'from_status': 'offline',
            'to_status': 'online',
            'source': 'health_check',
            'success': True,
            'detail': {'serial_number': 'A-1'},
        }
        transition_event = monitor.events[1]
        assert transition_event['from_status'] == 'offline'
        assert transition_event['to_status'] == 'online'
        assert transition_event['detail'] == {'serial_number': 'A-1'}
        assert repo.update_calls[0][0]['last_online_at'] is not None

    def test_unchanged_status_writes_only_health_check_event(self):
        devices = [_device(1, 'Android', 'A-1', status='online')]
        android = _CountingDriver('Android', ['A-1'])

        _, _, monitor = _run_health_check(devices, {'android': android})

        assert [event['event_type'] for event in monitor.events] == ['health_check']

    def test_explicit_device_ids_path(self):
        """显式传 ID 只处理这些设备（get_device 路径），不触发全表读取。"""
        devices = [
            _device(1, 'Android', 'A-1'),
            _device(2, 'Android', 'A-2'),
            _device(3, 'Android', 'A-3'),
        ]
        android = _CountingDriver('Android', ['A-1', 'A-3'])

        result, repo, _ = _run_health_check(
            devices, {'android': android}, device_ids=[1, 3])

        assert [item['id'] for item in result['data']] == [1, 3]
        assert len(repo.update_calls) == 1


class TestBatchPersistence:
    """批量写落库真仓储（sqlite）：一次提交写全批，字段口径不变。"""

    IDS = [91225801, 91225802, 91225803]

    @staticmethod
    def _session():
        from shared.models import database
        from device_service.infrastructure.persistence.models import (
            Device,
            DeviceStatusEvent,
        )

        database.init_db()
        database.Base.metadata.create_all(
            bind=database.get_engine(),
            tables=[Device.__table__, DeviceStatusEvent.__table__])
        session = database.get_db_session()
        session.query(DeviceStatusEvent).filter(
            DeviceStatusEvent.device_id.in_(TestBatchPersistence.IDS)).delete(
            synchronize_session=False)
        session.query(Device).filter(
            Device.id.in_(TestBatchPersistence.IDS)).delete(synchronize_session=False)
        session.add_all([
            Device(id=device_id, name=f'INT2258批量{device_id}', model='M', type='phone',
                   system='Android', system_version='14', app_name='a', app_version='1',
                   serial_number=f'BATCH-{device_id}', status='offline', deleted=False)
            for device_id in TestBatchPersistence.IDS
        ])
        session.commit()
        return session

    def _cleanup(self):
        from shared.models import database
        from device_service.infrastructure.persistence.models import (
            Device,
            DeviceStatusEvent,
        )

        session = database.get_db_session()
        session.query(DeviceStatusEvent).filter(
            DeviceStatusEvent.device_id.in_(self.IDS)).delete(synchronize_session=False)
        session.query(Device).filter(Device.id.in_(self.IDS)).delete(
            synchronize_session=False)
        session.commit()

    def test_update_device_statuses_persists_whole_batch(self):
        from datetime import datetime

        from device_service.infrastructure.persistence.device_repository import (
            device_repository,
        )
        from device_service.infrastructure.persistence.models import Device

        session = self._session()
        try:
            online_at = datetime(2026, 10, 31, 9, 0)
            updated = device_repository.update_device_statuses([
                {'id': self.IDS[0], 'status': 'online', 'last_online_at': online_at},
                {'id': self.IDS[1], 'status': 'offline', 'last_online_at': None},
                {'id': 999999999, 'status': 'online', 'last_online_at': online_at},  # 不存在，跳过
            ])

            assert updated == 2
            session.expire_all()
            rows = {row.id: row for row in session.query(Device).filter(
                Device.id.in_(self.IDS)).all()}
            assert rows[self.IDS[0]].status == 'online'
            assert rows[self.IDS[0]].last_online_at == online_at
            assert rows[self.IDS[1]].status == 'offline'
            assert rows[self.IDS[2]].status == 'offline'  # 未在批内，保持原值
        finally:
            self._cleanup()

    def test_status_event_mapping_fields_unchanged(self):
        """批量落库复用单条构造：字段口径与 record_status_event 完全一致。

        （sqlite 的 device_status_events.id 是 BIGINT 非自增列，无法在本机落库，
        故此处只核对 PO 构造字段；落库链路由 INT-1578 的 PG/链路用例覆盖。）
        """
        from device_service.infrastructure.persistence.device_monitor_repository import (
            DeviceMonitorRepository,
        )

        po = DeviceMonitorRepository._build_status_event_po({
            'device_id': self.IDS[0],
            'event_type': 'health_check',
            'from_status': 'offline',
            'to_status': 'online',
            'source': 'health_check',
            'success': True,
            'detail': {'serial_number': 'BATCH-1', 'metrics': {'battery': 88.0}},
        })

        assert po.device_id == self.IDS[0]
        assert po.device_kind == 'test'  # 默认测试设备，播放侧不受影响
        assert po.event_type == 'health_check'
        assert po.from_status == 'offline'
        assert po.to_status == 'online'
        assert po.source == 'health_check'
        assert po.success is True
        assert po.detail == {'serial_number': 'BATCH-1', 'metrics': {'battery': 88.0}}
