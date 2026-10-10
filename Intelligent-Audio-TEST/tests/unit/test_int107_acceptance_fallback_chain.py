# -*- coding: utf-8 -*-
"""INT-107 验收补充测试——测试工程师独立验收。

开发侧 tests/unit/test_int107_evaluation_report_quality.py 全程 mock 网络层与 ACL；
本文件在关键链路上用真实组件独立复核提测评论「建议测试点」：

建议测试点 1（真实 HTTP）：
  主端点不可达 + EVAL_FALLBACK_URLS 指向本地替身 → 兜底端点真实出分，
  日志出现「兜底端点 … 评估成功」；不配置兜底 → 连接级错误原样保留，
  且 compose_case_error_message 对真实 ConnectTimeout 文案聚合出非空去重摘要
  （即落 task_case_relations.error_message 的内容，不再空串）。

建议测试点 2（真实 HTTP）：
  业务级失败（替身返回 HTTP 400 / 评估任务执行 failed）→ 不切换端点，
  兜底替身零请求，错误不带 __error_kind__=connection。

缺陷① 服务端契约（真 sqlite）：
  task_repository.update_task_case_status 非空 error_message 落库、
  空串不覆盖既有值——评估侧修复依赖该契约，开发自测未覆盖真库行为。
"""
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest


# ============================================================
# 本地 eval_server 替身（真实 HTTP，动态端口）
# ============================================================

class _StubEvalServer:
    """最小 eval_server 替身：实现 create_task / get_status / get_final_result 异步协议。

    mode:
      ok           创建成功→completed→返回 {"score": 88.5}
      create_400   创建任务返回 HTTP 400（业务级失败）
      task_failed  创建成功但轮询状态为 failed（评估任务执行失败，业务级）
    记录收到的每个请求 (method, path)，供「未切换端点」断言。
    """

    def __init__(self, mode='ok'):
        self.mode = mode
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, obj, status=200):
                body = json.dumps(obj).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                outer.requests.append(('POST', self.path))
                if self.path == '/api/create_task':
                    if outer.mode == 'create_400':
                        return self._json({'code': 400, 'msg': 'bad request'}, status=400)
                    return self._json({'code': 0, 'data': {'eval_task_id': 'et-int107-1'}})
                return self._json({'code': 404, 'msg': 'not found'}, status=404)

            def do_GET(self):
                outer.requests.append(('GET', self.path))
                if self.path.startswith('/api/get_status/'):
                    if outer.mode == 'task_failed':
                        return self._json({'code': 0, 'data': {
                            'status': 'failed', 'error_msg': 'ASR engine crashed'}})
                    return self._json({'code': 0, 'data': {'status': 'completed'}})
                if self.path.startswith('/api/get_final_result/'):
                    return self._json({'code': 0, 'data': {
                        'result': {'score': 88.5, 'wer': 0.115}}})
                return self._json({'code': 404, 'msg': 'not found'}, status=404)

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self._server.server_address[1]}'
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    @property
    def create_task_calls(self):
        return [r for r in self.requests if r == ('POST', '/api/create_task')]


def _unreachable_url():
    """取一个当前无监听的 127.0.0.1 端口（连接立即被拒，不超时）。"""
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return f'http://127.0.0.1:{port}'


class _LogCapture:
    """替换客户端实例的 _log，同时验证提测要求的日志内容。"""

    def __init__(self):
        self.entries = []

    def __call__(self, *args, **kwargs):
        content = kwargs.get('content')
        if content is None and len(args) >= 2:
            content = args[1]
        self.entries.append(str(content or ''))

    def has(self, *fragments):
        return any(all(f in e for f in fragments) for e in self.entries)


def _make_client(log_capture):
    from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import (
        evaluationApiClient,
    )

    client = evaluationApiClient()
    client._log = log_capture
    return client


def _call_with_fallback(client, api_url, endpoints=None, payload=None):
    return client.make_api_request_with_fallback(
        endpoints=endpoints or [], method='POST', headers={},
        payload=payload if payload is not None else {'text': '你好'},
        task_id=9107, dim_names=['wer'], api_url=api_url,
        test_case_id='int107-acc-case', api_id=None,
        dim_info={'task_type_code': 'wer'},
    )


@pytest.fixture
def stub():
    server = _StubEvalServer()
    server.start()
    yield server
    server.stop()


# ============================================================
# 建议测试点 1：兜底端点真实出分 / 不配置时错误保留并可聚合
# ============================================================

class TestFallbackProducesScore:
    def test_unreachable_primary_with_fallback_config_produces_score(self, monkeypatch, stub):
        """主端点不可达 + EVAL_FALLBACK_URLS=替身 → 真实 HTTP 链路兜底出分。"""
        monkeypatch.setenv('EVAL_FALLBACK_URLS', stub.url)
        logs = _LogCapture()
        client = _make_client(logs)
        primary = _unreachable_url()

        selected_url, resp = _call_with_fallback(client, primary)

        assert selected_url == stub.url
        assert resp == {'score': 88.5, 'wer': 0.115}
        assert '__error__' not in resp
        # 兜底动作可观察（提测要求：日志出现「兜底端点 … 评估成功」）
        assert logs.has('兜底端点', '评估成功'), logs.entries
        # 替身确实走完异步协议：create → status → final_result
        assert stub.create_task_calls

    def test_unreachable_primary_without_config_error_preserved_and_summarizable(self, monkeypatch):
        """不配置兜底 → 连接级错误原样保留（不再静默），且能聚合成用例级摘要。"""
        monkeypatch.delenv('EVAL_FALLBACK_URLS', raising=False)
        logs = _LogCapture()
        client = _make_client(logs)
        primary = _unreachable_url()

        selected_url, resp = _call_with_fallback(client, primary)

        assert selected_url == primary
        assert '__error__' in resp
        assert resp.get('__error_kind__') == 'connection'
        # 真实连接错误文案可被 compose_case_error_message 聚合为非空去重摘要
        from evaluation_service.domain.services.evaluation_utils import (
            compose_case_error_message,
        )
        summary = compose_case_error_message([resp['__error__']] * 6)
        assert summary.startswith('维度评估失败: ')
        assert '127.0.0.1' in summary
        # 6 条相同文案去重后仅保留一条（真实文案中 host 出现 2 次属正常）
        assert summary.count('Max retries exceeded') == 1

    def test_all_endpoints_unreachable_keeps_primary_error_kind(self, monkeypatch):
        """主端点与全部兜底端点均不可达 → 保留主端点连接级错误与标记。"""
        monkeypatch.setenv('EVAL_FALLBACK_URLS', _unreachable_url())
        logs = _LogCapture()
        client = _make_client(logs)
        primary = _unreachable_url()

        selected_url, resp = _call_with_fallback(client, primary)

        assert selected_url == primary
        assert resp.get('__error_kind__') == 'connection'
        assert logs.has('均不可达'), logs.entries


# ============================================================
# 建议测试点 2：业务级失败不切换端点
# ============================================================

class TestBusinessFailureNoSwitch:
    def test_http_400_create_does_not_switch_endpoint(self, monkeypatch):
        """创建任务返回 HTTP 400（业务级）→ 不切换端点，兜底零请求。"""
        primary_stub = _StubEvalServer(mode='create_400')
        primary_stub.start()
        fallback_stub = _StubEvalServer()
        fallback_stub.start()
        try:
            monkeypatch.setenv('EVAL_FALLBACK_URLS', fallback_stub.url)
            logs = _LogCapture()
            client = _make_client(logs)

            selected_url, resp = _call_with_fallback(client, primary_stub.url)

            assert selected_url == primary_stub.url
            assert '__error__' in resp
            assert '400' in resp['__error__']
            assert resp.get('__error_kind__') is None
            assert fallback_stub.requests == []
            assert logs.has('兜底端点') is False
        finally:
            primary_stub.stop()
            fallback_stub.stop()

    def test_eval_task_failed_does_not_switch_endpoint(self, monkeypatch):
        """评估任务执行失败（轮询 status=failed，业务级）→ 不切换端点。"""
        primary_stub = _StubEvalServer(mode='task_failed')
        primary_stub.start()
        fallback_stub = _StubEvalServer()
        fallback_stub.start()
        try:
            monkeypatch.setenv('EVAL_FALLBACK_URLS', fallback_stub.url)
            client = _make_client(_LogCapture())

            selected_url, resp = _call_with_fallback(client, primary_stub.url)

            assert selected_url == primary_stub.url
            assert '__error__' in resp
            assert resp.get('__error_kind__') is None
            assert fallback_stub.requests == []
        finally:
            primary_stub.stop()
            fallback_stub.stop()


# ============================================================
# 缺陷① 服务端契约（真 sqlite）：非空落库 / 空串不覆盖
# ============================================================

@pytest.fixture(scope='module')
def int107_db():
    from shared.models.database import Base, get_engine, init_db, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import TaskCase

    init_db(pool_size=2)
    Base.metadata.create_all(bind=get_engine(), tables=[TaskCase.__table__])
    yield
    remove_db_session()


def _seed_task_case(task_id, case_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import TaskCase

    session = get_db_session()
    try:
        if not session.query(TaskCase).filter_by(
                task_id=task_id, test_case_id=case_id).first():
            session.add(TaskCase(
                task_id=task_id, test_case_id=case_id,
                status='running', execution_status='completed',
                evaluation_status='failed'))
        session.commit()
    finally:
        remove_db_session()


def _get_case_error_message(task_id, case_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import TaskCase

    session = get_db_session()
    try:
        row = session.query(TaskCase).filter_by(
            task_id=task_id, test_case_id=case_id).first()
        return row.error_message
    finally:
        remove_db_session()


class TestServerSideErrorMessageContract:
    """评估侧修复依赖的服务端契约：仅非空写入 error_message。"""

    TASK_ID = 91070001
    CASE_ID = 'int107-acc-contr'

    def test_nonempty_error_message_persists(self, int107_db):
        from task_service.infrastructure.persistence.task_repository import (
            task_repository,
        )

        _seed_task_case(self.TASK_ID, self.CASE_ID)
        reason = '维度评估失败: HTTPConnectionPool: Max retries exceeded (ConnectTimeout)'

        ok = task_repository.update_task_case_status(
            self.TASK_ID, self.CASE_ID,
            status='failed', evaluation_status='failed',
            error_message=reason)

        assert ok is True
        assert _get_case_error_message(self.TASK_ID, self.CASE_ID) == reason

    def test_empty_error_message_does_not_overwrite(self, int107_db):
        from task_service.infrastructure.persistence.task_repository import (
            task_repository,
        )

        ok = task_repository.update_task_case_status(
            self.TASK_ID, self.CASE_ID,
            status='failed', evaluation_status='failed',
            error_message='')

        assert ok is True
        assert _get_case_error_message(self.TASK_ID, self.CASE_ID) == (
            '维度评估失败: HTTPConnectionPool: Max retries exceeded (ConnectTimeout)')
