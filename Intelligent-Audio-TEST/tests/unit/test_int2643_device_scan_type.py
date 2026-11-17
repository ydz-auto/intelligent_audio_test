# -*- coding: utf-8 -*-
"""INT-2643 回归：设备扫描结果的 type 固定为 physical（三值枚举口径）。

背景：扫描入口此前把每行 `type` 写死 'phone'，与 device_type 三值枚举
（physical / http_api / websocket_api）不一致，扫描→添加新建的设备落库即
`phone`，前端只能按「未知」展示。扫描源只产出实体设备，口径应恒为
`DeviceType.PHYSICAL`。

覆盖：
- 各系统驱动返回的真实行 → type == 'physical'
- 无真机 + mock 开启的回退行 → type == 'physical'
- 驱动行自带 type（脏值）也被统一覆写为 'physical'
- 值落在 DeviceType 枚举内（不是 'phone'/'tablet' 旧值）
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock, patch

import pytest

from device_service.application.commands.device_command_service import DeviceCommandService
from shared.models.common_enums import DeviceType

FACTORY_TARGET = 'device_service.infrastructure.drivers.driver_factory.device_driver_factory'


class FakeDriver:
    def __init__(self, devices=None):
        self._mock_mode = False
        self._devices = devices or []

    def scan(self):
        return [dict(d) for d in self._devices]


def _scan_with(drivers_by_system=None, mock_mode=False, scan_devices=None):
    factory = MagicMock()
    if scan_devices is not None:
        factory.get_driver_by_system.side_effect = (
            lambda system: FakeDriver(scan_devices) if system == 'Android' else FakeDriver([]))
    else:
        factory.get_driver_by_system.side_effect = (
            lambda system: (drivers_by_system or {}).get(system))
    factory.get_mock_mode.return_value = mock_mode
    repo = MagicMock()
    repo.get_all_device_serials.return_value = []
    svc = DeviceCommandService(repo=repo)
    with patch(FACTORY_TARGET, factory):
        return svc.scan()


class TestScanTypeIsPhysical:
    def test_driver_rows_type_physical(self):
        result = _scan_with(scan_devices=[
            {'serial': 'sn-android-1', 'model': 'Mi 14', 'system': 'Android', 'status': 'online'},
        ])
        assert result['success'] is True
        assert [row['type'] for row in result['data']] == ['physical']

    def test_all_systems_type_physical(self):
        result = _scan_with(drivers_by_system={
            'Android': FakeDriver([
                {'serial': 'a-1', 'model': 'M', 'system': 'Android', 'status': 'online'}]),
            'iOS': FakeDriver([
                {'serial': 'i-1', 'model': 'P', 'system': 'iOS', 'status': 'online'}]),
            'HarmonyOS': FakeDriver([
                {'serial': 'h-1', 'model': 'H', 'system': 'HarmonyOS', 'status': 'online'}]),
        })
        assert len(result['data']) == 3
        assert {row['type'] for row in result['data']} == {'physical'}

    def test_mock_fallback_rows_type_physical(self):
        result = _scan_with(drivers_by_system={}, mock_mode=True)
        assert len(result['data']) == 3
        assert {row['type'] for row in result['data']} == {'physical'}

    def test_dirty_driver_type_overwritten(self):
        # 驱动行自带 type（历史脏值/未来扩展）不能穿透到登记表单
        result = _scan_with(scan_devices=[
            {'serial': 'sn-1', 'model': 'M', 'system': 'Android',
             'status': 'online', 'type': 'phone'},
        ])
        assert result['data'][0]['type'] == 'physical'

    def test_type_is_enum_member_not_legacy_value(self):
        result = _scan_with(scan_devices=[
            {'serial': 'sn-1', 'model': 'M', 'system': 'Android', 'status': 'online'},
        ])
        value = result['data'][0]['type']
        assert value in {member.value for member in DeviceType}
        assert value not in {'phone', 'tablet'}

    @pytest.mark.parametrize('mock_mode', [False, True])
    def test_scan_never_emits_phone(self, mock_mode):
        result = _scan_with(
            drivers_by_system={} if mock_mode else {
                'Android': FakeDriver([
                    {'serial': 'sn-1', 'model': 'M', 'system': 'Android', 'status': 'online'}])},
            mock_mode=mock_mode)
        assert all(row['type'] != 'phone' for row in result['data'])
