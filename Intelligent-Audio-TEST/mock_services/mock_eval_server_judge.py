# -*- coding: utf-8 -*-
"""Mock eval_server 裁判端点替身 — 评估链第二条上游替身（INT-182，仅联调/验收/回归用）。

透传/模拟语义：本服务为纯模拟替身（无任何透传）——模拟真实 eval_server 的异步
任务协议与 llm_judge 结果产出，评分/延迟/失败/协议错误全部可注入，供
evaluation_service 出站评估链路（evaluationApiClient → eval_server）在无真实
eval_server 环境下完成联调、验收与回归。生产路径零引用。

契约对齐（生产客户端，勿改 mock 侧以外的契约）：
- 出站评估客户端：evaluation_service/infrastructure/evaluation_api/api_request_handler.py
  - POST {url}/api/create_task          JSON payload → {'code': 0, 'data': {'eval_task_id': ...}}
  - POST {url}/api/create_task_upload   multipart（fields + files）→ 同上
  - GET  {url}/api/get_status/{id}      → {'code': 0, 'data': {'status': ..., 'progress': N}}
  - GET  {url}/api/get_final_result/{id} → {'code': 0, 'data': {'result': {...}}}
- 结果形态：INT-95 R8 轮 llm_judge 契约（逐轮话轮评估 0.85 / response_latency_ms 850 /
  per_round[0/1]），评分与轮次形态可注入。

行为可配置（优先级：命令行 > 环境变量 MOCK_JUDGE_* > 配置文件 > 默认值），
运行中可经控制端点热更新（无需重启）：
- GET  /__control              查看当前行为与状态（任务表 / 注入计数 / 最近 create 观测）
- POST /__control              JSON body 或查询参数热更新行为（?delay_ms=200&fail_mode=first_5xx）
- POST /__control/reset        清空状态（任务表 / 注入计数 / 最近请求）
- GET  /health                 健康检查

注入场景：
- 延迟（HTTP 层）   behavior.delay_ms（每个协议响应前 sleep，可触发客户端超时）
- 延迟（异步轮询）  behavior.running_polls（前 N 次 get_status 回 running，其后 completed）
- 5xx 重试退避      behavior.fail_mode=first_5xx（每注入键首次 5xx，其后放行）
                    behavior.fail_mode=always_5xx（持续 5xx）+ fail_status
- 4xx 不重试        behavior.fail_mode=always_4xx
                    注入计数键：create 端点共用 '__create__'，get_status /
                    get_final_result 按 eval_task_id，相互独立（/__control/reset 清零）
- 协议错误          behavior.protocol_error=missing_task_id（create 返回 code 0 但缺
                    eval_task_id）/ bad_code（业务码恒 1）/ malformed_json（协议端点回非 JSON
                    文本；协议错误优先于失败注入；控制端点与 /health 不受影响）
- 分数模式          behavior.score_mode=fixed|random（fixed_score，默认 0.85）
- 轮次形态          behavior.per_round_rounds（结果 per_round 轮数，0 = 不带 per_round 键）

独立可运行（仅标准库与 mock_services 包内代码，不依赖仓库其余代码；端口取
shared/config/service_ports.py 注册值）：
    python mock_services/mock_eval_server_judge.py [--port 5097] [行为参数...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass, asdict, field
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 端口唯一来源：service_ports 注册表（独立运行时回退仓库根导入）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config.service_ports import MOCK_EVAL_SERVER_HTTP_PORT  # noqa: E402
from mock_services.mock_third_party_eval import parse_multipart  # noqa: E402

DEFAULT_PORT = MOCK_EVAL_SERVER_HTTP_PORT

OK_MSG = 'success'

# create 端点共享的失败注入计数键（create 无 eval_task_id 可用）
CREATE_HIT_KEY = '__create__'


class MockJudgeScoreMode(str, Enum):
    """评分模式：固定分数 / 随机分数。"""
    FIXED = 'fixed'
    RANDOM = 'random'


class MockJudgeFailMode(str, Enum):
    """失败注入模式：无 / 每注入键首次 5xx（轮询重试收敛）/ 持续 5xx / 持续 4xx（不重试）。"""
    NONE = 'none'
    FIRST_5XX = 'first_5xx'
    ALWAYS_5XX = 'always_5xx'
    ALWAYS_4XX = 'always_4xx'


class MockJudgeProtocolError(str, Enum):
    """协议错误注入模式：无 / create 缺 eval_task_id / 业务码恒 1 / 非 JSON 响应。"""
    NONE = 'none'
    MISSING_TASK_ID = 'missing_task_id'
    BAD_CODE = 'bad_code'
    MALFORMED_JSON = 'malformed_json'


@dataclass
class MockJudgeBehavior:
    """mock 行为配置（enum 化 + 配置文件 + 命令行 + 控制端点热更新，禁魔法字符串）。"""
    score_mode: str = MockJudgeScoreMode.FIXED.value
    fixed_score: float = 0.85
    fixed_latency_ms: int = 850
    delay_ms: int = 0
    fail_mode: str = MockJudgeFailMode.NONE.value
    fail_status: int = 500
    protocol_error: str = MockJudgeProtocolError.NONE.value
    per_round_rounds: int = 2
    running_polls: int = 0

    def validate(self) -> None:
        if self.score_mode not in (m.value for m in MockJudgeScoreMode):
            raise ValueError(f'非法 score_mode: {self.score_mode}'
                             f'（允许 {", ".join(m.value for m in MockJudgeScoreMode)}）')
        if self.fail_mode not in (m.value for m in MockJudgeFailMode):
            raise ValueError(f'非法 fail_mode: {self.fail_mode}'
                             f'（允许 {", ".join(m.value for m in MockJudgeFailMode)}）')
        if self.protocol_error not in (m.value for m in MockJudgeProtocolError):
            raise ValueError(f'非法 protocol_error: {self.protocol_error}'
                             f'（允许 {", ".join(m.value for m in MockJudgeProtocolError)}）')
        if self.delay_ms < 0 or self.delay_ms > 60000:
            raise ValueError(f'非法 delay_ms: {self.delay_ms}（允许 0~60000）')
        if self.fail_status < 400 or self.fail_status > 599:
            raise ValueError(f'非法 fail_status: {self.fail_status}（允许 400~599）')
        if self.fixed_latency_ms < 0 or self.fixed_latency_ms > 600000:
            raise ValueError(f'非法 fixed_latency_ms: {self.fixed_latency_ms}（允许 0~600000）')
        if self.per_round_rounds < 0 or self.per_round_rounds > 100:
            raise ValueError(f'非法 per_round_rounds: {self.per_round_rounds}（允许 0~100）')
        if self.running_polls < 0 or self.running_polls > 1000:
            raise ValueError(f'非法 running_polls: {self.running_polls}（允许 0~1000）')

    def update(self, changes: dict) -> None:
        """部分字段热更新（控制端点入口），非法值 fail-closed 整体拒绝。"""
        allowed = {'score_mode', 'fixed_score', 'fixed_latency_ms', 'delay_ms',
                   'fail_mode', 'fail_status', 'protocol_error',
                   'per_round_rounds', 'running_polls'}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f'未知行为字段: {sorted(unknown)}（允许 {sorted(allowed)}）')
        candidate = MockJudgeBehavior(**{**asdict(self), **changes})
        candidate.validate()
        for key, value in asdict(candidate).items():
            setattr(self, key, value)

    @classmethod
    def from_env(cls) -> 'MockJudgeBehavior':
        prefix = 'MOCK_JUDGE_'
        mapping = {
            'score_mode': str, 'fixed_score': float, 'fixed_latency_ms': int,
            'delay_ms': int, 'fail_mode': str, 'fail_status': int,
            'protocol_error': str, 'per_round_rounds': int, 'running_polls': int,
        }
        kwargs = {}
        for key, cast in mapping.items():
            raw = os.environ.get(prefix + key.upper())
            if raw is not None and raw != '':
                kwargs[key] = cast(raw)
        return cls(**kwargs)

    @classmethod
    def from_config_file(cls, path: str) -> 'MockJudgeBehavior':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        behavior = data.get('behavior') or data
        return cls(**behavior)


@dataclass
class MockJudgeState:
    """服务端可观测状态（任务表 / 注入计数 / 最近 create 观测证据）。"""
    tasks: dict = field(default_factory=dict)         # eval_task_id -> {'polls': int}
    hits: dict = field(default_factory=dict)          # 注入计数键 -> 次数
    last_create: dict = field(default_factory=dict)   # 最近一次 create_task(_upload) 观测
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        with self.lock:
            self.tasks.clear()
            self.hits.clear()
            self.last_create.clear()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                'tasks': {k: dict(v) for k, v in self.tasks.items()},
                'hits': dict(self.hits),
                'last_create': dict(self.last_create),
            }


def build_judge_result(behavior: MockJudgeBehavior) -> dict:
    """生成一次合法 eval_server llm_judge 结果（INT-95 R8 轮契约形态）。"""
    if behavior.score_mode == MockJudgeScoreMode.RANDOM.value:
        score = round(random.uniform(0.6, 0.99), 2)
    else:
        score = float(behavior.fixed_score)
    result = {
        '逐轮话轮评估': score,
        'response_latency_ms': int(behavior.fixed_latency_ms),
        'env_sound_start_ms': 120,
        'env_sound_end_ms': 1500,
        'user_question_end_ms': 2100,
        'model_first_word_start_ms': 2950,
        'ncc': 0.92,
    }
    if behavior.per_round_rounds > 0:
        result['per_round'] = [
            {'round_number': i, '逐轮话轮评估': score,
             'response_latency_ms': int(behavior.fixed_latency_ms)}
            for i in range(behavior.per_round_rounds)
        ]
    return result


class MockJudgeService:
    """行为与状态的持有者（Handler 与控制端点共享）。"""

    def __init__(self, behavior: MockJudgeBehavior):
        self.behavior = behavior
        self.state = MockJudgeState()

    # ---- 失败/延迟注入判定 ----
    def _maybe_inject(self, key: str) -> bool:
        """返回 True 表示本次命中被失败注入终结（fail_mode 语义见模块头）。"""
        fail_mode = MockJudgeFailMode(self.behavior.fail_mode)
        if fail_mode == MockJudgeFailMode.NONE:
            return False
        with self.state.lock:
            hits = self.state.hits.get(key, 0)
        if fail_mode == MockJudgeFailMode.FIRST_5XX and hits > 1:
            return False
        return True  # first_5xx 首次 / always_* 每次均注入

    def record_hit(self, key: str) -> int:
        with self.state.lock:
            self.state.hits[key] = self.state.hits.get(key, 0) + 1
            return self.state.hits[key]

    def fail_response(self) -> dict:
        """失败注入响应体（{'__status__', '__body__'} 由 Handler 落为原始 HTTP 响应）。"""
        fail_mode = MockJudgeFailMode(self.behavior.fail_mode)
        if fail_mode == MockJudgeFailMode.ALWAYS_4XX:
            return {'__status__': 400,
                    '__body__': {'code': 400, 'msg': 'mock 注入：持续 4xx（不重试语义）'}}
        return {'__status__': int(self.behavior.fail_status),
                '__body__': {'code': int(self.behavior.fail_status),
                             'msg': 'mock 注入：5xx（重试退避语义）'}}

    # ---- 异步任务协议（统一注入判定 → 协议错误 → 正常响应）----
    def create_task(self, form: str, fields: dict = None, files: dict = None) -> dict:
        """create_task / create_task_upload 统一入口：发号 eval_task_id。"""
        with self.state.lock:
            self.state.last_create = {
                'form': form,
                'fields': dict(fields or {}),
                'files': {name: hashlib.sha256(content).hexdigest()
                          for name, content in (files or {}).items()},
            }
        self.record_hit(CREATE_HIT_KEY)
        if self._maybe_inject(CREATE_HIT_KEY):
            return self.fail_response()
        if (MockJudgeProtocolError(self.behavior.protocol_error)
                == MockJudgeProtocolError.MISSING_TASK_ID):
            return {'code': 0, 'msg': OK_MSG, 'data': {}}
        if (MockJudgeProtocolError(self.behavior.protocol_error)
                == MockJudgeProtocolError.BAD_CODE):
            return {'code': 1, 'msg': 'mock 注入：协议错误 bad_code', 'data': {}}
        eval_task_id = f'eval-{uuid.uuid4().hex[:8]}'
        with self.state.lock:
            self.state.tasks[eval_task_id] = {'polls': 0}
        return {'code': 0, 'msg': OK_MSG, 'data': {'eval_task_id': eval_task_id}}

    def get_status(self, eval_task_id: str) -> dict:
        self.record_hit(eval_task_id)
        if self._maybe_inject(eval_task_id):
            return self.fail_response()
        if (MockJudgeProtocolError(self.behavior.protocol_error)
                == MockJudgeProtocolError.BAD_CODE):
            return {'code': 1, 'msg': 'mock 注入：协议错误 bad_code', 'data': {}}
        with self.state.lock:
            task = self.state.tasks.setdefault(eval_task_id, {'polls': 0})
            task['polls'] += 1
            polls = task['polls']
        if polls <= self.behavior.running_polls:
            status, progress = 'running', min(99, polls * 10)
        else:
            status, progress = 'completed', 100
        return {'code': 0, 'msg': OK_MSG,
                'data': {'status': status, 'progress': progress}}

    def get_final_result(self, eval_task_id: str) -> dict:
        self.record_hit(eval_task_id)
        if self._maybe_inject(eval_task_id):
            return self.fail_response()
        if (MockJudgeProtocolError(self.behavior.protocol_error)
                == MockJudgeProtocolError.BAD_CODE):
            return {'code': 1, 'msg': 'mock 注入：协议错误 bad_code', 'data': {}}
        return {'code': 0, 'msg': OK_MSG,
                'data': {'result': build_judge_result(self.behavior)}}

    def snapshot(self) -> dict:
        return {'behavior': asdict(self.behavior), 'state': self.state.snapshot()}


class MockJudgeRequestHandler(BaseHTTPRequestHandler):
    """HTTP Handler：异步任务协议端点 + health + 控制端点（server.service 注入共享服务）。"""

    def log_message(self, *args):  # 静默默认访问日志（运行日志由 main 打关键行）
        pass

    @property
    def service(self) -> MockJudgeService:
        return self.server.service

    def _reply(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reply_text(self, status: int, text: str) -> None:
        body = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
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

    def _reply_judge(self, result: dict) -> None:
        """协议端点统一出口：协议错误（malformed_json）→ 失败注入 → 正常 JSON。"""
        if (MockJudgeProtocolError(self.service.behavior.protocol_error)
                == MockJudgeProtocolError.MALFORMED_JSON):
            self._reply_text(200, 'mock-injected-malformed-json')
            return
        status = result.pop('__status__', None)
        if status is not None:
            self._reply(status, result.get('__body__'))
        else:
            self._reply(200, result)

    # ---- GET ----
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == '/health':
            self._reply(200, {'status': 'ok', 'service': 'mock_eval_server_judge'})
        elif path == '/__control':
            self._reply(200, self.service.snapshot())
        elif path.startswith('/api/get_status/'):
            self._apply_delay()
            eval_task_id = path.rsplit('/', 1)[-1]
            self._reply_judge(self.service.get_status(eval_task_id))
        elif path.startswith('/api/get_final_result/'):
            self._apply_delay()
            eval_task_id = path.rsplit('/', 1)[-1]
            self._reply_judge(self.service.get_final_result(eval_task_id))
        else:
            self._reply(404, {'code': 404, 'msg': 'not found'})

    # ---- POST ----
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == '/api/create_task':
            self._handle_create_task()
        elif path == '/api/create_task_upload':
            self._handle_create_task_upload()
        elif path == '/__control':
            self._handle_control(parsed.query)
        elif path == '/__control/reset':
            self.service.state.reset()
            self._reply(200, {'status': 'reset', 'snapshot': self.service.snapshot()})
        else:
            self._reply(404, {'code': 404, 'msg': 'not found'})

    def _handle_create_task(self):
        self._apply_delay()
        payload = json.loads(self._read_body() or b'{}')
        self._reply_judge(self.service.create_task('create_task', fields=payload))

    def _handle_create_task_upload(self):
        self._apply_delay()
        content_type = self.headers.get('Content-Type', '')
        body = self._read_body()
        if content_type.startswith('multipart/form-data'):
            fields, files = parse_multipart(body, content_type)
        else:
            fields, files = {}, {}
        self._reply_judge(self.service.create_task('create_task_upload',
                                                   fields=fields, files=files))

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
        casters = {'fixed_score': float, 'fixed_latency_ms': int, 'delay_ms': int,
                   'fail_status': int, 'per_round_rounds': int, 'running_polls': int}
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


class MockJudgeServer:
    """可编程启停的 mock eval_server 替身（进程内测试 / 独立进程运行共用）。"""

    def __init__(self, behavior: MockJudgeBehavior = None, host: str = '127.0.0.1',
                 port: int = 0):
        self.service = MockJudgeService(behavior or MockJudgeBehavior())
        self._httpd = ThreadingHTTPServer((host, port), MockJudgeRequestHandler)
        self._httpd.service = self.service
        self.host, self.port = self._httpd.server_address[:2]

    @property
    def base_url(self) -> str:
        return f'http://{self.host}:{self.port}'

    def start(self):
        thread = threading.Thread(target=self._httpd.serve_forever, daemon=True,
                                  name='mock-eval-server-judge')
        thread.start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()

    def serve_forever(self):
        self._httpd.serve_forever()

    def set_behavior(self, changes: dict) -> None:
        """跨线程热更新行为（测试驱动注入用；独立进程用 /__control 控制端点）。"""
        self.service.behavior.update(changes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Mock eval_server 裁判端点替身（INT-182）')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--config', default='',
                        help='行为配置文件（JSON，behavior 段；优先级低于命令行与环境变量）')
    parser.add_argument('--score-mode', choices=[m.value for m in MockJudgeScoreMode])
    parser.add_argument('--fixed-score', type=float)
    parser.add_argument('--fixed-latency-ms', type=int)
    parser.add_argument('--delay-ms', type=int)
    parser.add_argument('--fail-mode', choices=[m.value for m in MockJudgeFailMode])
    parser.add_argument('--fail-status', type=int)
    parser.add_argument('--protocol-error',
                        choices=[m.value for m in MockJudgeProtocolError])
    parser.add_argument('--per-round-rounds', type=int)
    parser.add_argument('--running-polls', type=int)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    behavior = (MockJudgeBehavior.from_config_file(args.config)
                if args.config else MockJudgeBehavior.from_env())
    cli_changes = {}
    for flag, key in [('score_mode', 'score_mode'), ('fixed_score', 'fixed_score'),
                      ('fixed_latency_ms', 'fixed_latency_ms'), ('delay_ms', 'delay_ms'),
                      ('fail_mode', 'fail_mode'), ('fail_status', 'fail_status'),
                      ('protocol_error', 'protocol_error'),
                      ('per_round_rounds', 'per_round_rounds'),
                      ('running_polls', 'running_polls')]:
        value = getattr(args, flag)
        if value is not None:
            cli_changes[key] = value
    if cli_changes:
        behavior.update(cli_changes)

    server = MockJudgeServer(behavior, host=args.host, port=args.port)
    print(f'[mock_eval_server_judge] listening on http://{args.host}:{server.port} '
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
