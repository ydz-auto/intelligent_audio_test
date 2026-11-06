# -*- coding: utf-8 -*-
"""第三方评估调度接线单元测试（INT-29）。

- 维度按评估能力注册表分流（THIRD_PARTY_C / LOCAL），注册表异常 fail-closed 回退 LOCAL
- ThirdPartyEndpointWorker 仅替换「调评估 API」一步：文件提取后交给第三方评估 ACL
"""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

import evaluation_service.infrastructure.evaluation_api.third_party_worker as tp_worker_module
from evaluation_service.infrastructure.evaluation_api.third_party_worker import (
    ThirdPartyDispatcherMixin,
    ThirdPartyEndpointWorker,
    resolve_capability_entry,
)
from shared.models.common_enums import EvalCapabilityTarget, ThirdPartyAdapterKind


class FakeRegistry:
    def __init__(self, entries=None):
        self.entries = entries or {}

    def resolve(self, dim_data):
        key = dim_data.get('task_type_code') or dim_data.get('name') or str(dim_data.get('id'))
        return self.entries.get(str(key))


class _SplitHost(ThirdPartyDispatcherMixin):
    def __init__(self, registry):
        self.registry = registry
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


class FakeACL:
    def __init__(self):
        self.calls = []
        self.response = {'code': 0, 'data': {'result': {'score': 0.9}}}

    def evaluate_dimension_group(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeApiClient:
    def __init__(self):
        self.extracted = None

    def _extract_files_from_payload(self, payload, audio_field_names=None):
        return ({k: v for k, v in payload.items() if k != 'record_file'},
                {'record_file': ('a.wav', b'RIFF', 'audio/wav')})


@pytest.fixture
def patched_registry(monkeypatch):
    registry = FakeRegistry()
    monkeypatch.setattr(tp_worker_module, 'resolve_capability_entry',
                        lambda dim_data: _safe_resolve(registry, dim_data))
    return registry


def _safe_resolve(registry, dim_data):
    try:
        return registry.resolve(dim_data)
    except Exception:
        return None


class TestSplitByEvalCapability:
    def test_third_party_dims_are_split_out(self, patched_registry):
        from evaluation_service.domain.services.evaluation_capability_registry import CapabilityEntry
        patched_registry.entries = {
            'llm_judge': CapabilityEntry(
                dimension='llm_judge', target=EvalCapabilityTarget.THIRD_PARTY_C,
                adapter=ThirdPartyAdapterKind.MULTIPART, enabled=True),
        }
        host = _SplitHost(patched_registry)
        dims = [
            {'id': 1, 'name': 'llm_judge', 'task_type_code': 'llm_judge'},
            {'id': 2, 'name': 'wer', 'task_type_code': 'wer'},
        ]
        local, third = host._split_by_eval_capability(dims, task_id=1, test_case_id='11')
        assert [d['id'] for d in third] == [1]
        assert [d['id'] for d in local] == [2]
        assert host.logs, '分流发生时应输出审计日志'

    def test_registry_failure_falls_back_to_local(self, monkeypatch):
        import evaluation_service.domain.services.evaluation_capability_registry as registry_module

        class BoomRegistry:
            def resolve(self, dim_data):
                raise RuntimeError('registry down')

        monkeypatch.setattr(registry_module, 'evaluation_capability_registry', BoomRegistry())
        host = _SplitHost(None)
        local, third = host._split_by_eval_capability(
            [{'id': 1, 'name': 'x'}], task_id=1, test_case_id='11')
        assert len(local) == 1 and third == []


class TestThirdPartyEndpointWorker:
    def _make_worker(self, monkeypatch, eval_service, adapter_kind='multipart'):
        monkeypatch.setattr(
            'evaluation_service.infrastructure.evaluation_api.endpoint_worker.'
            'EndpointWorker._get_redis_client', staticmethod(lambda: None))
        return ThirdPartyEndpointWorker(
            endpoint_url='third-party-c://multipart/7', eval_service=eval_service,
            adapter_kind=adapter_kind)

    def test_worker_delegates_to_acl_with_extracted_files(self, monkeypatch):
        acl = FakeACL()
        eval_service = type('Host', (), {'api_client': FakeApiClient(), 'third_party_eval': acl})()
        worker = self._make_worker(monkeypatch, eval_service)
        resp = worker._call_evaluation_api(
            task_id=1, test_case_id='11', endpoints=[], method='POST', headers={},
            payload={'task_type': 'llm_judge', 'record_file': 'ignored'},
            representative_dim_data={'id': 7, 'name': 'llm_judge'},
            dim_names=['llm_judge'], dim_info={}, audio_field_names={'record_file'})
        assert resp == acl.response
        call = acl.calls[0]
        assert call['adapter_kind'] == 'multipart'
        assert call['files']['record_file'][0] == 'a.wav'
        assert call['form_fields'] == {'task_type': 'llm_judge'}
        assert call['task_id'] == 1 and call['test_case_id'] == '11'

    def test_worker_file_extraction_failure_returns_error(self, monkeypatch):
        class BrokenClient:
            def _extract_files_from_payload(self, payload, audio_field_names=None):
                raise RuntimeError('extract boom')
        acl = FakeACL()
        eval_service = type('Host', (), {'api_client': BrokenClient(), 'third_party_eval': acl})()
        worker = self._make_worker(monkeypatch, eval_service)
        resp = worker._call_evaluation_api(
            task_id=1, test_case_id='11', endpoints=[], method='POST', headers={},
            payload={}, representative_dim_data={'id': 7}, dim_names=[],
            dim_info={}, audio_field_names=set())
        assert '__error__' in resp and 'extract boom' in resp['__error__']
        assert acl.calls == []
