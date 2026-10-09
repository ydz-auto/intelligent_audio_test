# -*- coding: utf-8 -*-
"""第三方评估 ACL 编排单元测试（INT-29/INT-49/INT-50）。

8 步流程编排语义（替身传输客户端/出站适配器工厂，不依赖网络）：
- 中枢全流程：打包→传输登记→T-B 出站投递→校验→审计事件（Dispatched→Completed）
- 幂等 transfer_id 链路传递（重试/重发同键）
- 失败审计：投递失败 / 传输失败 → Failed 事件（stage 标注）+ __error__ 语义
- 边缘中转 8 步：dispatch → execute_incoming（解包→出站投递→结果回同步）→ fetch
- 边缘自动中转（F2.2 接线）：evaluate_dimension_group 在边缘区自动
  dispatch → 轮询取回回同步 EVAL_RESULT（后台线程模拟中枢执行），失败收敛
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
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
from evaluation_service.infrastructure.acl.third_party_outbound_adapter import (
    ThirdPartyEvalAdapterFactory,
)
from evaluation_service.infrastructure.acl.transfer_eval_client import ThirdPartyEvalError

OK_DATA = {'code': 0, 'msg': 'ok', 'data': {'result': {'score': 0.92}}}
DELIVERED_VIEW = {'delivered': True, 'dst_status': 200, 'dst_body': OK_DATA,
                  'dst_text': '', 'attempts': 1}


class FakeTransferClient:
    """传输链路替身：记录 send_file / 出站投递 / 提供审计视图。

    发送时对 bundle 做字节快照（真实链路中分片上传后源文件即可回收，
    出站投递腿读取远端 final_path 的 transit 暂存包）。
    """

    def __init__(self, tokens=None, final_dir=None):
        self.sent = []
        self.tokens = tokens or {'A_B': 'x', 'B_C': 'x'}
        self.final_dir = final_dir
        self.fail_on_send = False
        self.fail_on_dispatch = False
        self.dispatch_calls = []
        self.dispatch_view = dict(DELIVERED_VIEW)

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

    def dispatch_outbound(self, *, transfer_id, adapter_kind, src_zone, dst_zone):
        if self.fail_on_dispatch:
            raise ThirdPartyEvalError('transfer_agent 不可达')
        self.dispatch_calls.append({'transfer_id': transfer_id,
                                    'adapter_kind': adapter_kind,
                                    'src_zone': src_zone, 'dst_zone': dst_zone})
        return dict(self.dispatch_view)

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
    """出站适配器替身：记录请求并触发 client.dispatch_outbound（与真实适配器同构），
    返回注入结果（用于分别驱动投递失败/成功路径）。"""

    def __init__(self, result, client):
        self.result = result
        self.client = client
        self.requests = []

    def evaluate(self, request):
        self.requests.append(request)
        route = request.eval_params.get('package_route') or {}
        self.client.dispatch_outbound(
            transfer_id=request.transfer_id,
            adapter_kind=str(request.eval_params.get('adapter') or 'multipart'),
            src_zone=str(route.get('src') or request.src_zone),
            dst_zone=str(route.get('dst') or request.dst_zone))
        return self.result


class StubAdapterFactory:
    def __init__(self, result=None):
        self.result = result or ThirdPartyEvalResult(ok=True, transfer_id='tid', data=OK_DATA)
        self.created = []

    def create(self, kind, client):
        adapter = StubAdapter(self.result, client)
        self.created.append((kind, client, adapter))
        return adapter


def make_settings(tmp_path, **overrides):
    defaults = dict(
        self_zone='B', hub_zone='B',
        transfer_agent_base_url='http://ta-b', hub_transfer_agent_base_url='http://ta-b',
        adapter='multipart',
        timeout_seconds=10, dispatch_timeout_seconds=30,
        staging_ttl_seconds=600,
        sync_back_enabled=True, sync_back_zone='A',
        response_required_keys=[],
        relay_poll_interval_seconds=2, relay_result_timeout_seconds=900,
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
        # ② 传输登记：EVAL_REQUEST、src=B、dst=C、ephemeral=True（真实 B→C 数据面暂存）
        assert len(client.sent) == 1
        sent = client.sent[0]
        assert sent['pkg_type'] == 'EVAL_REQUEST'
        assert sent['src_zone'] == 'B' and sent['dst_zone'] == 'C'
        assert sent['ephemeral'] is True
        # ③ 出站投递经 T-B（同 transfer_id，契约形态 multipart）
        assert len(client.dispatch_calls) == 1
        dispatch = client.dispatch_calls[0]
        assert dispatch == {'transfer_id': sent['transfer_id'],
                            'adapter_kind': 'multipart', 'src_zone': 'B', 'dst_zone': 'C'}
        # 适配器收到解包等价的请求（文件完整）
        kind, bound_client, adapter = factory.created[0]
        assert kind == 'multipart'
        assert bound_client is client
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
        # 链路幂等键：两次调用同 transfer_id（传输层凭此去重，出站投递幂等重投）
        assert [s['transfer_id'] for s in client.sent] == ['fixed-tid', 'fixed-tid']
        assert [c['transfer_id'] for c in client.dispatch_calls] == ['fixed-tid', 'fixed-tid']

    def test_no_sync_back_for_hub_self_origin(self, tmp_path):
        acl, client, factory, events = make_acl(tmp_path)
        acl.evaluate_dimension_group(**group_kwargs())
        # 中枢自有评估不产生 EVAL_RESULT 回传包
        assert all(s['pkg_type'] == 'EVAL_REQUEST' for s in client.sent)

    def test_hub_inline_staging_is_real_data_plane(self, tmp_path):
        acl, client, factory, events = make_acl(tmp_path)
        acl.evaluate_dimension_group(**group_kwargs())
        # dst='C' 登记即真实 B→C 数据面（F2.1 起），不再携带过渡期审计锚点标注
        assert 'staging_purpose' not in client.sent[0]['meta']
        assert client.sent[0]['meta']['adapter'] == 'multipart'

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

    def test_dispatch_unreachable_emits_failed_event(self, tmp_path):
        # 暂存成功但出站投递不可达：传输层异常按 stage=transfer 审计
        client = FakeTransferClient()
        client.fail_on_dispatch = True
        acl, client, factory, events = make_acl(tmp_path, client=client)
        resp = acl.evaluate_dimension_group(**group_kwargs())
        assert '__error__' in resp
        assert [type(e) for e in events] == [ThirdPartyEvalDispatched, ThirdPartyEvalFailed]
        assert events[1].stage == 'transfer'


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

        # B: ③~⑧ 执行中转请求（解包→T-B 出站投递→校验→EVAL_RESULT 回同步 A）
        hub_resp = hub_acl.execute_incoming('relay-001')
        assert hub_resp == OK_DATA
        # 出站投递 token 按暂存包自身路由（A→B）
        assert client.dispatch_calls[0] == {'transfer_id': 'relay-001',
                                            'adapter_kind': 'multipart',
                                            'src_zone': 'A', 'dst_zone': 'B'}
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


class TestEdgeAutoRelay:
    """边缘区（A）evaluate_dimension_group 自动中转接线（F2.2/INT-50）。

    区角色分流：EDGE 命中 THIRD_PARTY_C 不再拦截失败，自动 dispatch →
    轮询取回回同步 EVAL_RESULT（后台线程模拟中枢 execute_incoming 执行）；
    失败路径一律收敛为 {'__error__'} + Failed 审计（stage 标注），任务不悬挂。
    """

    def _edge_acl(self, tmp_path, client, factory, events, **overrides):
        settings = make_settings(
            tmp_path, self_zone='A', hub_zone='B',
            hub_transfer_agent_base_url='http://ta-b',
            relay_poll_interval_seconds=overrides.pop('relay_poll_interval_seconds', 0.01),
            relay_result_timeout_seconds=overrides.pop('relay_result_timeout_seconds', 10),
            **overrides)
        return ThirdPartyEvalACL(settings=settings, adapter_factory=factory,
                                 client=client, event_sink=events.append)

    def _start_hub_relay(self, hub_acl, client, transfer_id, timeout=8.0):
        """后台线程模拟中枢：发现 A→B 的 EVAL_REQUEST 包即执行 execute_incoming。"""

        def _run():
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if any(s['pkg_type'] == 'EVAL_REQUEST' and s['src_zone'] == 'A'
                       and s['transfer_id'] == transfer_id for s in client.sent):
                    hub_acl.execute_incoming(transfer_id)
                    return
                time.sleep(0.01)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread

    def test_auto_relay_full_chain_returns_result(self, tmp_path):
        final_dir = str(tmp_path / 'final')
        os.makedirs(final_dir)
        client = FakeTransferClient(final_dir=final_dir)
        factory = StubAdapterFactory()
        hub_acl = ThirdPartyEvalACL(
            settings=make_settings(tmp_path, self_zone='B', hub_zone='B'),
            adapter_factory=factory, client=client, event_sink=lambda e: None)
        events = []
        edge_acl = self._edge_acl(tmp_path, client, factory, events)
        self._start_hub_relay(hub_acl, client, 'relay-auto-1')

        resp = edge_acl.evaluate_dimension_group(**group_kwargs(), transfer_id='relay-auto-1')

        # ⑧ 取回的回同步结果原样返回（resp_data 与本地评估端点响应同形态）
        assert resp == OK_DATA
        # 传输流水全链路：EVAL_REQUEST A→B + EVAL_RESULT B→A
        assert [(s['pkg_type'], s['src_zone'], s['dst_zone']) for s in client.sent] == [
            ('EVAL_REQUEST', 'A', 'B'), ('EVAL_RESULT', 'B', 'A')]
        # 边缘审计事件：Dispatched（发起）→ Completed（取回，synced_back）
        assert [type(e) for e in events] == [ThirdPartyEvalDispatched, ThirdPartyEvalCompleted]
        assert (events[0].src_zone, events[0].dst_zone) == ('A', 'B')
        assert events[0].transfer_id == events[1].transfer_id == 'relay-auto-1'
        assert events[1].synced_back is True

    def test_dispatch_failure_converges_immediately(self, tmp_path):
        client = FakeTransferClient()
        client.fail_on_send = True
        events = []
        acl = self._edge_acl(tmp_path, client, StubAdapterFactory(), events)

        resp = acl.evaluate_dimension_group(**group_kwargs())

        assert '__error__' in resp and '中转发起失败' in resp['__error__']
        assert [type(e) for e in events] == [ThirdPartyEvalFailed]
        assert events[0].stage == 'transfer'

    def test_fetch_timeout_converges_with_fetch_result_stage(self, tmp_path):
        # 中枢不执行（无回同步包）：轮询到超时收敛为失败，任务不悬挂
        events = []
        acl = self._edge_acl(tmp_path, FakeTransferClient(), StubAdapterFactory(),
                             events, relay_result_timeout_seconds=0)

        resp = acl.evaluate_dimension_group(**group_kwargs())

        assert '__error__' in resp and '中转结果取回失败' in resp['__error__']
        assert [type(e) for e in events] == [ThirdPartyEvalDispatched, ThirdPartyEvalFailed]
        assert events[1].stage == 'fetch_result'
        assert '超时' in events[1].error

    def test_malformed_result_payload_converges(self, tmp_path):
        final_dir = str(tmp_path / 'final')
        os.makedirs(final_dir)
        client = FakeTransferClient(final_dir=final_dir)
        # 预置一份缺 result 字段的回同步包（中枢回同步契约被破坏）
        fd, path = tempfile.mkstemp(suffix='.zip')
        with os.fdopen(fd, 'wb') as raw:
            with zipfile.ZipFile(raw, 'w') as zf:
                zf.writestr('result.json', json.dumps({'transfer_id': 'relay-bad'}))
        try:
            client.send_file(transfer_id='relay-bad-result', pkg_type='EVAL_RESULT',
                             src_zone='B', dst_zone='A', category='case-result',
                             key='eval_result/relay-bad.zip', local_path=path,
                             ephemeral=False, ttl_seconds=600, meta={})
        finally:
            os.remove(path)
        events = []
        acl = self._edge_acl(tmp_path, client, StubAdapterFactory(), events)

        resp = acl.evaluate_dimension_group(**group_kwargs(), transfer_id='relay-bad')

        assert '__error__' in resp and 'result 字段' in resp['__error__']
        assert events[-1].stage == 'fetch_result'
        assert events[-1].transfer_id == 'relay-bad'


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

    def test_direct_call_settings_retired(self, tmp_path):
        settings = make_settings(tmp_path)
        # 直连路径退役（F2.1）：c_api_base_url / staging_enabled / 适配器重试配置不再存在
        assert not hasattr(settings, 'c_api_base_url')
        assert not hasattr(settings, 'staging_enabled')
        assert not hasattr(settings, 'max_retries')
        assert not hasattr(settings, 'backoff_seconds')
        assert not hasattr(settings, 'adapter_settings')
        assert settings.dispatch_timeout_seconds == 30
