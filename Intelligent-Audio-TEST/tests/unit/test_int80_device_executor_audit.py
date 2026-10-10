# -*- coding: utf-8 -*-
"""INT-80 专项：设备操作执行器（adb/hdc 命令构造）+ 网关设备审计。

覆盖：
- DeviceOperationExecutor：mock 模式模拟成功、Android/HarmonyOS 命令构造、
  参数校验（install_app 缺 file_path / uninstall_app 缺 package_name）、
  命令失败抛 DeviceOperationError、未知系统拒绝、USB 设备不可远程断开
- write_device_audit：category='device' 落库（log_not_emit 捕获）、
  operator 注入、旁路（log 异常不影响业务）
"""
import os
import json

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from device_service.infrastructure.device_operations import (
    DeviceOperationExecutor,
    DeviceOperationError,
)
from api_gateway.application.services.device.device_audit import write_device_audit


def _device(system='Android', serial='sn-1', ip='', connection_type='usb'):
    return SimpleNamespace(id=1, name='D1', system=system, serial_number=serial,
                           ip=ip, connection_type=connection_type)


@pytest.fixture
def executor():
    runner = MagicMock(return_value=(0, 'done'))
    return DeviceOperationExecutor(command_runner=runner), runner


class TestExecutorMockMode:
    def test_mock_mode_simulates_success(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = True
            result = exec_.execute(_device(), 'reboot')
        assert result['mock'] is True
        assert 'reboot' in result['output']
        runner.assert_not_called()


class TestExecutorAndroid:
    def test_reboot_command(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            exec_.execute(_device(), 'reboot')
        cmd = runner.call_args[0][0]
        assert cmd[:4] == ['adb', '-s', 'sn-1', 'shell'] and 'reboot' in cmd

    def test_shutdown_command(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            exec_.execute(_device(), 'shutdown')
        assert runner.call_args[0][0][-2:] == ['reboot', '-p']

    def test_connect_usb_wakes_screen(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            exec_.execute(_device(), 'connect')
        assert 'KEYCODE_WAKEUP' in runner.call_args[0][0]

    def test_connect_remote_uses_adb_connect(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            exec_.execute(_device(ip='192.168.1.8', connection_type='remote'), 'connect')
        assert runner.call_args[0][0] == ['adb', 'connect', '192.168.1.8']

    def test_disconnect_usb_rejected(self, executor):
        exec_, _ = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            with pytest.raises(DeviceOperationError):
                exec_.execute(_device(), 'disconnect')

    def test_install_app_requires_file_path(self, executor):
        exec_, _ = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            with pytest.raises(DeviceOperationError):
                exec_.execute(_device(), 'install_app')
            exec_.execute(_device(), 'install_app', {'file_path': '/data/app.apk'})
        assert '/data/app.apk' in executor[1].call_args[0][0]

    def test_uninstall_app_requires_package(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            with pytest.raises(DeviceOperationError):
                exec_.execute(_device(), 'uninstall_app')
            exec_.execute(_device(), 'uninstall_app', {'package_name': 'com.example.app'})
        assert runner.call_args[0][0][-1] == 'com.example.app'

    def test_command_failure_raises(self, executor):
        exec_, runner = executor
        runner.return_value = (1, 'error: device not found')
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            with pytest.raises(DeviceOperationError):
                exec_.execute(_device(), 'reboot')


class TestExecutorHarmony:
    def test_reboot_command_hdc(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            exec_.execute(_device(system='HarmonyOS'), 'reboot')
        assert runner.call_args[0][0][:2] == ['hdc', '-t']

    def test_uninstall_uses_bm(self, executor):
        exec_, runner = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            exec_.execute(_device(system='HarmonyOS'), 'uninstall_app', {'package_name': 'com.x.y'})
        assert 'bm' in runner.call_args[0][0]

    def test_shutdown_unsupported(self, executor):
        exec_, _ = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            with pytest.raises(DeviceOperationError):
                exec_.execute(_device(system='HarmonyOS'), 'shutdown')

    def test_unknown_system_rejected(self, executor):
        exec_, _ = executor
        with patch('device_service.infrastructure.drivers.device_driver.device_driver_factory') as factory:
            factory.get_mock_mode.return_value = False
            with pytest.raises(DeviceOperationError):
                exec_.execute(_device(system='Symbian'), 'reboot')


class TestDeviceAudit:
    def test_audit_written_with_device_category(self):
        from shared.models.common_enums import AuditEvent
        captured = {}

        def fake_log_not_emit(level, module, content, category=None, source=None, **kwargs):
            captured.update(level=level, module=module, content=content,
                            category=category, source=source)

        with patch('shared.utils.log_handler.log_not_emit', side_effect=fake_log_not_emit):
            write_device_audit(AuditEvent.DEVICE_GROUP_CREATED, 'device_group',
                               {'name': '产线A', 'group_id': 'g1'})
        assert captured['category'] == 'device'
        payload = json.loads(captured['content'])
        assert payload['event'] == 'DEVICE_GROUP_CREATED'
        assert payload['name'] == '产线A'
        assert 'operator' in payload

    def test_audit_bypasses_on_log_failure(self):
        from shared.models.common_enums import AuditEvent
        with patch('shared.utils.log_handler.log_not_emit', side_effect=RuntimeError('db down')):
            # 不抛异常：审计为旁路记录
            write_device_audit(AuditEvent.DEVICE_CONTROL_EXECUTED, 'device_control',
                               {'device_id': 1, 'operation': 'reboot'})
