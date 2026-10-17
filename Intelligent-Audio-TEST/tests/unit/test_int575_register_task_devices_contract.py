# -*- coding: utf-8 -*-
"""INT-575 验收：e2e register_task_devices 显式 action=register，device_service 只登记不解析驱动。

背景：INT-321 全流程实机走查 A 段发现——e2e 首次 CreateDriver（register_task_devices）
发送的 device_config 缺 system 字段且无 action，device_service 按默认 initialize
分支解析驱动时 DeviceSystem.normalize(None) 抛「设备系统 system 不能为空」，
CreateDriver 返回 success=False（被 register_task_devices 静默吞掉，每任务浪费
~12s + 误导性错误日志）；随后 initialize_devices 带显式 system 重试才成功。

根因：register_task_devices serializable_info 白名单漏 system（及 keywords），
且无 action 使 device_service 落入默认 initialize 分支。

修复：e2e register_task_devices 显式携带 action='register' 并补齐 system/keywords
元数据；device_service CreateDriver 新增 register 分支——仅登记 SNS（供停止清理），
不解析/初始化驱动。避免「补 system 后首次 CreateDriver 顺带真初始化首个设备、
initialize_devices 再次真初始化」的双重初始化。
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer
from e2e_test_service.infrastructure.acl.device_acl_repository_impl import DeviceAclRepositoryImpl

FACTORY_TARGET = 'device_service.infrastructure.drivers.device_driver.device_driver_factory'

SN = '5SM0125613000197'


def _req(cfg):
    return SimpleNamespace(device_config=json.dumps(cfg), task_id='500')


# ==================== 1. e2e register_task_devices 序列化契约 ====================

class TestE2eRegisterTaskDevicesPayload:
    def _stub(self):
        stub = MagicMock()
        stub.CreateDriver.return_value = SimpleNamespace(success=True, message='ok')
        return stub

    def test_payload_carries_action_register_and_system_keywords(self):
        # INT-575 根因：白名单漏 system/keywords 且无 action。修复后二者都要有，
        # 且显式 action=register 使 device_service 只登记不解析驱动。
        stub = self._stub()
        info = {
            'device_id': 1, 'device_sn': SN, 'device_name': 'pura90小艺',
            'system': 'HarmonyOS', 'keywords': 'harmony.xiaoyi_livechat.v1',
            'needs_prompt_audio': False, 'prompt_audio_path': None, 'prompt_audio_name': None,
        }
        with patch('shared.clients.grpc_clients.get_device_service_stub', return_value=stub):
            ok = DeviceAclRepositoryImpl().register_task_devices('500', [info])
        assert ok is True
        req = stub.CreateDriver.call_args.args[0]
        assert req.task_id == '500'
        payload = json.loads(req.device_config)
        assert payload[0]['action'] == 'register'
        assert payload[0]['system'] == 'HarmonyOS'
        assert payload[0]['keywords'] == 'harmony.xiaoyi_livechat.v1'
        assert payload[0]['device_sn'] == SN
        # 与 get_device_info 组装字段对齐（e2e_device_manager.py:49-55）
        assert set(payload[0]) == {
            'action', 'device_id', 'device_sn', 'device_name', 'system', 'keywords',
            'needs_prompt_audio', 'prompt_audio_path', 'prompt_audio_name',
        }

    def test_grpc_failure_returns_false(self):
        stub = self._stub()
        stub.CreateDriver.return_value = SimpleNamespace(success=False, message='boom')
        with patch('shared.clients.grpc_clients.get_device_service_stub', return_value=stub):
            assert DeviceAclRepositoryImpl().register_task_devices('500', [{'device_sn': SN}]) is False


# ==================== 2. device_service CreateDriver register 分支 ====================

class TestCreateDriverRegisterAction:
    def test_register_records_sns_without_resolving_driver(self):
        # 回归缺陷现象：list 无 action 曾默认 initialize，system=None 解析失败报
        # 「设备系统 system 不能为空」。显式 register 必须零解析、零初始化即成功。
        factory = MagicMock()
        payload = [{'action': 'register', 'device_sn': SN, 'system': 'HarmonyOS',
                    'keywords': 'harmony.xiaoyi_livechat.v1'}]
        s = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = s.CreateDriver(_req(payload))
        assert resp.success is True
        factory.register_task_devices.assert_called_once_with('500', payload)
        factory.get_driver_for_device.assert_not_called()
        factory.get_driver_by_sn.assert_not_called()
        assert json.loads(resp.data)['registered'] == 1

    def test_register_dict_form_with_device_info_list(self):
        # 兼容 dict 形态（含 device_info_list），与 list 形态行为一致
        factory = MagicMock()
        cfg = {'action': 'register', 'device_info_list': [{'device_sn': SN}]}
        s = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = s.CreateDriver(_req(cfg))
        assert resp.success is True
        factory.register_task_devices.assert_called_once_with('500', [{'device_sn': SN}])
        assert json.loads(resp.data)['registered'] == 1

    def test_register_empty_list_returns_success(self):
        factory = MagicMock()
        s = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = s.CreateDriver(_req({'action': 'register', 'device_info_list': []}))
        assert resp.success is True
        factory.register_task_devices.assert_not_called()

    def test_register_never_initializes_driver(self):
        # 即使 system/keywords 已注册可用，register 分支也不得触发驱动初始化
        factory = MagicMock()
        driver = MagicMock()
        factory.get_driver_for_device.return_value = driver
        payload = [{'action': 'register', 'device_sn': SN, 'system': 'HarmonyOS',
                    'keywords': 'harmony.xiaoyi_livechat.v1'}]
        s = DeviceServiceServicer()
        with patch(FACTORY_TARGET, factory):
            resp = s.CreateDriver(_req(payload))
        assert resp.success is True
        driver.initialize.assert_not_called()
        factory.get_driver_for_device.assert_not_called()
