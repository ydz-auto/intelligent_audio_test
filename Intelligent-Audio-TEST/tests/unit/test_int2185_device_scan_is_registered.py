# -*- coding: utf-8 -*-
"""INT-2185 回归：设备扫描 is_registered 按 serial 判定，注册后回读一致。

背景：4b6d2c9d4 为让扫描行「始终可添加」把 is_registered 写死 False，顺带丢掉了
展示语义（前端无法区分已注册/未注册）。本卡把展示与添加动作解耦：

- is_registered = 有 serial 且 serial 出现在未删除设备的 serial 集合里；
- 仍不按 serial 去重/过滤，扫描行（含同 serial 多行）始终保留、始终可添加。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock, patch

from device_service.application.commands.device_command_service import DeviceCommandService

FACTORY_TARGET = 'device_service.infrastructure.drivers.driver_factory.device_driver_factory'


class FakeDriver:
    def __init__(self, devices=None):
        self._mock_mode = False
        self._devices = devices or []

    def scan(self):
        return [dict(d) for d in self._devices]


def _scan_with(scan_devices, registered_serials):
    factory = MagicMock()
    factory.get_driver_by_system.side_effect = (
        lambda system: FakeDriver(scan_devices) if system == 'HarmonyOS' else FakeDriver([]))
    factory.get_mock_mode.return_value = False
    repo = MagicMock()
    repo.get_all_device_serials.return_value = list(registered_serials)
    svc = DeviceCommandService(repo=repo)
    with patch(FACTORY_TARGET, factory):
        result = svc.scan()
    return result, repo


class TestScanIsRegisteredBySerial:
    def test_registered_serial_reads_true(self):
        result, _ = _scan_with(
            [{'serial': '5SM0125701000448', 'model': 'H', 'system': 'HarmonyOS'}],
            ['5SM0125701000448'])
        assert result['success'] is True
        assert result['data'][0]['is_registered'] is True

    def test_unregistered_serial_reads_false(self):
        result, _ = _scan_with(
            [{'serial': '5SM0125701000448', 'model': 'H', 'system': 'HarmonyOS'}],
            ['other-serial'])
        assert result['data'][0]['is_registered'] is False

    def test_empty_serial_never_registered(self):
        result, _ = _scan_with(
            [{'serial': '', 'model': 'H', 'system': 'HarmonyOS'}],
            [''])
        assert result['data'][0]['is_registered'] is False

    def test_duplicate_registered_rows_kept_and_all_true(self):
        # 同 serial 多行都保留（不按 serial 去重/过滤），展示状态一致
        scan = [{'serial': 'sn-dup', 'model': 'H', 'system': 'HarmonyOS'},
                {'serial': 'sn-dup', 'model': 'H', 'system': 'HarmonyOS'}]
        result, _ = _scan_with(scan, ['sn-dup'])
        assert len(result['data']) == 2
        assert all(d['is_registered'] is True for d in result['data'])

    def test_registration_does_not_gate_adding(self):
        # is_registered 只做展示：已注册行依旧返回，不因已注册被剔除或标记为不可添加
        result, repo = _scan_with(
            [{'serial': 'sn-1', 'model': 'H', 'system': 'HarmonyOS'}],
            ['sn-1'])
        assert [d['serial'] for d in result['data']] == ['sn-1']
        repo.get_all_device_serials.assert_called_once_with()

    def test_scan_reads_registered_serials_once(self):
        result, repo = _scan_with(
            [{'serial': 'a', 'model': 'H', 'system': 'HarmonyOS'},
             {'serial': 'b', 'model': 'H', 'system': 'HarmonyOS'}],
            ['a'])
        assert [d['is_registered'] for d in result['data']] == [True, False]
        assert repo.get_all_device_serials.call_count == 1
