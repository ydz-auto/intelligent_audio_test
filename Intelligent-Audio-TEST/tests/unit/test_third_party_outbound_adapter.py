# -*- coding: utf-8 -*-
"""第三方评估出站适配器单元测试（INT-49）。

ThirdPartyEvalPort 经 T-B 出站投递契约的实现：投递视图解析（delivered/dst_body）、
EVAL_RESULT 校验（code!=0 / 必填字段）、包路由 token 选择（package_route 注入）、
传输层异常上抛语义（stage=transfer）、工厂 fail-closed、直连路径退役守卫。
"""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from evaluation_service.domain.repositories.third_party_eval_port import (
    ThirdPartyEvalFile,
    ThirdPartyEvalRequest,
)
from evaluation_service.infrastructure.acl.third_party_outbound_adapter import (
    ThirdPartyEvalAdapterFactory,
    TransferAgentOutboundEvalAdapter,
)
from evaluation_service.infrastructure.acl.transfer_eval_client import ThirdPartyEvalError

OK_RESULT = {'code': 0, 'msg': 'ok', 'data': {'result': {'score': 0.92}}}


class FakeDispatchClient:
    def __init__(self, view=None, error=None):
        self.calls = []
        self.view = view or {'delivered': True, 'dst_status': 200, 'dst_body': OK_RESULT,
                             'dst_text': '', 'attempts': 1}
        self.error = error

    def dispatch_outbound(self, *, transfer_id, adapter_kind, src_zone, dst_zone):
        self.calls.append({'transfer_id': transfer_id, 'adapter_kind': adapter_kind,
                           'src_zone': src_zone, 'dst_zone': dst_zone})
        if self.error is not None:
            raise self.error
        return dict(self.view)


def make_request(eval_params=None):
    return ThirdPartyEvalRequest(
        transfer_id='tid-001',
        form_fields={'task_type': 'llm_judge', 'prompt': '评分'},
        files={'record_file': ThirdPartyEvalFile(
            name='record_file', filename='a.wav',
            content=b'RIFFxxxxWAVEfmt ', content_type='audio/wav')},
        eval_params=eval_params if eval_params is not None else {'adapter': 'multipart'},
    )


class TestOutboundEvalAdapter:
    def test_delivers_via_transfer_agent_and_returns_result(self):
        client = FakeDispatchClient()
        adapter = TransferAgentOutboundEvalAdapter(client=client)
        result = adapter.evaluate(make_request())
        assert result.ok is True
        assert result.data == OK_RESULT
        assert result.status_code == 200
        call = client.calls[0]
        assert call == {'transfer_id': 'tid-001', 'adapter_kind': 'multipart',
                        'src_zone': 'B', 'dst_zone': 'C'}

    def test_dispatch_token_uses_package_route_when_injected(self):
        # 中转流（A→B 暂存包）：execute_incoming 注入包自身路由，token 按包路由取
        client = FakeDispatchClient()
        adapter = TransferAgentOutboundEvalAdapter(client=client)
        adapter.evaluate(make_request({'adapter': 'multipart',
                                       'package_route': {'src': 'A', 'dst': 'B'}}))
        assert (client.calls[0]['src_zone'], client.calls[0]['dst_zone']) == ('A', 'B')

    def test_undelivered_view_maps_to_not_ok(self):
        client = FakeDispatchClient(view={'delivered': False, 'dst_status': 503,
                                          'dst_body': None, 'dst_text': '',
                                          'attempts': 4, 'error': 'HTTP 503'})
        result = TransferAgentOutboundEvalAdapter(client=client).evaluate(make_request())
        assert result.ok is False
        assert result.status_code == 503
        assert 'HTTP 503' in result.error

    def test_c_business_failure_code_not_zero(self):
        client = FakeDispatchClient(view={'delivered': True, 'dst_status': 200,
                                          'dst_body': {'code': 1, 'msg': '维度不支持'},
                                          'dst_text': '', 'attempts': 1})
        result = TransferAgentOutboundEvalAdapter(client=client).evaluate(make_request())
        assert result.ok is False
        assert '维度不支持' in result.error

    def test_non_object_body_rejected(self):
        client = FakeDispatchClient(view={'delivered': True, 'dst_status': 200,
                                          'dst_body': None, 'dst_text': 'not-json',
                                          'attempts': 1})
        result = TransferAgentOutboundEvalAdapter(client=client).evaluate(make_request())
        assert result.ok is False
        assert '响应为空或非对象' in result.error

    def test_required_keys_validation(self):
        client = FakeDispatchClient(view={'delivered': True, 'dst_status': 200,
                                          'dst_body': {'unexpected': 1},
                                          'dst_text': '', 'attempts': 1})
        result = TransferAgentOutboundEvalAdapter(client=client).evaluate(
            make_request({'adapter': 'multipart', 'response_required_keys': ['result']}))
        assert result.ok is False
        assert '缺少必填字段' in result.error

    def test_invalid_kind_fail_closed(self):
        client = FakeDispatchClient()
        result = TransferAgentOutboundEvalAdapter(client=client).evaluate(
            make_request({'adapter': 'smoke_signal'}))
        assert result.ok is False
        assert '非法第三方评估适配形态' in result.error
        assert client.calls == []

    def test_transfer_agent_unreachable_propagates(self):
        # 传输层异常原样上抛 → 编排层按 stage=transfer 审计（区别于 C 契约失败）
        client = FakeDispatchClient(error=ThirdPartyEvalError('transfer_agent 不可达'))
        with pytest.raises(ThirdPartyEvalError):
            TransferAgentOutboundEvalAdapter(client=client).evaluate(make_request())


class TestFactory:
    def test_factory_binds_outbound_adapter_for_all_kinds(self):
        client = FakeDispatchClient()
        factory = ThirdPartyEvalAdapterFactory()
        for kind in ('multipart', 'feature_extract', 'presigned_url'):
            adapter = factory.create(kind, client)
            assert isinstance(adapter, TransferAgentOutboundEvalAdapter)

    def test_factory_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match='非法第三方评估适配形态'):
            ThirdPartyEvalAdapterFactory().create('smoke_signal', FakeDispatchClient())


def test_direct_adapters_module_retired():
    """直连路径退役守卫：third_party_adapters 模块已删除，不可再 import。"""
    with pytest.raises(ImportError):
        import evaluation_service.infrastructure.acl.third_party_adapters  # noqa: F401
