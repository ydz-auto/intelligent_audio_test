# -*- coding: utf-8 -*-
"""INT-182 eval_server 裁判端点替身集成测试（契约对齐 + 注入语义锁定）。

被测对象（mock_services/ 独立 mock 服务，生产替身，非测试夹具）：
- mock_eval_server_judge  eval_server 异步任务协议替身：create_task /
  create_task_upload / get_status / get_final_result 契约 + INT-95 R8 llm_judge
  结果形态 + 延迟（HTTP 层/轮询层）/ 5xx 重试退避 / 4xx 不重试 / 协议错误 /
  分数模式 / per_round 形态注入 + /__control 热更新
- mock_third_party_eval   presigned 两步失败注入补齐（INT-137 注 B 缺口）：
  POST /upload-url 与 PUT /upload/{seq} 的 first_5xx 重试收敛 / always_4xx 不重试
  （真实 ThirdPartyCAPIClient 出站腿，C 端重试语义全真实）

外部依赖以替身仿真（无 DB/OSS/Redis 依赖）。
"""
import hashlib
import os
import sys
import time

import pytest
import requests

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mock_services.mock_eval_server_judge import (
    DEFAULT_PORT,
    MockJudgeBehavior,
    MockJudgeServer,
)
from mock_services.mock_third_party_eval import MockEvalBehavior, MockEvalServer
from shared.config.service_ports import MOCK_EVAL_SERVER_HTTP_PORT
from transfer_agent.domain.services.eval_request_bundle import (
    EvalRequestBundle,
    EvalRequestFile,
)
from transfer_agent.infrastructure.acl.c_api_client import ThirdPartyCAPIClient

AUDIO_BYTES = b'RIFF' + os.urandom(2 * 1024)


# ================= mock eval_server 裁判端点替身 =================
@pytest.fixture(scope='module')
def judge():
    server = MockJudgeServer(MockJudgeBehavior())
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture()
def judge_clean(judge):
    """每用例前后重置 mock 行为与状态（注入互不污染）。"""
    judge.service.behavior = MockJudgeBehavior()
    judge.service.state.reset()
    yield judge
    judge.service.behavior = MockJudgeBehavior()
    judge.service.state.reset()


def _create_task(base):
    r = requests.post(f'{base}/api/create_task',
                      json={'task_type': 'llm_judge'}, timeout=5)
    assert r.status_code == 200 and r.json()['code'] == 0
    return r.json()['data']['eval_task_id']


class TestMockJudgeContract:
    """AC1：异步任务协议契约 + INT-95 R8 llm_judge 结果形态 + 端口注册。"""

    def test_port_registered_from_service_ports(self):
        assert MOCK_EVAL_SERVER_HTTP_PORT == 5097
        assert DEFAULT_PORT == MOCK_EVAL_SERVER_HTTP_PORT

    def test_async_task_protocol_full_flow(self, judge_clean):
        base = judge_clean.base_url
        r = requests.post(f'{base}/api/create_task',
                          json={'task_type': 'llm_judge', 'rounds': []}, timeout=5)
        body = r.json()
        assert body['code'] == 0
        eval_task_id = body['data']['eval_task_id']
        assert eval_task_id
        # create 观测证据
        assert judge_clean.service.state.last_create['form'] == 'create_task'
        assert judge_clean.service.state.last_create['fields']['task_type'] == 'llm_judge'

        r = requests.get(f'{base}/api/get_status/{eval_task_id}', timeout=5)
        body = r.json()
        assert body['code'] == 0
        assert body['data']['status'] == 'completed'
        assert body['data']['progress'] == 100

        r = requests.get(f'{base}/api/get_final_result/{eval_task_id}', timeout=5)
        result = r.json()['data']['result']
        # INT-95 R8 轮契约形态（_int95_r8_judge.py RESULT 同构）
        assert result['逐轮话轮评估'] == 0.85
        assert result['response_latency_ms'] == 850
        assert result['ncc'] == 0.92
        assert [p['round_number'] for p in result['per_round']] == [0, 1]
        assert result['per_round'][0]['逐轮话轮评估'] == 0.85
        assert result['per_round'][1]['response_latency_ms'] == 850

    def test_create_task_upload_multipart(self, judge_clean):
        base = judge_clean.base_url
        r = requests.post(f'{base}/api/create_task_upload',
                          data={'task_type': 'llm_judge', 'threshold': '0.6'},
                          files={'record_file': ('a.wav', AUDIO_BYTES, 'audio/wav')},
                          timeout=5)
        body = r.json()
        assert body['code'] == 0 and body['data']['eval_task_id']
        last = judge_clean.service.state.last_create
        assert last['form'] == 'create_task_upload'
        assert last['fields']['task_type'] == 'llm_judge'
        assert last['files']['record_file'] == hashlib.sha256(AUDIO_BYTES).hexdigest()

    def test_health_endpoint(self, judge_clean):
        r = requests.get(f'{judge_clean.base_url}/health', timeout=5)
        assert r.status_code == 200
        assert r.json() == {'status': 'ok', 'service': 'mock_eval_server_judge'}


class TestMockJudgeInjection:
    """AC1：行为注入语义锁定（延迟 / 5xx·4xx / 协议错误 / 分数 / 轮次形态 / 热更新）。"""

    def test_running_polls_injection(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control', json={'running_polls': 2}, timeout=5)
        eval_task_id = _create_task(base)

        statuses = [requests.get(f'{base}/api/get_status/{eval_task_id}', timeout=5)
                    .json()['data']['status'] for _ in range(3)]

        # 异步轮询延迟：前 2 次 running，其后 completed（客户端轮询循环全走通）
        assert statuses == ['running', 'running', 'completed']

    def test_first_5xx_injects_once_per_key(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control?fail_mode=first_5xx', timeout=5)

        # create 键首次 5xx → 重试成功
        r1 = requests.post(f'{base}/api/create_task', json={}, timeout=5)
        assert r1.status_code == 500
        r2 = requests.post(f'{base}/api/create_task', json={}, timeout=5)
        assert r2.status_code == 200
        eval_task_id = r2.json()['data']['eval_task_id']

        # eval_task_id 键独立计数：status 首次 5xx → 重试成功 → final_result 放行
        s1 = requests.get(f'{base}/api/get_status/{eval_task_id}', timeout=5)
        assert s1.status_code == 500
        s2 = requests.get(f'{base}/api/get_status/{eval_task_id}', timeout=5)
        assert s2.status_code == 200 and s2.json()['data']['status'] == 'completed'
        f1 = requests.get(f'{base}/api/get_final_result/{eval_task_id}', timeout=5)
        assert f1.status_code == 200

        # 控制端点与健康检查不受失败注入影响
        assert requests.get(f'{base}/health', timeout=5).status_code == 200
        assert requests.get(f'{base}/__control', timeout=5).status_code == 200

    def test_always_5xx_and_always_4xx(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control?fail_mode=always_5xx&fail_status=503', timeout=5)
        r = requests.post(f'{base}/api/create_task', json={}, timeout=5)
        assert r.status_code == 503 and r.json()['code'] == 503

        requests.post(f'{base}/__control?fail_mode=always_4xx', timeout=5)
        r = requests.post(f'{base}/api/create_task', json={}, timeout=5)
        assert r.status_code == 400 and r.json()['code'] == 400

    def test_protocol_error_missing_task_id(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control',
                      json={'protocol_error': 'missing_task_id'}, timeout=5)
        body = requests.post(f'{base}/api/create_task',
                             json={'task_type': 'llm_judge'}, timeout=5).json()
        # code 0 但缺 eval_task_id（客户端收敛"创建任务失败: 未返回task_id"）
        assert body['code'] == 0 and 'eval_task_id' not in body['data']

    def test_protocol_error_bad_code(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control', json={'protocol_error': 'bad_code'}, timeout=5)
        create_body = requests.post(f'{base}/api/create_task', json={}, timeout=5).json()
        assert create_body['code'] == 1
        status_body = requests.get(
            f'{base}/api/get_status/eval-xxx', timeout=5).json()
        assert status_body['code'] == 1

    def test_protocol_error_malformed_json(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control',
                      json={'protocol_error': 'malformed_json'}, timeout=5)
        r = requests.post(f'{base}/api/create_task', json={}, timeout=5)
        assert r.status_code == 200
        assert 'mock-injected' in r.text
        with pytest.raises(ValueError):
            r.json()
        # 控制端点不受协议错误注入影响
        assert requests.get(f'{base}/__control', timeout=5).status_code == 200

    def test_control_rejects_invalid_behavior(self, judge_clean):
        base = judge_clean.base_url
        r = requests.post(f'{base}/__control',
                          json={'protocol_error': 'carrier_pigeon'}, timeout=5)
        assert r.status_code == 400 and '非法 protocol_error' in r.json()['msg']
        r = requests.post(f'{base}/__control', json={'no_such_field': 1}, timeout=5)
        assert r.status_code == 400 and '未知行为字段' in r.json()['msg']

    def test_score_mode_fixed_and_random(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control', json={'fixed_score': 0.7}, timeout=5)
        eval_task_id = _create_task(base)
        result = requests.get(f'{base}/api/get_final_result/{eval_task_id}',
                              timeout=5).json()['data']['result']
        assert result['逐轮话轮评估'] == 0.7
        assert result['per_round'][0]['逐轮话轮评估'] == 0.7

        requests.post(f'{base}/__control', json={'score_mode': 'random'}, timeout=5)
        eval_task_id = _create_task(base)
        result = requests.get(f'{base}/api/get_final_result/{eval_task_id}',
                              timeout=5).json()['data']['result']
        assert 0.6 <= result['逐轮话轮评估'] <= 0.99

    def test_per_round_shape_injection(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control', json={'per_round_rounds': 3}, timeout=5)
        result = requests.get(f'{base}/api/get_final_result/eval-any',
                              timeout=5).json()['data']['result']
        assert [p['round_number'] for p in result['per_round']] == [0, 1, 2]

        requests.post(f'{base}/__control', json={'per_round_rounds': 0}, timeout=5)
        result = requests.get(f'{base}/api/get_final_result/eval-any',
                              timeout=5).json()['data']['result']
        assert 'per_round' not in result

    def test_delay_injection(self, judge_clean):
        base = judge_clean.base_url
        requests.post(f'{base}/__control', json={'delay_ms': 300}, timeout=5)
        started = time.monotonic()
        requests.post(f'{base}/api/create_task', json={}, timeout=10)
        elapsed = time.monotonic() - started
        assert elapsed >= 0.3, f'延迟注入未生效（耗时 {elapsed:.2f}s）'

    def test_control_snapshot_and_reset(self, judge_clean):
        base = judge_clean.base_url
        _create_task(base)
        snapshot = requests.get(f'{base}/__control', timeout=5).json()
        assert snapshot['behavior']['fixed_score'] == 0.85
        assert len(snapshot['state']['tasks']) == 1

        requests.post(f'{base}/__control/reset', timeout=5)
        snapshot = requests.get(f'{base}/__control', timeout=5).json()
        assert snapshot['state']['tasks'] == {}
        assert snapshot['state']['hits'] == {}


class TestMockJudgeBehaviorConfig:
    """行为配置 enum 化 fail-closed（禁魔法字符串）。"""

    def test_validate_rejects_invalid(self):
        # 校验入口是 update()（对齐 MockEvalBehavior 模式，构造器不校验）
        for changes in (
            {'score_mode': 'carrier_pigeon'},
            {'fail_mode': 'carrier_pigeon'},
            {'protocol_error': 'carrier_pigeon'},
            {'delay_ms': -1},
            {'per_round_rounds': 1000},
            {'running_polls': -1},
        ):
            with pytest.raises(ValueError):
                MockJudgeBehavior().update(changes)

    def test_update_fail_closed(self):
        behavior = MockJudgeBehavior()
        with pytest.raises(ValueError):
            behavior.update({'no_such_field': 1})
        with pytest.raises(ValueError):
            behavior.update({'fixed_score': 0.7, 'fail_mode': 'carrier_pigeon'})
        # 整体拒绝：合法字段未被部分写入
        assert behavior.fixed_score == 0.85
        assert behavior.fail_mode == 'none'


# ================= presigned 两步失败注入补齐（INT-137 注 B 缺口，INT-182） =================
@pytest.fixture(scope='module')
def eval_mock():
    server = MockEvalServer(MockEvalBehavior())
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture()
def eval_clean(eval_mock):
    eval_mock.service.behavior = MockEvalBehavior()
    eval_mock.service.state.reset()
    yield eval_mock
    eval_mock.service.behavior = MockEvalBehavior()
    eval_mock.service.state.reset()


def _presign_bundle(transfer_id):
    return EvalRequestBundle(
        transfer_id=transfer_id,
        form_fields={'task_type': 'llm_judge', 'prompt': '评分', 'threshold': 0.6},
        files={'record_file': EvalRequestFile(name='record_file', filename='a.wav',
                                              content=AUDIO_BYTES, content_type='audio/wav')},
    )


class TestPresignedFailureInjection:
    """presigned /upload-url 与 PUT /upload/{seq} 失败注入（真实 C 端出站腿收敛）。"""

    def test_first_5xx_three_steps_each_recover_on_retry(self, eval_clean):
        server = eval_clean
        requests.post(f'{server.base_url}/__control?fail_mode=first_5xx', timeout=5)
        client = ThirdPartyCAPIClient(base_url=server.base_url, timeout_seconds=10,
                                      max_retries=3, backoff_seconds=0.05)

        outcome = client.deliver('presigned_url', _presign_bundle('int182-presign-1'))

        # 三步各自首次 5xx → C 端指数退避重试 → 全链收敛
        assert outcome.delivered and outcome.body['code'] == 0
        assert outcome.body['data']['result']['score'] == 0.92
        assert outcome.attempts == 2
        # upload-url / PUT / evaluate 计数键相互独立，各自恰好命中两次
        assert server.service.state.hits['__upload_url__int182-presign-1'] == 2
        upload_path = next(iter(server.service.state.uploads))
        assert server.service.state.hits[f'__upload__{upload_path}'] == 2
        assert server.service.state.hits['int182-presign-1'] == 2
        # PUT 上传字节与源文件一致
        assert AUDIO_BYTES in list(server.service.state.uploads.values())

    def test_upload_url_always_4xx_no_retry(self, eval_clean):
        server = eval_clean
        requests.post(f'{server.base_url}/__control?fail_mode=always_4xx', timeout=5)
        client = ThirdPartyCAPIClient(base_url=server.base_url, timeout_seconds=10,
                                      max_retries=3, backoff_seconds=0.05)

        outcome = client.deliver('presigned_url', _presign_bundle('int182-presign-2'))

        # 4xx 不重试（恰好一次）→ 上传两步未发生
        assert not outcome.delivered and outcome.dst_status == 400
        assert server.service.state.hits['__upload_url__int182-presign-2'] == 1
        assert not server.service.state.uploads
