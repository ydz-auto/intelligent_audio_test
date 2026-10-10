# -*- coding: utf-8 -*-
"""INT-86 验收：扫描链路驱动解析回归锁定。

背景：get_driver_for_device 语义收紧（keywords 必填，INT-83）后，扫描链路
（POST /test-devices/scan、GET /test-devices/serials、注册后在线检查、健康检查）
仍按无 keywords 旧方式调用导致固定 400 / 静默失效。修复（INT-86）统一改用
get_driver_by_system 取平台基础驱动。

覆盖：
- scan / get_available_serials 全部经 get_driver_by_system 解析（Android/iOS/HarmonyOS），
  不再触发 get_driver_for_device（无 keywords 会抛 ValueError）
- 无真机且 mock 开启时回退 3 条 mock 设备
- 健康检查：扫描命中序列号 → online（修复前此处抛 ValueError 全部误标 offline）；
  未命中 → offline
- 注册设备在线检查：serial 命中扫描结果 → 置 online
- get_driver_for_device keywords 必填语义未放松（真实工厂实例）
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from device_service.application.commands.device_command_service import DeviceCommandService
from device_service.application.queries.device_query_service import DeviceQueryService

FACTORY_TARGET = 'device_service.infrastructure.drivers.device_driver.device_driver_factory'


class FakeDriver:
    """带 _mock_mode 的替身驱动，scan() 返回可配置结果。"""

    def __init__(self, devices=None):
        self._mock_mode = False
        self._devices = devices or []

    def scan(self):
        return list(self._devices)


def _fake_factory(drivers=None, mock_mode=False):
    factory = MagicMock()
    factory.get_driver_by_system.side_effect = lambda system: (drivers or {}).get(system)
    factory.get_mock_mode.return_value = mock_mode
    factory.get_driver_for_device = MagicMock(
        side_effect=ValueError('设备必须提供明确的驱动 keywords 标识'))
    return factory


def _repo_stub(devices=None):
    repo = MagicMock()
    repo.list_devices.return_value = {'items': list(devices or [])}
    repo.update_device_status.return_value = True
    repo.get_all_device_serials.return_value = []
    return repo


PLATFORMS = ['Android', 'iOS', 'HarmonyOS']


class TestScanUsesPlatformBaseDriver:
    def test_scan_resolves_three_platforms_by_system(self):
        drivers = {p: FakeDriver([]) for p in PLATFORMS}
        factory = _fake_factory(drivers)
        svc = DeviceCommandService(repo=_repo_stub())
        with patch(FACTORY_TARGET, factory):
            result = svc.scan()
        assert result['success'] is True
        assert result['data'] == []
        assert {call.args[0] for call in factory.get_driver_by_system.call_args_list} == set(PLATFORMS)
        factory.get_driver_for_device.assert_not_called()

    def test_scan_collects_all_platform_results(self):
        drivers = {
            'Android': FakeDriver([{'serial': 'adb-1', 'model': 'A', 'system': 'Android'}]),
            'iOS': FakeDriver([]),
            'HarmonyOS': FakeDriver([{'serial': 'hdc-1', 'model': 'H', 'system': 'HarmonyOS'}]),
        }
        factory = _fake_factory(drivers)
        svc = DeviceCommandService(repo=_repo_stub())
        with patch(FACTORY_TARGET, factory):
            result = svc.scan()
        serials = [d['serial'] for d in result['data']]
        assert serials == ['adb-1', 'hdc-1']

    def test_scan_skips_platform_without_base_driver(self):
        # iOS 无平台基础驱动：get_driver_by_system 返回 None 应跳过而非报错
        drivers = {'Android': FakeDriver([]), 'HarmonyOS': FakeDriver([])}
        factory = _fake_factory(drivers)
        svc = DeviceCommandService(repo=_repo_stub())
        with patch(FACTORY_TARGET, factory):
            result = svc.scan()
        assert result['success'] is True

    def test_scan_mock_fallback_returns_three_mock_devices(self):
        factory = _fake_factory({}, mock_mode=True)
        svc = DeviceCommandService(repo=_repo_stub())
        with patch(FACTORY_TARGET, factory):
            result = svc.scan()
        assert result['success'] is True
        assert [d['serial'] for d in result['data']] == [
            'mock-android-1', 'mock-ios-1', 'mock-harmony-1']

    def test_get_available_serials_resolves_by_system(self):
        drivers = {
            'Android': FakeDriver([{'serial': 'adb-1', 'model': 'A', 'system': 'Android'}]),
            'iOS': FakeDriver([{'serial': 'ios-1', 'model': 'I', 'system': 'iOS'}]),
            'HarmonyOS': FakeDriver([{'serial': 'hdc-1', 'model': 'H', 'system': 'HarmonyOS'}]),
        }
        factory = _fake_factory(drivers)
        svc = DeviceQueryService(repo=_repo_stub())
        with patch(FACTORY_TARGET, factory):
            result = svc.get_available_serials()
        assert result['success'] is True
        assert [d['serial'] for d in result['data']] == ['adb-1', 'ios-1', 'hdc-1']
        assert {call.args[0] for call in factory.get_driver_by_system.call_args_list} == set(PLATFORMS)
        factory.get_driver_for_device.assert_not_called()


class TestHealthCheckOnlineDecision:
    def _run(self, scan_devices, device=None):
        device = device or SimpleNamespace(
            id=7, name='D7', model='M', system='HarmonyOS', serial_number='sn-7',
            status='offline')
        drivers = {'HarmonyOS': FakeDriver(scan_devices)}
        factory = _fake_factory(drivers)
        repo = _repo_stub([{
            'id': device.id, 'name': device.name, 'model': device.model,
            'system': device.system, 'serial_number': device.serial_number,
            'status': device.status}])
        svc = DeviceCommandService(repo=repo)
        with patch(FACTORY_TARGET, factory), \
             patch('device_service.application.services.device_monitor_service.device_monitor_service') as monitor, \
             patch('device_service.application.commands.device_command_service.time.sleep'):
            result = svc.health_check()
        return result, repo.update_device_status

    def test_scanned_device_marked_online(self):
        # 修复前：此处 get_driver_for_device 缺 keywords 抛 ValueError → 设备被误标 offline
        result, update = self._run([{'serial': 'sn-7', 'system': 'HarmonyOS'}])
        assert result['success'] is True
        assert result['data'][0]['status'] == 'online'
        update.assert_called_once()
        assert update.call_args[0][1] == 'online'

    def test_unscanned_device_marked_offline(self):
        result, update = self._run([{'serial': 'other-sn', 'system': 'HarmonyOS'}])
        assert result['data'][0]['status'] == 'offline'
        assert update.call_args[0][1] == 'offline'


class TestCreateOnlineCheck:
    def test_registered_serial_matched_marks_online(self):
        drivers = {'HarmonyOS': FakeDriver([{'serial': 'mock-harmony-1', 'system': 'HarmonyOS'}])}
        factory = _fake_factory(drivers)
        repo = _repo_stub()
        repo.create_device.return_value = SimpleNamespace(
            id=11, serial_number='mock-harmony-1', system='HarmonyOS')
        svc = DeviceCommandService(repo=repo)
        with patch(FACTORY_TARGET, factory), \
             patch('device_service.application.commands.device_command_service.refresh_stats_cache'):
            result = svc.create({'name': 'D', 'system': 'HarmonyOS',
                                 'serial_number': 'mock-harmony-1'})
        assert result['success'] is True
        assert result['data'] == {'id': 11}
        factory.get_driver_by_system.assert_called_once_with('HarmonyOS')
        repo.update_device_status.assert_called_once()
        assert repo.update_device_status.call_args[0][:2] == (11, 'online')


class TestKeywordSemanticsUnchanged:
    def test_get_driver_for_device_without_keywords_raises(self):
        # INT-83 收紧语义不得被 INT-86 放松：无 keywords 仍拒绝
        from device_service.infrastructure.drivers.device_driver import device_driver_factory
        with pytest.raises(ValueError, match='设备必须提供明确的驱动 keywords 标识'):
            device_driver_factory.get_driver_for_device('Android')

    def test_get_driver_for_device_unknown_keywords_raises(self):
        from device_service.infrastructure.drivers.device_driver import device_driver_factory
        with pytest.raises(ValueError, match='未注册驱动 keywords'):
            device_driver_factory.get_driver_for_device('Android', keywords='no.such.keyword')

    def test_get_driver_by_system_unknown_system_returns_none(self):
        from device_service.infrastructure.drivers.device_driver import device_driver_factory
        assert device_driver_factory.get_driver_by_system('') is None
        assert device_driver_factory.get_driver_by_system('NoSuchSystem') is None
