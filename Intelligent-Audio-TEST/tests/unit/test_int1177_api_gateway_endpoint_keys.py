# -*- coding: utf-8 -*-
"""INT-1177 网关 schema 端点级密钥池透传（INT-1230 审计 D1'/D6' 返工）。

APIModel `extra="ignore"` 会静默丢弃未声明字段——`endpoints[].api_keys`
（写侧）与 `endpoints[].api_keys_summary`（读侧）必补字段，否则前端传参/
网关读回被 Pydantic 丢弃。验证：
- ApiEndpointInput.api_keys 接受 snake_case 与 camelCase（apiKeys）
- ApiCreateInput/ApiUpdateInput.endpoints[].api_keys 透传（model_dump 保留）
- ApiEndpointItem.api_keys_summary 读侧字段存在
"""
from api_gateway.schemas.api import (
    ApiCreateInput,
    ApiEndpointItem,
    ApiUpdateInput,
)


class TestApiEndpointInputApiKeys:
    """ApiEndpointInput 接受 api_keys（snake_case 与 camelCase）。"""

    def test_accepts_snake_case_api_keys(self):
        data = ApiCreateInput.model_validate({
            'name': 'API-1',
            'meta': {},
            'endpoints': [{
                'endpoint': 'https://ep.example.com',
                'api_keys': ['sk-a1', 'sk-b2'],
            }],
        })
        ep = data.endpoints[0]
        assert ep.api_keys == ['sk-a1', 'sk-b2']

    def test_accepts_camel_case_apiKeys(self):
        """前端 DTO 以 camelCase（apiKeys）提交时可被 schema 接受。"""
        data = ApiCreateInput.model_validate({
            'name': 'API-1',
            'meta': {},
            'endpoints': [{
                'endpoint': 'https://ep.example.com',
                'apiKeys': ['sk-a1', 'sk-b2'],
            }],
        })
        assert data.endpoints[0].api_keys == ['sk-a1', 'sk-b2']

    def test_omitted_api_keys_default_none(self):
        """未传 api_keys 时行为与改动前一致（回归）：默认 None。"""
        data = ApiCreateInput.model_validate({
            'name': 'API-1',
            'meta': {},
            'endpoints': [{'endpoint': 'https://ep.example.com'}],
        })
        assert data.endpoints[0].api_keys is None

    def test_dump_keeps_api_keys(self):
        """create 侧真实路径：model_dump 保留 endpoints[].api_keys 透传给微服务。"""
        create = ApiCreateInput(
            name='API-1', meta={},
            endpoints=[{'endpoint': 'https://ep.example.com',
                        'api_keys': ['sk-a1']}],
        )
        dump = create.model_dump(by_alias=False, exclude_none=True)
        assert dump['endpoints'][0]['api_keys'] == ['sk-a1']

    def test_update_dump_keeps_api_keys(self):
        update = ApiUpdateInput(
            endpoints=[{'endpoint': 'https://ep.example.com',
                        'api_keys': ['sk-b2']}],
        )
        dump = update.model_dump(by_alias=False, exclude_none=True)
        assert dump['endpoints'][0]['api_keys'] == ['sk-b2']


class TestApiEndpointItemApiKeysSummary:
    """ApiEndpointItem.api_keys_summary 读侧字段（INT-1230 审计 D6'）。"""

    def test_accepts_per_endpoint_summary(self):
        item = ApiEndpointItem.model_validate({
            'endpoint': 'https://ep.example.com',
            'api_keys_summary': {'count': 2, 'tails': ['a1b2', 'c3d4']},
        })
        assert item.api_keys_summary == {'count': 2, 'tails': ['a1b2', 'c3d4']}

    def test_omitted_summary_default_none(self):
        item = ApiEndpointItem.model_validate({
            'endpoint': 'https://ep.example.com',
        })
        assert item.api_keys_summary is None
