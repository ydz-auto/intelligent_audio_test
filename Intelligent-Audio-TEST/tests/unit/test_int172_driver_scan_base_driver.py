# -*- coding: utf-8 -*-
"""INT-172 验收：DriverScan 扫描语义一律走基础驱动。

背景：device_runtime_servicers.DriverScan 原实现带 keywords 时走
get_driver_for_device（keywords 专用驱动解析），与"扫描/在线检测只用
基础驱动"的口径不符；且调用方默认 keywords='' 时直接抛 ValueError
导致扫描固定失败（INT-172 审计）。对齐后：
- system 有值 → get_driver_by_system 基础驱动，request.keywords 保留但忽略
- system 为空 → factory.scan_devices() 扫描所有基础驱动
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer

FACTORY_TARGET = 'device_service.infrastructure.drivers.device_driver.device_driver_factory'


class FakeBaseDriver:
    def __init__(self, devices=None):
        self._devices = devices or []

    def scan(self):
        return list(self._devices)


def _request(system='', keywords=''):
    return SimpleNamespace(system=system, keywords=keywords)


class TestDriverScanUsesBaseDriver:
    def test_scan_with_system_ignores_keywords(self):
        # 有 keywords 也必须走基础驱动，不再解析 keywords 专用驱动
        factory = MagicMock()
        factory.get_driver_by_system.return_value = FakeBaseDriver(
            [{'serial': 'adb-1', 'model': 'A', 'system': 'Android'}])
        servicer = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = servicer.DriverScan(_request('Android', keywords='plaud'))
        assert resp.success is True
        assert [d['serial'] for d in json.loads(resp.data)] == ['adb-1']
        factory.get_driver_by_system.assert_called_once_with('Android')
        factory.get_driver_for_device.assert_not_called()

    def test_scan_without_keywords_and_system_resolves_base_driver(self):
        # 修复前：system 有值但 keywords='' → get_driver_for_device 抛 ValueError → 扫描固定失败
        factory = MagicMock()
        factory.get_driver_by_system.return_value = FakeBaseDriver(
            [{'serial': 'hdc-1', 'model': 'H', 'system': 'HarmonyOS'}])
        servicer = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = servicer.DriverScan(_request('HarmonyOS', keywords=''))
        assert resp.success is True
        assert [d['serial'] for d in json.loads(resp.data)] == ['hdc-1']
        factory.get_driver_for_device.assert_not_called()

    def test_scan_without_system_scans_all_base_drivers(self):
        factory = MagicMock()
        factory.scan_devices.return_value = [
            {'serial': 'adb-1', 'system': 'Android'},
            {'serial': 'hdc-1', 'system': 'HarmonyOS'},
        ]
        servicer = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = servicer.DriverScan(_request('', keywords=''))
        assert resp.success is True
        assert len(json.loads(resp.data)) == 2
        factory.scan_devices.assert_called_once()
        factory.get_driver_for_device.assert_not_called()

    def test_scan_system_without_base_driver_returns_empty(self):
        factory = MagicMock()
        factory.get_driver_by_system.return_value = None
        servicer = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = servicer.DriverScan(_request('iOS', keywords=''))
        assert resp.success is True
        assert json.loads(resp.data) == []

    def test_scan_error_reports_failure(self):
        factory = MagicMock()
        factory.get_driver_by_system.side_effect = RuntimeError('adb crashed')
        servicer = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = servicer.DriverScan(_request('Android', keywords=''))
        assert resp.success is False
