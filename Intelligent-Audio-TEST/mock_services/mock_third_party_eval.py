# -*- coding: utf-8 -*-
"""Mock 第三方评估服务 — C 区替身（INT-137，仅联调/验收/回归用）。

契约对齐（生产客户端，勿改 mock 侧以外的契约）：
- 出站投递客户端：transfer_agent/infrastructure/acl/c_api_client.py（§4.3 三契约）
- EVAL_RESULT schema：与既有集成测试"本地模拟 C 区三契约端点"一致
  （tests/integration/test_third_party_eval_chain.py）：
  {'code': 0, 'msg': 'ok', 'data': {'result': {'score': <float>, 'value': '<str>'}}}

三契约端点：
- multipart        POST /evaluate   multipart/form-data（fields + files，transfer_id 字段）
- feature_extract  POST /evaluate   JSON {transfer_id, fields, features}
- presigned_url    POST /upload-url → PUT /upload/{seq} → POST /evaluate
                                    JSON {transfer_id, fields, objects}

行为可配置（优先级：命令行 > 环境变量 MOCK_EVAL_* > 配置文件 > 默认值），
运行中可经控制端点热更新（无需重启）：
- GET  /__control              查看当前行为与状态（命中计数 / 已存结果 / 最近请求）
- POST /__control              JSON body 或查询参数热更新行为（?delay_ms=200&fail_mode=first_5xx）
- POST /__control/reset        清空状态（命中计数 / 幂等结果 / 最近请求）
- GET  /health                 健康检查

注入场景：
- 延迟         behavior.delay_ms（响应前 sleep）
- 5xx 重试退避 behavior.fail_mode=first_5xx（每 transfer_id 首次 5xx，重试成功）
               behavior.fail_mode=always_5xx（持续 5xx，重试耗尽收敛）
- 4xx 不重试   behavior.fail_mode=always_4xx
- 幂等去重     behavior.idempotent_dedup=true 时同 transfer_id 重复请求回放同结果
- 分数模式     behavior.score_mode=fixed|random（fixed_score）
- presigned 两步失败注入（INT-182 补齐 INT-137 注 B 缺口）：fail_mode 同样作用于
  POST /upload-url（计数键 __upload_url__{transfer_id}）与 PUT /upload/{seq}
  （计数键 __upload__{path}），与 /evaluate（按 transfer_id 计数）相互独立

独立可运行（仅标准库，不依赖仓库其余代码；端口取 shared/config/service_ports.py 注册值）：
    python mock_services/mock_third_party_eval.py [--port 5099] [行为参数...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, asdict, field
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 端口唯一来源：service_ports 注册表（独立运行时回退仓库根导入）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config.service_ports import MOCK_THIRD_PARTY_EVAL_HTTP_PORT  # noqa: E402

DEFAULT_PORT = MOCK_THIRD_PARTY_EVAL_HTTP_PORT

# EVAL_RESULT 必备形态（与既有集成测试本地 C 区模拟端点一致，勿新造 schema）
OK_MSG = 'ok'


class MockScoreMode(str, Enum):
    """分数模式：固定分数 / 随机分数。"""
    FIXED = 'fixed'
    RANDOM = 'random'


class MockFailMode(str, Enum):
    """失败注入模式：无 / 每 transfer_id 首次 5xx（重试退避）/ 持续 5xx / 持续 4xx（不重试）。"""
    NONE = 'none'
    FIRST_5XX = 'first_5xx'
    ALWAYS_5XX = 'always_5xx'
    ALWAYS_4XX = 'always_4xx'


class MockEvalForm(str, Enum):
    """已接收的请求契约形态（观测记录用）。"""
    MULTIPART = 'multipart'
    FEATURE_EXTRACT = 'feature_extract'
    PRESIGNED_URL = 'presigned_url'
    UPLOAD = 'upload'


@dataclass
class MockEvalBehavior:
    """mock 行为配置（enum 化 + 配置文件 + 命令行 + 控制端点热更新，禁魔法字符串）。"""
    score_mode: str = MockScoreMode.FIXED.value
    fixed_score: float = 0.92
    delay_ms: int = 0
    fail_mode: str = MockFailMode.NONE.value
    fail_status: int = 500
    idempotent_dedup: bool = True

    def validate(self) -> None:
        if self.score_mode not in (m.value for m in MockScoreMode):
            raise ValueError(f'非法 score_mode: {self.score_mode}'
                             f'（允许 {", ".join(m.value for m in MockScoreMode)}）')
        if self.fail_mode not in (m.value for m in MockFailMode):
            raise ValueError(f'非法 fail_mode: {self.fail_mode}'
                             f'（允许 {", ".join(m.value for m in MockFailMode)}）')
        if self.delay_ms < 0 or self.delay_ms > 60000:
            raise ValueError(f'非法 delay_ms: {self.delay_ms}（允许 0~60000）')
        if self.fail_status < 400 or self.fail_status > 599:
            raise ValueError(f'非法 fail_status: {self.fail_status}（允许 400~599）')

    def update(self, changes: dict) -> None:
        """部分字段热更新（控制端点入口），非法值 fail-closed 整体拒绝。"""
        allowed = {'score_mode', 'fixed_score', 'delay_ms', 'fail_mode',
                   'fail_status', 'idempotent_dedup'}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f'未知行为字段: {sorted(unknown)}（允许 {sorted(allowed)}）')
        candidate = MockEvalBehavior(**{**asdict(self), **changes})
        candidate.validate()
        for key, value in asdict(candidate).items():
            setattr(self, key, value)

    @classmethod
    def from_env(cls) -> 'MockEvalBehavior':
        prefix = 'MOCK_EVAL_'
        mapping = {
            'score_mode': str, 'fixed_score': float, 'delay_ms': int,
            'fail_mode': str, 'fail_status': int, 'idempotent_dedup': _env_bool,
        }
        kwargs = {}
        for key, cast in mapping.items():
            raw = os.environ.get(prefix + key.upper())
            if raw is not None and raw != '':
                kwargs[key] = cast(raw)
        return cls(**kwargs)

    @classmethod
    def from_config_file(cls, path: str) -> 'MockEvalBehavior':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        behavior = data.get('behavior') or data
        return cls(**behavior)


def _env_bool(raw: str) -> bool:
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class MockEvalState:
    """服务端可观测状态（幂等去重结果 / 命中计数 / 最近请求证据）。"""
    hits: dict = field(default_factory=dict)          # transfer_id -> 次数
    results: dict = field(default_factory=dict)       # transfer_id -> 回放结果（幂等去重）
    presigned: dict = field(default_factory=dict)     # transfer_id -> upload-url 请求列表
    uploads: dict = field(default_factory=dict)       # /upload/{seq} -> bytes
    last_request: dict = field(default_factory=dict)  # 最近一次 /evaluate 观测
    upload_seq: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()
            self.results.clear()
            self.presigned.clear()
            self.uploads.clear()
            self.last_request.clear()
            self.upload_seq = 0

    def snapshot(self) -> dict:
        with self.lock:
            return {
                'hits': dict(self.hits),
                'results': {k: dict(v) for k, v in self.results.items()},
                'presigned': {k: list(v) for k, v in self.presigned.items()},
                'upload_count': len(self.uploads),
                'last_request': dict(self.last_request),
            }


def parse_multipart(body: bytes, content_type: str):
    """解析 multipart/form-data（与 requests 出站形态对齐，集成测试同源逻辑）。"""
    boundary = content_type.split('boundary=', 1)[1].split(';', 1)[0].strip().encode()
    parts = body.split(b'--' + boundary)
    fields, files = {}, {}
    for part in parts[1:-1]:
        part = part.lstrip(b'\r\n')
        if not part or part == b'--':
            continue
        header_blob, _, content = part.partition(b'\r\n\r\n')
        if content.endswith(b'\r\n'):
            content = content[:-2]
        disposition = ''
        for line in header_blob.split(b'\r\n'):
            key, _, value = line.partition(b':')
            if key.decode(errors='replace').strip().lower() == 'content-disposition':
                disposition = value.decode(errors='replace').strip()

        def _attr(name):
            match = re.search(f'{name}="([^"]*)"', disposition)
            return match.group(1) if match else None

        field_name = _attr('name')
        if field_name is None:
            continue
        if _attr('filename'):
            files[field_name] = content
        else:
            fields[field_name] = content.decode('utf-8')
    return fields, files


def build_eval_result(behavior: MockEvalBehavior) -> dict:
    """生成一次合法 EVAL_RESULT（schema 与既有集成测试本地 C 区模拟端点一致）。"""
    if behavior.score_mode == MockScoreMode.RANDOM.value:
        score = round(random.uniform(0.6, 0.99), 2)
    else:
        score = float(behavior.fixed_score)
    return {'code': 0, 'msg': OK_MSG,
            'data': {'result': {'score': score, 'value': str(score)}}}


class MockEvalService:
    """行为与状态的持有者（Handler 与控制端点共享）。"""

    def __init__(self, behavior: MockEvalBehavior):
        self.behavior = behavior
        self.state = MockEvalState()

    # ---- 失败/延迟注入判定 ----
    def _maybe_inject(self, transfer_id: str) -> bool:
        """返回 True 表示本次命中被失败注入终结（已写响应）。"""
        behavior = self.behavior
        fail_mode = MockFailMode(behavior.fail_mode)
        if fail_mode == MockFailMode.NONE:
            return False
        with self.state.lock:
            hits = self.state.hits.get(transfer_id, 0)
        if fail_mode == MockFailMode.FIRST_5XX and hits > 1:
            return False
        return True  # first_5xx 首次 / always_* 每次均注入

    def record_hit(self, transfer_id: str) -> int:
        with self.state.lock:
            self.state.hits[transfer_id] = self.state.hits.get(transfer_id, 0) + 1
            return self.state.hits[transfer_id]

    def fail_response(self) -> dict:
        """失败注入响应体（{'__status__', '__body__'} 由 Handler 落为原始 HTTP 响应）。"""
        fail_mode = MockFailMode(self.behavior.fail_mode)
        if fail_mode == MockFailMode.ALWAYS_4XX:
            return {'__status__': 400,
                    '__body__': {'code': 400, 'msg': 'mock 注入：持续 4xx（不重试语义）'}}
        return {'__status__': int(self.behavior.fail_status),
                '__body__': {'code': int(self.behavior.fail_status),
                             'msg': 'mock 注入：5xx（重试退避语义）'}}

    def evaluate(self, form: MockEvalForm, transfer_id: str, fields: dict,
                 files: dict, features=None, objects=None) -> dict:
        """评估主流程（三契约统一入口）：注入判定 → 幂等去重 → 生成结果。"""
        hit = self.record_hit(transfer_id)
        with self.state.lock:
            self.state.last_request = {
                'form': form.value,
                'transfer_id': transfer_id,
                'fields': dict(fields),
                'files': {name: hashlib.sha256(content).hexdigest()
                          for name, content in (files or {}).items()},
                'features': features or {},
                'objects': objects or {},
                'hit': hit,
            }
        if self._maybe_inject(transfer_id):
            return self.fail_response()
        with self.state.lock:
            cached = self.state.results.get(transfer_id) \
                if self.behavior.idempotent_dedup else None
        if cached is not None:
            return cached
        result = build_eval_result(self.behavior)
        if self.behavior.idempotent_dedup:
            with self.state.lock:
                self.state.results[transfer_id] = result
        return result

    def snapshot(self) -> dict:
        return {'behavior': asdict(self.behavior), 'state': self.state.snapshot()}


class MockEvalRequestHandler(BaseHTTPRequestHandler):
    """HTTP Handler：三契约端点 + health + 控制端点（server.service 注入共享服务）。"""

    def log_message(self, *args):  # 静默默认访问日志（运行日志由 main 打关键行）
        pass

    # ---- 基础 ----
    @property
    def service(self) -> MockEvalService:
        return self.server.service

    def _reply(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(length) if length > 0 else b''

    def _apply_delay(self) -> None:
        delay_ms = self.service.behavior.delay_ms
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    # ---- GET ----
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == '/health':
            self._reply(200, {'status': 'ok', 'service': 'mock_third_party_eval'})
        elif path == '/__control':
            self._reply(200, self.service.snapshot())
        else:
            self._reply(404, {'code': 404, 'msg': 'not found'})

    # ---- POST ----
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == '/evaluate':
            self._handle_evaluate()
        elif path == '/upload-url':
            self._handle_upload_url()
        elif path == '/__control':
            self._handle_control(parsed.query)
        elif path == '/__control/reset':
            self.service.state.reset()
            self._reply(200, {'status': 'reset', 'snapshot': self.service.snapshot()})
        else:
            self._reply(404, {'code': 404, 'msg': 'not found'})

    def _handle_evaluate(self):
        self._apply_delay()
        content_type = self.headers.get('Content-Type', '')
        body = self._read_body()
        if content_type.startswith('multipart/form-data'):
            fields, files = parse_multipart(body, content_type)
            transfer_id = str(fields.pop('transfer_id', '') or '')
            result = self.service.evaluate(MockEvalForm.MULTIPART, transfer_id,
                                           fields, files)
        else:
            payload = json.loads(body or b'{}')
            transfer_id = str(payload.get('transfer_id') or '')
            if 'features' in payload:
                form = MockEvalForm.FEATURE_EXTRACT
            elif 'objects' in payload:
                form = MockEvalForm.PRESIGNED_URL
            else:
                form = MockEvalForm.FEATURE_EXTRACT
            result = self.service.evaluate(
                form, transfer_id, dict(payload.get('fields') or {}),
                {}, features=payload.get('features') or {},
                objects=payload.get('objects') or {})
        status = result.pop('__status__', None)
        if status is not None:
            self._reply(status, result.get('__body__'))
        else:
            self._reply(200, result)

    def _handle_upload_url(self):
        self._apply_delay()
        payload = json.loads(self._read_body() or b'{}')
        transfer_id = str(payload.get('transfer_id') or '')
        # 失败注入（INT-182 补齐注 B 缺口）：upload-url 步按 transfer_id 独立计数
        hit_key = f'__upload_url__{transfer_id}'
        self.service.record_hit(hit_key)
        if self.service._maybe_inject(hit_key):
            injected = self.service.fail_response()
            self._reply(injected.pop('__status__'), injected.get('__body__'))
            return
        with self.service.state.lock:
            self.service.state.upload_seq += 1
            seq = self.service.state.upload_seq
            self.service.state.presigned.setdefault(transfer_id, []).append(payload)
        host, port = self.server.server_address[:2]
        if host in ('0.0.0.0', '::'):
            # 通配绑定时对外可达地址是回环（standalone 部署形态）
            host = '127.0.0.1'
        self._reply(200, {'upload_url': f'http://{host}:{port}/upload/{seq}',
                          'object_ref': f'obj-{seq}'})

    def _handle_control(self, query: str):
        body = self._read_body()
        changes = {}
        if body:
            try:
                changes.update(json.loads(body) or {})
            except ValueError:
                self._reply(400, {'code': 400, 'msg': 'JSON body 非法'})
                return
        # 查询参数覆盖 JSON body（查询参数即注入入口：?fail_mode=first_5xx&delay_ms=200）
        casters = {'fixed_score': float, 'delay_ms': int, 'fail_status': int,
                   'idempotent_dedup': _env_bool}
        for key, values in urllib.parse.parse_qs(query).items():
            raw = values[-1]
            changes[key] = casters[key](raw) if key in casters else raw
        if not changes:
            self._reply(200, self.service.snapshot())
            return
        try:
            self.service.behavior.update(changes)
        except ValueError as e:
            self._reply(400, {'code': 400, 'msg': str(e)})
            return
        self._reply(200, self.service.snapshot())

    # ---- PUT ----
    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/upload/'):
            self._apply_delay()
            content = self._read_body()
            with self.service.state.lock:
                self.service.state.uploads[path] = content
            # 失败注入（INT-182 补齐注 B 缺口）：PUT 步按上传路径独立计数
            hit_key = f'__upload__{path}'
            self.service.record_hit(hit_key)
            if self.service._maybe_inject(hit_key):
                injected = self.service.fail_response()
                self._reply(injected.pop('__status__'), injected.get('__body__'))
                return
            self._reply(200, {'code': 0, 'msg': OK_MSG})
        else:
            self._reply(404, {'code': 404, 'msg': 'not found'})


class MockEvalServer:
    """可编程启停的 mock 评估服务（进程内测试 / 独立进程运行共用）。"""

    def __init__(self, behavior: MockEvalBehavior = None, host: str = '127.0.0.1',
                 port: int = 0):
        self.service = MockEvalService(behavior or MockEvalBehavior())
        self._httpd = ThreadingHTTPServer((host, port), MockEvalRequestHandler)
        self._httpd.service = self.service
        self.host, self.port = self._httpd.server_address[:2]

    @property
    def base_url(self) -> str:
        return f'http://{self.host}:{self.port}'

    def start(self):
        thread = threading.Thread(target=self._httpd.serve_forever, daemon=True,
                                  name='mock-third-party-eval')
        thread.start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()

    def serve_forever(self):
        self._httpd.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Mock 第三方评估服务（C 区替身）')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--config', default='',
                        help='行为配置文件（JSON，behavior 段；优先级低于命令行与环境变量）')
    parser.add_argument('--score-mode', choices=[m.value for m in MockScoreMode])
    parser.add_argument('--fixed-score', type=float)
    parser.add_argument('--delay-ms', type=int)
    parser.add_argument('--fail-mode', choices=[m.value for m in MockFailMode])
    parser.add_argument('--fail-status', type=int)
    parser.add_argument('--no-idempotent-dedup', action='store_true',
                        help='关闭按 transfer_id 幂等去重（重复请求各自生成结果）')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    behavior = (MockEvalBehavior.from_config_file(args.config)
                if args.config else MockEvalBehavior.from_env())
    cli_changes = {}
    if args.score_mode:
        cli_changes['score_mode'] = args.score_mode
    if args.fixed_score is not None:
        cli_changes['fixed_score'] = args.fixed_score
    if args.delay_ms is not None:
        cli_changes['delay_ms'] = args.delay_ms
    if args.fail_mode:
        cli_changes['fail_mode'] = args.fail_mode
    if args.fail_status is not None:
        cli_changes['fail_status'] = args.fail_status
    if args.no_idempotent_dedup:
        cli_changes['idempotent_dedup'] = False
    if cli_changes:
        behavior.update(cli_changes)

    server = MockEvalServer(behavior, host=args.host, port=args.port)
    print(f'[mock_third_party_eval] listening on http://{args.host}:{server.port} '
          f'behavior={asdict(behavior)}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
