# -*- coding: utf-8 -*-
"""第三方评估 ACL 编排单元测试（INT-29）。

8 步流程编排语义（替身传输客户端/适配器工厂，不依赖网络）：
- 中枢全流程：打包→传输登记→C 执行→校验→审计事件（Dispatched→Completed）
- 幂等 transfer_id 链路传递（重试/重发同键）
- 失败审计：适配器失败 / 传输失败 → Failed 事件（stage 标注）+ __error__ 语义
- 边缘中转 8 步：dispatch → execute_incoming（解包→执行→结果回同步）→ fetch
"""
import io
import json
import os
import sys
import zipfile

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from evaluation_service.domain.events.evaluation_events import (
    ThirdPartyEvalCompleted,
    ThirdPartyEvalDispatched,
    ThirdPartyEvalFailed,
)
from evaluation_service.domain.repositories.third_party_eval_port import ThirdPartyEvalResult
from evaluation_service.infrastructure.acl.third_party_eval_acl import (
    ThirdPartyEvalACL,
    ThirdPartyEvalSettings,
)
from evaluation_service.infrastructure.acl.transfer_eval_client import ThirdPartyEvalError

OK_DATA = {'code': 0, 'msg': 'ok', 'data': {'result': {'score': 0.92}}}


class FakeTransferClient:
    """传输链路替身：记录 send_file / 提供 get_transfer 审计视图。

    发送时对 bundle 做字节快照（真实链路中分片上传后源文件即可回收，
    审计/后续读取走远端 final_path —— 与 ACL「先删临时 bundle」的行为对齐）。
    """

    def __init__(self, tokens=None, final_dir=None):
        self.sent = []
        self.tokens = tokens or {'A_B': 'x', 'B_C': 'x'}
        self.final_dir = final_dir
        self.fail_on_send = False

    def get_token(self, src_zone, dst_zone):
        route = '_'.join(sorted([src_zone.upper(), dst_zone.upper()]))
        return self.tokens.get(route)

    def send_file(self, **kwargs):
        if self.fail_on_send:
            raise ThirdPartyEvalError('transfer_agent 不可达')
        with open(kwargs['local_path'], 'rb') as f:
            content = f.read()
        record = dict(kwargs)
        record['bundle_bytes'] = content
        if self.final_dir is not None:
            final_path = os.path.join(self.final_dir, f"{kwargs['transfer_id']}.zip")
            with open(final_path, 'wb') as dst:
                dst.write(content)
            record['final_path'] = final_path
        self.sent.append(record)
        return {'transfer_id': kwargs['transfer_id'], 'status': 'COMPLETED', 'dedup': False}

    def get_transfer(self, transfer_id, token=''):
        for record in self.sent:
            if record['transfer_id'] == transfer_id:
                view = {'transfer_id': transfer_id,
                        'pkg_type': record['pkg_type'],
                        'src_zone': record['src_zone'],
                        'dst_zone': record['dst_zone'],
                        'final_path': record.get('final_path')}
                return view
        raise ThirdPartyEvalError(f'transfer {transfer_id} 不存在')


class StubAdapter:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def evaluate(self, request):
        self.requests.append(request)
        return self.result


class StubAdapterFactory:
    def __init__(self, result=None):
        self.result = result or ThirdPartyEvalResult(ok=True, transfer_id='tid', data=OK_DATA)
        self.created = []

    def create(self, kind, settings):
        adapter = StubAdapter(self.result)
        self.created.append((kind, settings, adapter))
        return adapter


def make_settings(tmp_path, **overrides):
    defaults = dict(
        self_zone='B', hub_zone='B',
        transfer_agent_base_url='http://ta-b', hub_transfer_agent_base_url='http://ta-b',
        c_api_base_url='http://c', adapter='multipart',
        timeout_seconds=10, max_retries=3, backoff_seconds=0.01,
        staging_enabled=True, staging_ttl_seconds=600,
        sync_back_enabled=True, sync_back_zone='A',
        response_required_keys=[],
    )
    defaults.update(overrides)
    settings = ThirdPartyEvalSettings.__new__(ThirdPartyEvalSettings)
    for key, value in defaults.items():
        setattr(settings, key, value)
    settings.config_path = str(tmp_path / 'cfg.json')
    return settings


def make_acl(tmp_path, client=None, factory=None, settings=None, bundle_reader=None):
    client = client or FakeTransferClient()
    factory = factory or StubAdapterFactory()
    settings = settings or make_settings(tmp_path)
    events = []
    acl = ThirdPartyEvalACL(
        settings=settings, adapter_factory=factory, client=client,
        bundle_reader=bundle_reader, event_sink=events.append)
    return acl, client, factory, events


def group_kwargs():
    return dict(
        payload={'task_type': 'llm_judge'},
        form_fields={'task_type': 'llm_judge', 'prompt': '评分'},
        files={'record_file': ('a.wav', b'RIFFxxxxWAVEfmt ', 'audio/wav')},
        representative_dim_data={'id': 7, 'name': 'llm_judge', 'task_type_code': 'llm_judge'},
        dim_names=['llm_judge'],
        dim_info={'task_type_code': 'llm_judge'},
        task_id=1, test_case_id='11',
    )


class TestHubFullFlow:
    def test_full_flow_success_and_audit_events(self, tmp_path):
        acl, client, factory, events = make_acl(tmp_path)
        resp = acl.evaluate_dimension_group(**group_kwargs())
        assert resp == OK_DATA
        # ①② 传输登记：EVAL_REQUEST、src=B、dst=C、ephemeral=True（transit 暂存）
        assert len(client.sent) == 1
        sent = client.sent[0]
        assert sent['pkg_type'] == 'EVAL_REQUEST'
        assert sent['src_zone'] == 'B' and sent['dst_zone'] == 'C'
        assert sent['ephemeral'] is True
        # ③ 适配器收到解包等价的请求（文件完整）
        kind, settings, adapter = factory.created[0]
        assert kind == 'multipart'
        req = adapter.requests[0]
        assert req.transfer_id == sent['transfer_id']
        assert req.files['record_file'].content == b'RIFFxxxxWAVEfmt '
        # ⑦ 审计事件完整（Dispatched → Completed，同 transfer_id）
        assert [type(e) for e in events] == [ThirdPartyEvalDispatched, ThirdPartyEvalCompleted]
        assert events[0].transfer_id == events[1].transfer_id == sent['transfer_id']
        assert events[1].duration_ms >= 0

    def test_transfer_id_reused_when_provided(self, tmp_path):
        acl, client, factory, events = make_acl(tmp_path)
        acl.evaluate_dimension_group(**group_kwargs(), transfer_id='fixed-tid')
        acl.evaluate_dimension_group(**group_kwargs(), transfer_id='fixed-tid')
        # 链路幂等键：两次调用同 transfer_id（传输层凭此去重）
        assert [s['transfer_id'] for s in client.sent] == ['fixed-tid', 'fixed-tid']

    def test_no_sync_back_for_hub_self_origin(self, tmp_path):
        acl, client, factory, events = make_acl(tmp_path)
        acl.evaluate_dimension_group(**group_kwargs())
        # 中枢自有评估不产生 EVAL_RESULT 回传包
        assert all(s['pkg_type'] == 'EVAL_REQUEST' for s in client.sent)

    def test_hub_inline_staging_meta_marks_audit_anchor(self, tmp_path):
        acl, client, factory, events = make_acl(tmp_path)
        acl.evaluate_dimension_group(**group_kwargs())
        # 流水语义（问题 2 过渡对齐）：中枢内联 dst='C' 登记为暂存/审计锚点，非数据面传输
        assert client.sent[0]['meta'].get('staging_purpose') == 'audit_anchor'

    def test_adapter_failure_emits_failed_event(self, tmp_path):
        factory = StubAdapterFactory(ThirdPartyEvalResult(
            ok=False, transfer_id='tid', error='C 返回失败'))
        acl, client, factory_, events = make_acl(tmp_path, factory=factory)
        resp = acl.evaluate_dimension_group(**group_kwargs())
        assert '__error__' in resp
        types = [type(e) for e in events]
        assert types == [ThirdPartyEvalDispatched, ThirdPartyEvalFailed]
        assert events[1].stage == 'third_party_call'

    def test_transfer_failure_emits_failed_event(self, tmp_path):
        client = FakeTransferClient()
        client.fail_on_send = True
        acl, client, factory, events = make_acl(tmp_path, client=client)
        resp = acl.evaluate_dimension_group(**group_kwargs())
        assert '__error__' in resp
        assert [type(e) for e in events] == [ThirdPartyEvalFailed]
        assert events[0].stage == 'transfer'

    def test_non_hub_rejected_with_clear_error(self, tmp_path):
        settings = make_settings(tmp_path, self_zone='A', hub_zone='B')
        acl, client, factory, events = make_acl(tmp_path, settings=settings)
        resp = acl.evaluate_dimension_group(**group_kwargs())
        assert '__error__' in resp and '评估中枢' in resp['__error__']
        assert events[0].stage == 'zone_role'


class TestEdgeRelayFlow:
    def test_full_relay_chain_a_to_b_to_c_and_back(self, tmp_path):
        final_dir = str(tmp_path / 'final')
        os.makedirs(final_dir)
        client = FakeTransferClient(final_dir=final_dir)
        factory = StubAdapterFactory()
        hub_settings = make_settings(tmp_path, self_zone='B', hub_zone='B')
        hub_acl = ThirdPartyEvalACL(settings=hub_settings, adapter_factory=factory,
                                    client=client, event_sink=lambda e: None)
        edge_settings = make_settings(tmp_path, self_zone='A', hub_zone='B',
                                      hub_transfer_agent_base_url='http://ta-b')
        edge_acl = ThirdPartyEvalACL(settings=edge_settings, adapter_factory=factory,
                                     client=client, event_sink=lambda e: None)

        # A: ①② 打包 + 传输到中枢（dst=B）
        dispatched = edge_acl.dispatch_eval_request(
            form_fields={'task_type': 'llm_judge'},
            files={'record_file': ('a.wav', b'RIFFxxxxWAVEfmt ', 'audio/wav')},
            eval_params={'task_id': 1, 'test_case_id': '11', 'dimensions': ['llm_judge'],
                         'adapter': 'multipart'},
            transfer_id='relay-001')
        assert dispatched['transfer_id'] == 'relay-001'
        request_sent = client.sent[0]
        assert request_sent['pkg_type'] == 'EVAL_REQUEST'
        assert request_sent['src_zone'] == 'A' and request_sent['dst_zone'] == 'B'

        # B: ③~⑧ 执行中转请求（解包→C→校验→EVAL_RESULT 回同步 A）
        hub_resp = hub_acl.execute_incoming('relay-001')
        assert hub_resp == OK_DATA
        result_sent = client.sent[1]
        assert result_sent['pkg_type'] == 'EVAL_RESULT'
        assert result_sent['src_zone'] == 'B' and result_sent['dst_zone'] == 'A'
        assert result_sent['transfer_id'] == 'relay-001-result'
        assert result_sent['ephemeral'] is False

        # A: ⑧ 接收侧取回回同步结果
        fetched = edge_acl.fetch_incoming_result('relay-001-result')
        assert fetched['transfer_id'] == 'relay-001'
        assert fetched['result'] == OK_DATA

    def test_execute_incoming_rejects_wrong_pkg_type(self, tmp_path):
        final_dir = str(tmp_path / 'final')
        os.makedirs(final_dir)
        client = FakeTransferClient(final_dir=final_dir)
        acl, _, _, _ = make_acl(tmp_path, client=client)
        client.send_file(transfer_id='x1', pkg_type='REPORT_SYNC', src_zone='A', dst_zone='B',
                         category='reports', key='r.zip', local_path=__file__,
                         ephemeral=False, ttl_seconds=600, meta={})
        client.sent[0]['final_path'] = __file__
        with pytest.raises(RuntimeError, match='EVAL_REQUEST'):
            acl.execute_incoming('x1')

    def test_bundle_roundtrip_preserves_files(self, tmp_path):
        acl, client, factory, _ = make_acl(tmp_path)
        acl.evaluate_dimension_group(**group_kwargs())
        sent = client.sent[0]
        with zipfile.ZipFile(io.BytesIO(sent['bundle_bytes'])) as zf:
            manifest = json.loads(zf.read('request.json').decode('utf-8'))
            assert manifest['form_fields']['task_type'] == 'llm_judge'
            assert manifest['files']['record_file']['filename'] == 'a.wav'
            assert zf.read('files/record_file') == b'RIFFxxxxWAVEfmt '

    def test_edge_dispatch_to_hub_meta_is_real_transfer_leg(self, tmp_path):
        settings = make_settings(tmp_path, self_zone='A', hub_zone='B',
                                 hub_transfer_agent_base_url='http://ta-b')
        acl, client, factory, _ = make_acl(tmp_path, settings=settings)
        acl.dispatch_eval_request(
            form_fields={'task_type': 'llm_judge'},
            files={'record_file': ('a.wav', b'RIFFxxxxWAVEfmt ', 'audio/wav')},
            eval_params={'task_id': 1, 'test_case_id': '11', 'dimensions': ['llm_judge'],
                         'adapter': 'multipart'})
        # A→B 中转腿是真实数据面：不携带暂存/审计锚点标注
        assert client.sent[0]['dst_zone'] == 'B'
        assert 'staging_purpose' not in client.sent[0]['meta']


class TestHubFailurePaths:
    def test_execute_incoming_bundle_missing_audits_failed_with_unpack_stage(self, tmp_path):
        final_dir = str(tmp_path / 'final')
        os.makedirs(final_dir)
        client = FakeTransferClient(final_dir=final_dir)
        acl, _, _, events = make_acl(tmp_path, client=client)
        client.send_file(transfer_id='x2', pkg_type='EVAL_REQUEST', src_zone='A', dst_zone='B',
                         category='case-result', key='e.zip', local_path=__file__,
                         ephemeral=True, ttl_seconds=600, meta={})
        # transit 包被 TTL 清理/文件缺失：读包失败发生在解包前（request 未构建）
        os.remove(client.sent[0]['final_path'])
        with pytest.raises(OSError):  # 原始错误原样上抛，不被 UnboundLocalError 掩蔽
            acl.execute_incoming('x2')
        failed = [e for e in events if isinstance(e, ThirdPartyEvalFailed)]
        assert len(failed) == 1
        assert failed[0].transfer_id == 'x2'
        assert failed[0].stage == 'unpack'
        assert failed[0].task_id is None and failed[0].test_case_id is None

    def test_execute_incoming_corrupt_bundle_audits_failed_with_unpack_stage(self, tmp_path):
        final_dir = str(tmp_path / 'final')
        os.makedirs(final_dir)
        client = FakeTransferClient(final_dir=final_dir)
        acl, _, _, events = make_acl(tmp_path, client=client)
        client.send_file(transfer_id='x3', pkg_type='EVAL_REQUEST', src_zone='A', dst_zone='B',
                         category='case-result', key='e.zip', local_path=__file__,
                         ephemeral=True, ttl_seconds=600, meta={})
        with open(client.sent[0]['final_path'], 'wb') as f:
            f.write(b'not-a-zip')
        with pytest.raises(zipfile.BadZipFile):
            acl.execute_incoming('x3')
        failed = [e for e in events if isinstance(e, ThirdPartyEvalFailed)]
        assert [e.stage for e in failed] == ['unpack']

    def test_staging_disabled_skips_transfer_registration(self, tmp_path):
        settings = make_settings(tmp_path, staging_enabled=False)
        acl, client, factory, events = make_acl(tmp_path, settings=settings)
        resp = acl.evaluate_dimension_group(**group_kwargs())
        assert resp == OK_DATA
        # 暂存登记关闭：仅直调 C，不产生 transfer_agent 登记流水
        assert client.sent == []
        assert [type(e) for e in events] == [ThirdPartyEvalDispatched, ThirdPartyEvalCompleted]


class TestSettings:
    def test_response_required_keys_list_from_config(self, tmp_path, monkeypatch):
        monkeypatch.delenv('THIRD_PARTY_EVAL_RESPONSE_REQUIRED_KEYS', raising=False)
        cfg = tmp_path / 'cfg.json'
        cfg.write_text(json.dumps({'third_party': {'response_required_keys': ['code', 'msg']}}),
                       encoding='utf-8')
        settings = ThirdPartyEvalSettings(config_path=str(cfg))
        assert settings.response_required_keys == ['code', 'msg']

    def test_response_required_keys_str_env_override_splits_by_comma(self, tmp_path, monkeypatch):
        cfg = tmp_path / 'cfg.json'
        cfg.write_text(json.dumps({'third_party': {}}), encoding='utf-8')
        monkeypatch.setenv('THIRD_PARTY_EVAL_RESPONSE_REQUIRED_KEYS', 'code, data.result.score')
        settings = ThirdPartyEvalSettings(config_path=str(cfg))
        assert settings.response_required_keys == ['code', 'data.result.score']
