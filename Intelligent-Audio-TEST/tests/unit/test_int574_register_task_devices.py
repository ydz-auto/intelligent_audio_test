# -*- coding: utf-8 -*-
"""INT-574 验收：e2e 首次 CreateDriver（register_task_devices）缺 system 字段缺陷修复。

背景：register_task_devices 以 list 格式调用 CreateDriver，但构造的
serializable_info 缺 action/system/keywords，device_service 对 list 格式
缺省 action='initialize' → 进入 initialize 分支调用
get_driver_for_device(system=None) → DeviceSystem.normalize(None) 抛
「设备系统 system 不能为空」→ 首次 CreateDriver 必然失败（~12s 空耗 + 日志噪音）。

修复方案（语义正确）：
- e2e ACL register_task_devices 显式携带 action='register' 及 system/keywords
- device_service servicer 新增 action='register' 分支：仅 factory.register_task_devices，
  不做驱动解析/initialize
- list 格式缺省 action 收紧为 register，消除「list 缺省 initialize」隐式语义

覆盖：
- e2e ACL register_task_devices 构造的 device_config 含 action/system/keywords 断言
- servicer register 分支行为：仅登记、不驱动解析、不 initialize
- list 格式无 action 缺省 register（回归：不再报「设备系统 system 不能为空」）
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from e2e_test_service.infrastructure.acl.device_acl_repository_impl import (
    DeviceAclRepositoryImpl,
)
from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer

SN = '5SM0125613000197'
FACTORY_TARGET = 'device_service.infrastructure.drivers.device_driver.device_driver_factory'


def _req(cfg):
    return SimpleNamespace(device_config=json.dumps(cfg), task_id='500')


def _device_info(**overrides):
    info = {
        'device_id': 11,
        'device_sn': SN,
        'device_name': 'pura90小艺',
        'system': 'HarmonyOS',
        'keywords': 'harmony.xiaoyi_livechat.v1',
        'needs_prompt_audio': True,
        'prompt_audio_path': '/tmp/prompt.wav',
        'prompt_audio_name': 'prompt.wav',
    }
    info.update(overrides)
    return info


# ==================== 1. e2e ACL register_task_devices 载荷 ====================

class TestRegisterTaskDevicesPayload:
    def _stub(self, success=True, message='ok'):
        stub = MagicMock()
        stub.CreateDriver.return_value = SimpleNamespace(
            success=success, message=message, data='')
        return stub

    def _call(self, stub):
        with patch('shared.clients.grpc_clients.get_device_service_stub', return_value=stub):
            return DeviceAclRepositoryImpl().register_task_devices(
                '500', [_device_info()])

    def test_payload_carries_action_register_and_system_keywords(self):
        stub = self._stub()
        ok = self._call(stub)
        assert ok is True
        req = stub.CreateDriver.call_args[0][0]
        payload = json.loads(req.device_config)
        assert isinstance(payload, list) and len(payload) == 1
        item = payload[0]
        # INT-574 核心断言：action + system/keywords 不再缺失
        assert item['action'] == 'register'
        assert item['system'] == 'HarmonyOS'
        assert item['keywords'] == 'harmony.xiaoyi_livechat.v1'
        # 设备元数据完整透传
        assert item['device_id'] == 11
        assert item['device_sn'] == SN
        assert item['device_name'] == 'pura90小艺'
        assert item['needs_prompt_audio'] is True

    def test_system_keywords_none_survive_serialization(self):
        stub = self._stub()
        with patch('shared.clients.grpc_clients.get_device_service_stub', return_value=stub):
            DeviceAclRepositoryImpl().register_task_devices(
                '500', [_device_info(system=None, keywords=None)])
        payload = json.loads(stub.CreateDriver.call_args[0][0].device_config)
        assert payload[0]['system'] is None
        assert payload[0]['keywords'] is None

    def test_failure_returns_false(self):
        stub = self._stub(success=False, message='boom')
        assert self._call(stub) is False


# ==================== 2. servicer register 分支行为 ====================

class TestServicerRegisterBranch:
    def _servicer(self, factory):
        s = DeviceServiceServicer()
        return s, patch(FACTORY_TARGET, factory)

    def test_register_only_registers_no_driver_resolution(self):
        factory = MagicMock()
        # 若误入 initialize 分支会调用 get_driver_for_device（缺 system 抛 ValueError）
        factory.get_driver_for_device.side_effect = ValueError('设备系统 system 不能为空')
        s, p = self._servicer(factory)
        payload = [{
            'action': 'register', 'device_sn': SN, 'device_name': 'd1',
            'system': 'HarmonyOS', 'keywords': 'x',
        }]
        with p:
            resp = s.CreateDriver(_req(payload))
        assert resp.success is True
        assert '驱动解析失败' not in resp.message and '不能为空' not in resp.message
        # 仅登记：factory.register_task_devices 收到完整设备列表
        factory.register_task_devices.assert_called_once_with('500', payload)
        factory.get_driver_for_device.assert_not_called()
        data = json.loads(resp.data)
        assert data['action'] == 'register'
        assert data['registered'] == 1

    def test_register_empty_list_still_succeeds(self):
        factory = MagicMock()
        s, p = self._servicer(factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'register', 'device_sn': None,
                'device_info_list': [], 'kwargs': {}}))
        assert resp.success is True
        factory.register_task_devices.assert_called_once_with('500', [])
        factory.get_driver_for_device.assert_not_called()


# ==================== 3. list 格式缺省 register（回归） ====================

class TestServicerListDefaultIsRegister:
    def test_list_without_action_registers_not_initializes(self):
        """INT-574 根因回归：list 缺 action 不再缺省 initialize → 不再报 system 不能为空"""
        factory = MagicMock()
        factory.get_driver_for_device.side_effect = ValueError('设备系统 system 不能为空')
        s, p = DeviceServiceServicer(), patch(FACTORY_TARGET, factory)
        payload = [{
            'device_sn': SN, 'device_name': 'd1',
            'system': 'HarmonyOS', 'keywords': 'x',
        }]
        with p:
            resp = s.CreateDriver(_req(payload))
        assert resp.success is True
        assert '驱动解析失败' not in resp.message and '不能为空' not in resp.message
        factory.register_task_devices.assert_called_once_with('500', payload)
        factory.get_driver_for_device.assert_not_called()

    def test_explicit_initialize_dict_unchanged(self):
        """dict 格式缺省 initialize 语义不变，list 缺省收紧不影响显式 initialize"""
        factory = MagicMock()
        driver = MagicMock()
        driver.initialize.return_value = True
        factory.get_driver_for_device.return_value = driver
        s, p = DeviceServiceServicer(), patch(FACTORY_TARGET, factory)
        with p:
            resp = s.CreateDriver(_req({
                'action': 'initialize', 'system': 'HarmonyOS', 'keywords': 'x',
                'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is True
        factory.get_driver_for_device.assert_called_once()
        # 空 device_info_list 不触发登记（initialize 分支原语义不变）
        factory.register_task_devices.assert_not_called()
