# -*- coding: utf-8 -*-
"""INT-164 专项：离线设备唤醒测试返回业务性失败（方案1：发送前查设备在线状态）。

覆盖：
- 探测离线：返回 success=False「设备离线，无法发送唤醒指令」，唤醒指令不发送
- 探测在线：保持 fire-and-forget 成功文案，指令照发
- 探测异常：降级照发（不因在线状态读取故障阻塞唤醒主流程）
- 探测超时：降级照发
- 无驱动 / 无可探测标识：降级照发
- 设备不存在：404 行为不变
"""
import os
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from device_service.application.commands.device_command_service import DeviceCommandService

FACTORY_TARGET = 'device_service.infrastructure.drivers.driver_factory.device_driver_factory'
SVC_MODULE = 'device_service.application.commands.device_command_service'


def make_device(**overrides):
    device = SimpleNamespace(
        id=1, name='测试设备', system='Android', keywords='android_base',
        serial_number='SN-001', ip='192.168.1.10', status='online',
    )
    for key, value in overrides.items():
        setattr(device, key, value)
    return device


class FakeRepo:
    def __init__(self, device):
        self._device = device

    def get_device(self, device_id):
        return self._device


def make_factory(scan_result=None, scan_error=None, scan_delay=0.0, scan_driver_exists=True):
    """构造设备驱动工厂替身：scan_driver 负责在线探测，wake_driver 承接唤醒指令。"""
    factory = MagicMock()
    scan_driver = MagicMock()
    if scan_driver_exists:
        def _scan():
            if scan_delay:
                time.sleep(scan_delay)
            if scan_error:
                raise scan_error
            return scan_result or []
        scan_driver.scan.side_effect = _scan
    factory.get_driver_by_system.return_value = scan_driver if scan_driver_exists else None
    wake_driver = MagicMock()
    factory.get_driver_for_device.return_value = wake_driver
    return factory, scan_driver, wake_driver


def run_test(factory, device=None):
    svc = DeviceCommandService(repo=FakeRepo(device if device is not None else make_device()))
    with patch(FACTORY_TARGET, factory), \
         patch(f'{SVC_MODULE}.log_not_emit'):
        return svc.test(1)


def test_offline_device_rejected_without_sending_wakeup():
    factory, scan_driver, wake_driver = make_factory(scan_result=[{'serial': 'SN-OTHER'}])
    result = run_test(factory)
    assert result['success'] is False
    assert result['message'] == '设备离线，无法发送唤醒指令'
    assert result['code'] == 400
    assert result['data'] == {'id': 1, 'status': 'online'}
    wake_driver.unlock.assert_not_called()


def test_online_device_keeps_fire_and_forget_success():
    factory, scan_driver, wake_driver = make_factory(
        scan_result=[{'serial': 'SN-002'}, {'serial': 'SN-001'}])
    result = run_test(factory)
    assert result['success'] is True
    assert result['message'] == '唤醒指令已发送，正在测试'
    assert result['code'] == 200
    wake_driver.unlock.assert_called_once_with('SN-001')


def test_probe_error_degrades_to_fire_and_forget():
    factory, scan_driver, wake_driver = make_factory(scan_error=RuntimeError('adb not found'))
    result = run_test(factory)
    assert result['success'] is True
    assert result['message'] == '唤醒指令已发送，正在测试'
    wake_driver.unlock.assert_called_once_with('SN-001')


def test_probe_timeout_degrades_to_fire_and_forget():
    factory, scan_driver, wake_driver = make_factory(
        scan_result=[{'serial': 'SN-001'}], scan_delay=1.0)
    svc = DeviceCommandService(repo=FakeRepo(make_device()))
    with patch(FACTORY_TARGET, factory), \
         patch(f'{SVC_MODULE}.log_not_emit'), \
         patch(f'{SVC_MODULE}._WAKEUP_ONLINE_PROBE_TIMEOUT_SECONDS', 0.2):
        result = svc.test(1)
    assert result['success'] is True
    assert result['message'] == '唤醒指令已发送，正在测试'
    wake_driver.unlock.assert_called_once_with('SN-001')


def test_missing_driver_degrades_to_fire_and_forget():
    factory, scan_driver, wake_driver = make_factory(scan_driver_exists=False)
    result = run_test(factory)
    assert result['success'] is True
    wake_driver.unlock.assert_called_once_with('SN-001')


def test_device_without_identifier_degrades_without_scan():
    factory, scan_driver, wake_driver = make_factory(scan_result=[{'serial': 'SN-001'}])
    device = make_device(serial_number='', ip=None)
    result = run_test(factory, device)
    assert result['success'] is True
    scan_driver.scan.assert_not_called()
    # 既有行为：唤醒指令目标为 device.serial_number or device.ip，此处两者皆空
    wake_driver.unlock.assert_called_once_with(None)


def test_missing_device_returns_404():
    factory, _, _ = make_factory(scan_result=[{'serial': 'SN-001'}])
    svc = DeviceCommandService(repo=FakeRepo(None))
    with patch(FACTORY_TARGET, factory), \
         patch(f'{SVC_MODULE}.log_not_emit'):
        result = svc.test(999)
    assert result == {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}
