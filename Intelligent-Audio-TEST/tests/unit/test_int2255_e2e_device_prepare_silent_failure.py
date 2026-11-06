# -*- coding: utf-8 -*-
"""INT-2255 验收：e2e 设备准备静默失败修复。

背景（设备域走查 2026-10-31 问题 1、2）：设备实际未就绪时用例仍继续执行，
最终产出空结果或给出误导性错误。

行为契约：
1. 并行初始化 future 超时必须作为该设备的初始化失败参与汇总 →
   ``initialize_devices`` 抛 ``RuntimeError``，错误含该设备的名称/SN/系统/关键字；
   且 future 等待严格大于 gRPC deadline（避免两者同时到期丢失 RPC 结果）。
2. ``get_devices_by_ids`` 单台 ``GetDevice`` 异常只丢该台并累计 error，
   已取到的设备不再连坐丢失。
3. ``get_device_info`` 校验取回数量，取不全即返回失败（而非空列表成功），
   写清缺失 device_id 并区分「查询失败」与「无数据」。
4. ``get_task_devices`` 查询失败抛 ``AclQueryError``，设备准备阶段转成可诊断
   失败，不再误报「没有可用的测试设备」。

全部离线可跑，不依赖真机。
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from e2e_test_service.application.services.e2e_device_manager import (
    E2EDeviceManager,
    resolve_device_op_future_timeout,
)
from e2e_test_service.domain.dto import DeviceDTO, TaskDeviceDTO
from e2e_test_service.domain.repositories.acl_errors import AclQueryError
from e2e_test_service.domain.repositories.device_acl_repository import (
    DeviceQueryResult,
)
from e2e_test_service.infrastructure.acl.device_acl_repository_impl import (
    DeviceAclRepositoryImpl,
)
from e2e_test_service.infrastructure.acl.task_data_acl_repository_impl import (
    TaskDataAclRepositoryImpl,
)
from shared.infrastructure.config import BaseConfig

SN = '5SM0125613000197'


# --------------------------------------------------------------------------- #
#  1. future 超时分层 + 超时落失败                                              #
# --------------------------------------------------------------------------- #

class TestFutureTimeoutLayering:

    def test_default_future_timeout_exceeds_grpc_deadline(self):
        assert (BaseConfig.E2E_DEVICE_OP_FUTURE_TIMEOUT_SECONDS
                > BaseConfig.GRPC_DEVICE_OP_DEADLINE_SECONDS)

    def test_helper_forces_margin_when_configured_equal(self, monkeypatch):
        # 环境变量可把两值配成相同；helper 必须补足余量，避免同时到期
        monkeypatch.setattr(BaseConfig, 'GRPC_DEVICE_OP_DEADLINE_SECONDS', 300, raising=False)
        monkeypatch.setattr(BaseConfig, 'E2E_DEVICE_OP_FUTURE_TIMEOUT_SECONDS', 300, raising=False)
        monkeypatch.setattr(BaseConfig, 'E2E_DEVICE_OP_FUTURE_TIMEOUT_MARGIN_SECONDS', 30, raising=False)
        assert resolve_device_op_future_timeout() == 330

    def test_helper_keeps_larger_configured_value(self, monkeypatch):
        monkeypatch.setattr(BaseConfig, 'GRPC_DEVICE_OP_DEADLINE_SECONDS', 100, raising=False)
        monkeypatch.setattr(BaseConfig, 'E2E_DEVICE_OP_FUTURE_TIMEOUT_SECONDS', 500, raising=False)
        monkeypatch.setattr(BaseConfig, 'E2E_DEVICE_OP_FUTURE_TIMEOUT_MARGIN_SECONDS', 30, raising=False)
        assert resolve_device_op_future_timeout() == 500


def _manager(initialize_driver, pool_workers=2):
    mgr = E2EDeviceManager.__new__(E2EDeviceManager)
    mgr._executor = SimpleNamespace(
        _log=MagicMock(),
        execution_engine=SimpleNamespace(
            device_control_pool=ThreadPoolExecutor(max_workers=pool_workers)),
    )
    mgr._device_repo = SimpleNamespace(initialize_driver=initialize_driver)
    return mgr


class TestInitializeTimeoutRecordedAsFailure:

    @pytest.fixture(autouse=True)
    def _fast_timeouts(self, monkeypatch):
        # future 0.2s > deadline 0.1s，保持修复后的分层关系
        monkeypatch.setattr(BaseConfig, 'GRPC_DEVICE_OP_DEADLINE_SECONDS', 0.1, raising=False)
        monkeypatch.setattr(BaseConfig, 'E2E_DEVICE_OP_FUTURE_TIMEOUT_SECONDS', 0.2, raising=False)
        monkeypatch.setattr(BaseConfig, 'E2E_DEVICE_OP_FUTURE_TIMEOUT_MARGIN_SECONDS', 0.01, raising=False)

    def test_hung_initialize_raises_with_device_identity(self):
        """mock initialize_driver 挂起 → 抛 RuntimeError 且错误含该设备"""
        def _hang(task_id, config):
            time.sleep(1.0)
            return {}

        mgr = _manager(_hang)
        infos = [{
            'device_name': 'pura90小艺', 'device_sn': SN, 'system': 'HarmonyOS',
            'keywords': 'harmony.xiaoyi_livechat.v1',
        }]
        with pytest.raises(RuntimeError) as exc_info:
            mgr.initialize_devices(infos, task_id=9, test_case_id='c1')
        message = str(exc_info.value)
        assert '设备初始化失败' in message
        assert '超时' in message
        # 设备标识齐备：名称 + SN + 系统 + 关键字
        assert 'pura90小艺' in message
        assert SN in message
        assert 'HarmonyOS' in message
        assert 'harmony.xiaoyi_livechat.v1' in message

    def test_partial_timeout_only_fails_hung_device(self):
        """一台成功、一台挂起：整体失败且错误只指向挂起的那台"""
        def _init(task_id, config):
            sn = config[0].get('device_sn')
            if sn == 'sn_hung':
                time.sleep(1.0)
            return {}

        mgr = _manager(_init)
        infos = [
            {'device_name': 'd_ok', 'device_sn': 'sn_ok', 'system': 'HarmonyOS',
             'keywords': 'harmony.base.v1'},
            {'device_name': 'd_hung', 'device_sn': 'sn_hung', 'system': 'HarmonyOS',
             'keywords': 'harmony.base.v1'},
        ]
        with pytest.raises(RuntimeError) as exc_info:
            mgr.initialize_devices(infos, task_id=9, test_case_id='c1')
        message = str(exc_info.value)
        assert 'd_hung' in message and 'sn_hung' in message
        assert 'd_ok' not in message

    def test_timeout_does_not_block_other_results(self):
        """超时不得掩盖同批其他设备的真实失败原因"""
        def _init(task_id, config):
            sn = config[0].get('device_sn')
            if sn == 'sn_hung':
                time.sleep(1.0)
                return {}
            raise RuntimeError(f'驱动解析失败 {sn}')

        mgr = _manager(_init)
        infos = [
            {'device_name': 'd_hung', 'device_sn': 'sn_hung', 'system': 'HarmonyOS',
             'keywords': 'k1'},
            {'device_name': 'd_bad', 'device_sn': 'sn_bad', 'system': 'HarmonyOS',
             'keywords': 'k2'},
        ]
        with pytest.raises(RuntimeError) as exc_info:
            mgr.initialize_devices(infos, task_id=9, test_case_id='c1')
        message = str(exc_info.value)
        assert '超时' in message and 'sn_hung' in message
        assert '驱动解析失败 sn_bad' in message


# --------------------------------------------------------------------------- #
#  2. ACL：单台失败只丢该台，区分查询失败与无数据                                #
# --------------------------------------------------------------------------- #

def _device_resp(device_id, name='设备'):
    return SimpleNamespace(
        success=True,
        data=json.dumps({'id': device_id, 'name': f'{name}{device_id}',
                         'system': 'HarmonyOS', 'keywords': 'harmony.base.v1',
                         'serial_number': f'sn{device_id}', 'lab_id': 1}))


class TestGetDevicesByIdsPartialFailure:

    def test_one_device_error_keeps_others(self):
        calls = []

        def _get_device(req):
            calls.append(req.device_id)
            if req.device_id == 2:
                raise RuntimeError('grpc unavailable')
            return _device_resp(req.device_id)

        stub = SimpleNamespace(GetDevice=_get_device)
        with patch('shared.clients.grpc_clients.get_device_config_service_stub',
                   return_value=stub):
            result = DeviceAclRepositoryImpl().get_devices_by_ids([1, 2, 3])

        assert [dev.id for dev in result.devices] == [1, 3]
        assert calls == [1, 2, 3]
        assert result.error_map() == {2: 'GetDevice 调用异常: grpc unavailable'}

    def test_server_false_recorded_as_error(self):
        def _get_device(req):
            if req.device_id == 2:
                return SimpleNamespace(success=False, message='not found')
            return _device_resp(req.device_id)

        stub = SimpleNamespace(GetDevice=_get_device)
        with patch('shared.clients.grpc_clients.get_device_config_service_stub',
                   return_value=stub):
            result = DeviceAclRepositoryImpl().get_devices_by_ids([1, 2])

        assert [dev.id for dev in result.devices] == [1]
        assert result.error_map() == {2: 'not found'}

    def test_stub_creation_failure_marks_every_id(self):
        with patch('shared.clients.grpc_clients.get_device_config_service_stub',
                   side_effect=RuntimeError('connect failed')):
            result = DeviceAclRepositoryImpl().get_devices_by_ids([1, 2])

        assert result.devices == []
        assert set(result.error_map()) == {1, 2}
        assert 'connect failed' in result.error_map()[1]


# --------------------------------------------------------------------------- #
#  3. get_device_info 数量校验：失败而非空列表                                   #
# --------------------------------------------------------------------------- #

def _info_manager(devices=None, errors=None, relations=None):
    mgr = E2EDeviceManager.__new__(E2EDeviceManager)
    mgr._task_data_repo = SimpleNamespace(
        get_task_devices=MagicMock(return_value=relations if relations is not None else [
            TaskDeviceDTO(task_id=9, device_id=1),
            TaskDeviceDTO(task_id=9, device_id=2),
        ]))
    mgr._device_repo = SimpleNamespace(get_devices_by_ids=MagicMock(
        return_value=DeviceQueryResult(devices=devices or [], errors=errors or [])))
    return mgr


class TestGetDeviceInfoCountValidation:

    def test_one_device_get_failure_returns_failure_not_empty_list(self):
        """mock 一台 GetDevice 抛异常 → get_device_info 返回失败而非空列表"""
        mgr = _info_manager(
            devices=[DeviceDTO(id=1, name='设备1', system='HarmonyOS',
                               keywords='harmony.base.v1', serial_number='sn1')],
            errors=[{'device_id': 2, 'error': 'GetDevice 调用异常: grpc unavailable'}],
        )
        result = mgr.get_device_info('9', {})
        assert result['success'] is False
        assert 'device_id=2' in result['error']
        assert '查询失败' in result['error']
        assert 'grpc unavailable' in result['error']
        assert 'data' not in result

    def test_missing_without_error_reported_as_no_data(self):
        mgr = _info_manager(
            devices=[DeviceDTO(id=1, name='设备1')], errors=[],
        )
        result = mgr.get_device_info('9', {})
        assert result['success'] is False
        assert 'device_id=2' in result['error']
        assert '无设备数据' in result['error']

    def test_all_devices_present_succeeds(self):
        mgr = _info_manager(devices=[
            DeviceDTO(id=1, name='设备1', system='HarmonyOS', keywords='k',
                      serial_number='sn1'),
            DeviceDTO(id=2, name='设备2', system='HarmonyOS', keywords='k',
                      serial_number='sn2'),
        ])
        result = mgr.get_device_info('9', {})
        assert result['success'] is True
        assert [item['device_id'] for item in result['data']['device_info_list']] == [1, 2]

    def test_real_acl_one_get_device_error_returns_failure(self):
        """端到端（ACL 真实实现 + stub）：一台 GetDevice 抛异常 → 返回失败"""
        def _get_device(req):
            if req.device_id == 2:
                raise RuntimeError('grpc unavailable')
            return _device_resp(req.device_id)

        mgr = E2EDeviceManager.__new__(E2EDeviceManager)
        mgr._task_data_repo = SimpleNamespace(get_task_devices=MagicMock(return_value=[
            TaskDeviceDTO(task_id=9, device_id=1),
            TaskDeviceDTO(task_id=9, device_id=2),
        ]))
        mgr._device_repo = DeviceAclRepositoryImpl()

        with patch('shared.clients.grpc_clients.get_device_config_service_stub',
                   return_value=SimpleNamespace(GetDevice=_get_device)):
            result = mgr.get_device_info('9', {})

        assert result['success'] is False
        assert 'device_id=2' in result['error']
        assert 'grpc unavailable' in result['error']
        # 设备 1 仍成功取到，不因设备 2 连坐丢失
        assert 'device_id=1' not in result['error']


class TestTaskDeviceQueryFailureIsNotNoData:

    def test_acl_query_error_becomes_failure(self):
        """任务设备关联查询失败不能被误报成「没有可用的测试设备」"""
        mgr = E2EDeviceManager.__new__(E2EDeviceManager)
        mgr._task_data_repo = SimpleNamespace(
            get_task_devices=MagicMock(side_effect=AclQueryError('GetTaskDevices 调用失败: grpc down')))
        mgr._device_repo = SimpleNamespace(get_devices_by_ids=MagicMock())

        result = mgr.get_device_info('9', {})
        assert result['success'] is False
        assert '任务设备关联查询失败' in result['error']
        assert 'grpc down' in result['error']
        assert '没有可用的测试设备' not in result['error']
        mgr._device_repo.get_devices_by_ids.assert_not_called()

    def test_acl_get_task_devices_raises_on_grpc_error(self):
        stub = SimpleNamespace(GetTaskDevices=MagicMock(side_effect=RuntimeError('boom')))
        with patch('shared.clients.grpc_clients.get_task_data_service_stub',
                   return_value=stub):
            with pytest.raises(AclQueryError, match='boom'):
                TaskDataAclRepositoryImpl().get_task_devices('9')

    def test_acl_get_task_devices_raises_on_server_false(self):
        stub = SimpleNamespace(GetTaskDevices=MagicMock(
            return_value=SimpleNamespace(success=False, message='task not found')))
        with patch('shared.clients.grpc_clients.get_task_data_service_stub',
                   return_value=stub):
            with pytest.raises(AclQueryError, match='task not found'):
                TaskDataAclRepositoryImpl().get_task_devices('9')

    def test_acl_get_task_devices_empty_data_is_valid_empty_list(self):
        stub = SimpleNamespace(GetTaskDevices=MagicMock(
            return_value=SimpleNamespace(success=True, data='[]')))
        with patch('shared.clients.grpc_clients.get_task_data_service_stub',
                   return_value=stub):
            assert TaskDataAclRepositoryImpl().get_task_devices('9') == []
