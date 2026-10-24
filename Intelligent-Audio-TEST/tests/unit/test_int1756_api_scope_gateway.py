# -*- coding: utf-8 -*-
"""INT-1756（C6a）网关写路径 api_id 作用域校验单测。

DB 层不建跨服务外键（父卡 INT-1751 硬错 1：apis 归 api_test_service），
``api_id`` 的存在性与算法类型一致性只能在网关写路径保证：
- api_id 为空 → 算法级默认，不校验；
- 对应 API 不存在 → 400；
- API 的 algorithm_type 与参数行不一致 → 400。
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.algorithm import (  # noqa: E402
    algorithm_command_service as command_service,
)
from api_gateway.schemas.algorithm import (  # noqa: E402
    AlgorithmApiParamCreate,
    AlgorithmApiParamUpdate,
    MappingCreateRequest,
    MappingUpdateRequest,
    ParamMappingCreate,
    ParamMappingUpdate,
)


class _FakeAPIConfigProxy:
    def __init__(self, apis):
        self._apis = apis
        self.calls = []

    def get_one(self, api_id):
        self.calls.append(api_id)
        data = self._apis.get(api_id)
        if data is None:
            return {'success': False, 'message': '未找到API配置',
                    'data': None, 'code': 404}
        return {'success': True, 'message': 'Success', 'data': data, 'code': 200}


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self):
        return self._payload


@pytest.fixture()
def apis(monkeypatch):
    proxy = _FakeAPIConfigProxy({
        11: {'id': 11, 'algorithm_type': 'translation', 'name': 'A家'},
        12: {'id': 12, 'algorithm_type': 'asr', 'name': 'B家'},
    })
    monkeypatch.setattr(command_service, 'api_config_service', proxy)
    return proxy


@pytest.fixture()
def acl(monkeypatch):
    """替换网关 ACL：记录调用，避免真 gRPC。"""
    calls = []

    class _FakeACL:
        def create_param(self, data):
            calls.append(('create_param', data))
            return {'success': True, 'data': {'id': 1}}

        def create_mapping(self, data):
            calls.append(('create_mapping', data))
            return {'success': True, 'data': {'id': 1}}

        def update_param(self, param_id, data):
            calls.append(('update_param', param_id, data))
            return {'success': True, 'data': {'id': param_id}}

        def update_mapping(self, mapping_id, data):
            calls.append(('update_mapping', mapping_id, data))
            return {'success': True, 'data': {'id': mapping_id}}

    monkeypatch.setattr(command_service, '_algorithm_acl', _FakeACL())
    return calls


def _http(result):
    """service 方法返回 (payload, http_code)。"""
    return result[1], result[0]


# ========== _validate_api_scope ==========

def test_validate_scope_skips_when_api_id_absent(apis):
    assert command_service._validate_api_scope(None, 'translation') is None
    assert apis.calls == []


def test_validate_scope_accepts_matching_algorithm_type(apis):
    assert command_service._validate_api_scope(11, 'translation') is None
    assert apis.calls == [11]


def test_validate_scope_rejects_missing_api(apis):
    result = command_service._validate_api_scope(999, 'translation')
    assert result is not None
    http_code, payload = _http(result)
    assert http_code == 400
    assert '999' in payload['message']


def test_validate_scope_rejects_algorithm_type_mismatch(apis):
    result = command_service._validate_api_scope(12, 'translation')
    assert result is not None
    http_code, payload = _http(result)
    assert http_code == 400
    assert 'asr' in payload['message']


# ========== 写入口接线 ==========

def test_create_api_param_rejects_scope_mismatch(monkeypatch, apis, acl):
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'param_type_source': 'api', 'algorithm_type': 'translation',
        'api_id': 12, 'param_code': 'lang', 'param_type': 'text',
    }))
    http_code, _ = _http(command_service.AlgorithmCommandService.create_param())
    assert http_code == 400
    assert acl == []  # 校验失败不得落库


def test_create_api_param_passes_api_id_through(monkeypatch, apis, acl):
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'param_type_source': 'api', 'algorithm_type': 'translation',
        'api_id': 11, 'param_code': 'lang', 'param_type': 'text',
    }))
    http_code, _ = _http(command_service.AlgorithmCommandService.create_param())
    assert http_code == 200
    assert acl[0][1]['api_id'] == 11


def test_create_device_param_ignores_api_scope(monkeypatch, apis, acl):
    """设备参数表没有 api_id 列，走设备分支时不做 API 校验。"""
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'param_type_source': 'device', 'algorithm_type': 'translation',
        'param_code': 'sample_rate', 'param_type': 'text',
    }))
    http_code, _ = _http(command_service.AlgorithmCommandService.create_param())
    assert http_code == 200
    assert apis.calls == []


def test_create_mapping_rejects_scope_mismatch(monkeypatch, apis, acl):
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'algorithm_type': 'translation', 'api_id': 12, 'source_type': 'api',
        'source_param': 'answer', 'target_param': 'text',
    }))
    http_code, _ = _http(command_service.AlgorithmCommandService.create_mapping())
    assert http_code == 400
    assert acl == []


def test_create_mapping_passes_api_id_through(monkeypatch, apis, acl):
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'algorithm_type': 'translation', 'api_id': 11, 'source_type': 'api',
        'source_param': 'answer', 'target_param': 'text',
    }))
    http_code, _ = _http(command_service.AlgorithmCommandService.create_mapping())
    assert http_code == 200
    assert acl[0][1]['api_id'] == 11


def test_update_param_validates_api_id(monkeypatch, apis, acl):
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'api_id': 999, 'param_name': '新名称',
    }))
    http_code, _ = _http(
        command_service.AlgorithmCommandService.update_param(5))
    assert http_code == 400
    assert acl == []

    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'api_id': 11, 'algorithm_type': 'translation', 'param_name': '新名称',
    }))
    http_code, _ = _http(
        command_service.AlgorithmCommandService.update_param(5))
    assert http_code == 200
    assert acl[0][2]['api_id'] == 11


def test_update_mapping_validates_api_id(monkeypatch, apis, acl):
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'api_id': 12, 'algorithm_type': 'translation', 'target_param': 'x',
    }))
    http_code, _ = _http(
        command_service.AlgorithmCommandService.update_mapping(3))
    assert http_code == 400
    assert acl == []


# ========== 非法 api_id 是 400，不是未捕获 ValueError（审计 P3-1） ==========

@pytest.mark.parametrize('bad', ['abc', '', '1.5', {}, []])
def test_validate_scope_rejects_non_integer_api_id(apis, bad):
    result = command_service._validate_api_scope(bad, 'translation')
    assert result is not None
    http_code, payload = _http(result)
    assert http_code == 400
    assert 'api_id' in payload['message']
    assert apis.calls == []  # 非法值不查 API


def test_validate_scope_rejects_non_positive_api_id(apis):
    for bad in (0, -3):
        result = command_service._validate_api_scope(bad, 'translation')
        assert result is not None
        assert _http(result)[0] == 400
    assert apis.calls == []


def test_update_param_invalid_api_id_returns_400(monkeypatch, apis, acl):
    """更新载荷是裸 JSON（无 schema 兜底），非法 api_id 必须是 400 而非 500。"""
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'api_id': 'abc', 'param_name': '新名称',
    }))
    http_code, payload = _http(
        command_service.AlgorithmCommandService.update_param(5))
    assert http_code == 400
    assert 'api_id' in payload['message']
    assert acl == []


def test_update_mapping_invalid_api_id_returns_400(monkeypatch, apis, acl):
    monkeypatch.setattr(command_service, 'request', _FakeRequest({
        'api_id': 'abc', 'target_param': 'x',
    }))
    http_code, payload = _http(
        command_service.AlgorithmCommandService.update_mapping(3))
    assert http_code == 400
    assert acl == []


# ========== DTO 兼容 snake_case / camelCase ==========

def test_schemas_accept_api_id_in_both_cases():
    assert AlgorithmApiParamCreate.model_validate({
        'algorithm_type': 't', 'param_code': 'p', 'param_type': 'text',
        'api_id': 7}).api_id == 7
    assert AlgorithmApiParamCreate.model_validate({
        'algorithm_type': 't', 'param_code': 'p', 'param_type': 'text',
        'apiId': 7}).api_id == 7
    assert AlgorithmApiParamUpdate.model_validate({'apiId': 8}).api_id == 8
    assert MappingCreateRequest.model_validate({
        'algorithm_type': 't', 'source_type': 'api', 'source_param': 'a',
        'target_param': 'b', 'apiId': 9}).api_id == 9
    assert MappingUpdateRequest.model_validate({'api_id': 10}).api_id == 10
    assert ParamMappingCreate.model_validate({
        'algorithm_type': 't', 'source_type': 'api', 'source_param': 'a',
        'dimension_id': 1, 'target_param': 'b', 'apiId': 3}).api_id == 3
    assert ParamMappingUpdate.model_validate({'api_id': 4}).api_id == 4
    # 不传 = None（算法级默认）
    assert AlgorithmApiParamCreate.model_validate({
        'algorithm_type': 't', 'param_code': 'p',
        'param_type': 'text'}).api_id is None
