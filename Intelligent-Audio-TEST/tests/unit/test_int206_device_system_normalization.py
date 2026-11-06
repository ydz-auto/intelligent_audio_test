# -*- coding: utf-8 -*-
"""INT-206 验收：设备 system 枚举写入校验 + 驱动侧归一 + CreateDriver 真因透传。

背景：换库（INT-139 生产直拷）后存量 device.system='harmony'（前端注册/扫描
表单写入的别名）导致 get_driver_for_device 平台映射 miss → CreateDriver
driver_found=false → E2E 物理链秒败（test_results 0 行），且 e2e 侧固定提示
hypium 缺失误导排障方向。

覆盖：
- shared DeviceSystem.normalize：规范值/大小写不敏感/harmony 别名/空与未知值拒绝
- api_gateway DeviceCreateSchema / DeviceUpdateSchema：system 归一落库，非法值 400
- driver_factory.get_driver_for_device：'harmony' 别名可达 keywords 解析；
  keywords 必填/未注册语义不放松（INT-83/INT-86）
- CreateDriver servicer initialize：解析失败消息携带真因，与 initialize False 可区分
- e2e ACL create_driver：失败上抛 device_service 真因，不再吞成 False；
  e2e_device_manager 错误信息透传真因，不再套用固定 hypium 提示
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from pydantic import ValidationError

from shared.models.common_enums import DeviceSystem
from device_service.infrastructure.drivers.driver_types import DevicePlatform
from device_service.infrastructure.drivers.driver_factory import device_driver_factory
from device_service.interfaces.grpc.device_runtime_servicers import DeviceServiceServicer
from e2e_test_service.application.services.e2e_device_manager import E2EDeviceManager

SN = '5SM0125613000197'


def _req(cfg):
    return SimpleNamespace(device_config=json.dumps(cfg), task_id='500')


def _find_keyword_by_platform(platform):
    """从真实工厂里找指定平台的已注册专用驱动 keywords；无（如缺 hypium）返回 None"""
    for keyword, driver in device_driver_factory._drivers_by_keyword.items():
        if driver.platform == platform:
            return keyword
    return None


# ==================== 1. shared DeviceSystem 归一 ====================

class TestDeviceSystemNormalize:
    def test_canonical_values_case_insensitive(self):
        assert DeviceSystem.normalize('HarmonyOS') is DeviceSystem.HARMONYOS
        assert DeviceSystem.normalize('android') is DeviceSystem.ANDROID
        assert DeviceSystem.normalize(' iOS ') is DeviceSystem.IOS

    def test_harmony_alias_normalizes_to_harmonyos(self):
        for raw in ('harmony', 'Harmony', 'HARMONY', 'harmonyos', 'HarmonyOS'):
            assert DeviceSystem.normalize(raw) is DeviceSystem.HARMONYOS, raw

    def test_normalized_value_is_storage_canonical(self):
        assert DeviceSystem.normalize('harmony').value == 'HarmonyOS'
        assert DeviceSystem.normalize('android').value == 'Android'

    def test_empty_rejected(self):
        for raw in ('', '   ', None):
            with pytest.raises(ValueError, match='不能为空'):
                DeviceSystem.normalize(raw)

    def test_unknown_rejected_with_legal_values(self):
        with pytest.raises(ValueError, match="未知设备系统.*'windows'"):
            DeviceSystem.normalize('windows')


# ==================== 2. api_gateway 写入侧 schema 校验 ====================

def _create_payload(**overrides):
    payload = {
        'name': 'pura90小艺', 'model': 'Pura90', 'type': 'smartphone',
        'system': 'harmony', 'system_version': '5.0',
        'app_name': '小艺通话', 'app_version': '1.0',
    }
    payload.update(overrides)
    return payload


class TestApiGatewaySchemaNormalization:
    def test_create_schema_normalizes_harmony(self):
        from api_gateway.schemas.device import DeviceCreateSchema
        req = DeviceCreateSchema.model_validate(_create_payload())
        assert req.system == 'HarmonyOS'

    def test_create_schema_rejects_unknown_system(self):
        from api_gateway.schemas.device import DeviceCreateSchema
        with pytest.raises(ValidationError):
            DeviceCreateSchema.model_validate(_create_payload(system='windows'))

    def test_create_schema_rejects_empty_system(self):
        from api_gateway.schemas.device import DeviceCreateSchema
        with pytest.raises(ValidationError):
            DeviceCreateSchema.model_validate(_create_payload(system='  '))

    def test_update_schema_normalizes_and_none_passthrough(self):
        from api_gateway.schemas.device import DeviceUpdateSchema
        assert DeviceUpdateSchema.model_validate({'system': 'harmony'}).system == 'HarmonyOS'
        assert DeviceUpdateSchema.model_validate({'system': 'ANDROID'}).system == 'Android'
        assert DeviceUpdateSchema.model_validate({}).system is None
        assert DeviceUpdateSchema.model_validate({'system': None}).system is None

    def test_update_schema_rejects_unknown_system(self):
        from api_gateway.schemas.device import DeviceUpdateSchema
        with pytest.raises(ValidationError):
            DeviceUpdateSchema.model_validate({'system': 'windows'})


# ==================== 3. 驱动侧 get_driver_for_device 归一 ====================

class TestDriverFactorySystemAlias:
    def test_harmony_alias_reaches_keyword_lookup(self):
        # 'harmony' 必须通过平台归一进入 keywords 解析：
        # 未注册 keywords 时报错应是「未注册驱动」而非「system 非法」
        with pytest.raises(ValueError, match='未注册驱动 keywords'):
            device_driver_factory.get_driver_for_device('harmony', keywords='no.such.keyword')

    def test_unknown_system_raises_real_cause(self):
        with pytest.raises(ValueError, match="未知设备系统.*'windows'"):
            device_driver_factory.get_driver_for_device('windows', keywords='x')

    def test_keywords_required_semantics_unchanged(self):
        # INT-83 收紧语义不得被 INT-206 放松：无 keywords 仍拒绝
        with pytest.raises(ValueError, match='设备必须提供明确的驱动 keywords 标识'):
            device_driver_factory.get_driver_for_device('harmony')

    def test_legacy_harmony_value_resolves_harmonyos_driver(self):
        keyword = _find_keyword_by_platform(DevicePlatform.HARMONYOS)
        if keyword is None:
            pytest.skip('本机未注册 HarmonyOS 专用驱动（hypium 不可用）')
        expected = device_driver_factory._drivers_by_keyword[keyword]
        for raw in ('harmony', 'HarmonyOS', 'HARMONYOS'):
            assert device_driver_factory.get_driver_for_device(raw, keywords=keyword) is expected, raw

    def test_android_case_insensitive_resolves_same_driver(self):
        keyword = _find_keyword_by_platform(DevicePlatform.ANDROID)
        if keyword is None:
            pytest.skip('本机未注册 Android 专用驱动')
        expected = device_driver_factory._drivers_by_keyword[keyword]
        assert device_driver_factory.get_driver_for_device('ANDROID', keywords=keyword) is expected


# ==================== 4. CreateDriver servicer 真因透传 ====================

class TestCreateDriverRealCause:
    def test_invalid_system_message_carries_cause(self):
        # 真实工厂：system 非法 → success=False 且消息即真因（不再伪装 initialize failed）
        resp = DeviceServiceServicer().CreateDriver(_req({
            'action': 'initialize', 'system': 'windows', 'keywords': 'x',
            'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is False
        assert "未知设备系统" in resp.message and 'windows' in resp.message
        data = json.loads(resp.data)
        assert data['driver_found'] is False
        assert data['resolve_error'] and 'windows' in data['resolve_error']

    def test_keywords_miss_message_distinguishable(self):
        resp = DeviceServiceServicer().CreateDriver(_req({
            'action': 'initialize', 'system': 'HarmonyOS', 'keywords': 'no.such.keyword',
            'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is False
        assert '未注册驱动 keywords' in resp.message

    def test_resolve_failure_distinguishable_from_initialize_false(self):
        # mock 工厂：解析 ValueError → 驱动解析失败；initialize False → initialize failed
        factory = MagicMock()
        factory.get_driver_for_device.side_effect = ValueError('未知设备系统 system: harmony')
        servicer = DeviceServiceServicer()
        with patch('device_service.infrastructure.drivers.driver_factory.device_driver_factory', factory):
            resp = servicer.CreateDriver(_req({
                'action': 'initialize', 'system': 'harmony', 'keywords': 'x',
                'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is False
        assert '驱动解析失败' in resp.message and SN in resp.message
        assert json.loads(resp.data)['driver_found'] is False

        driver = MagicMock()
        driver.initialize.return_value = False
        factory.get_driver_for_device.side_effect = None
        factory.get_driver_for_device.return_value = driver
        with patch('device_service.infrastructure.drivers.driver_factory.device_driver_factory', factory):
            resp = servicer.CreateDriver(_req({
                'action': 'initialize', 'system': 'HarmonyOS', 'keywords': 'x',
                'device_sn': SN, 'device_info_list': [], 'kwargs': {}}))
        assert resp.success is False
        assert 'initialize failed' in resp.message and '驱动解析失败' not in resp.message


# ==================== 5. e2e ACL / device_manager 真因透传 ====================

def _acl_stub(resp=None, error=None):
    stub = MagicMock()
    if error is not None:
        stub.CreateDriver.side_effect = error
    else:
        stub.CreateDriver.return_value = resp
    return stub


class TestE2eAclCreateDriverRaise:
    def test_failure_raises_with_device_service_message(self):
        from e2e_test_service.infrastructure.acl.device_acl_repository_impl import DeviceAclRepositoryImpl
        stub = _acl_stub(SimpleNamespace(success=False, message='驱动解析失败 on sn1: 未知设备系统 system: harmony'))
        with patch('shared.clients.grpc_clients.get_device_service_stub', return_value=stub):
            with pytest.raises(RuntimeError, match='驱动解析失败'):
                DeviceAclRepositoryImpl().create_driver('500', [{'action': 'initialize'}])

    def test_success_returns_true(self):
        from e2e_test_service.infrastructure.acl.device_acl_repository_impl import DeviceAclRepositoryImpl
        stub = _acl_stub(SimpleNamespace(success=True, message='ok'))
        with patch('shared.clients.grpc_clients.get_device_service_stub', return_value=stub):
            assert DeviceAclRepositoryImpl().create_driver('500', [{'action': 'initialize'}]) is True

    def test_grpc_error_raises_not_false(self):
        from e2e_test_service.infrastructure.acl.device_acl_repository_impl import DeviceAclRepositoryImpl
        stub = _acl_stub(error=RuntimeError('grpc channel unavailable'))
        with patch('shared.clients.grpc_clients.get_device_service_stub', return_value=stub):
            with pytest.raises(RuntimeError, match='grpc channel unavailable'):
                DeviceAclRepositoryImpl().create_driver('500', [{'action': 'initialize'}])


class TestE2eManagerRealCausePropagation:
    def _manager(self, side_effect):
        mgr = E2EDeviceManager.__new__(E2EDeviceManager)
        mgr._executor = SimpleNamespace(
            _log=MagicMock(),
            execution_engine=SimpleNamespace(device_control_pool=ThreadPoolExecutor(max_workers=1)),
        )
        mgr._device_repo = MagicMock()
        mgr._device_repo.initialize_driver.side_effect = side_effect
        return mgr

    def test_initialize_failure_carries_real_cause(self):
        real_cause = '驱动解析失败 on sn1: 未知设备系统 system: harmony'
        mgr = self._manager(RuntimeError(real_cause))
        infos = [{'device_name': 'pura90小艺', 'system': 'harmony', 'keywords': 'harmony.xiaoyi_livechat.v1', 'device_sn': 'sn1'}]
        with pytest.raises(RuntimeError, match='驱动解析失败'):
            mgr.initialize_devices(infos, task_id=500, test_case_id='c1')

    def test_error_message_no_longer_hardcoded_hypium_hint(self):
        mgr = self._manager(RuntimeError('grpc down'))
        infos = [{'device_name': 'd1', 'system': 'harmony', 'keywords': 'x', 'device_sn': 'sn1'}]
        with pytest.raises(RuntimeError) as exc_info:
            mgr.initialize_devices(infos, task_id=500, test_case_id='c1')
        assert 'hypium' not in str(exc_info.value)
        assert 'grpc down' in str(exc_info.value)
