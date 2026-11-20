# -*- coding: utf-8 -*-
"""VEGA-78 评估参数组装修复单测（开发卡 VEGA-81，方案 v2 F1-F5）。

矩阵第 1-4 项：
- F1：子维度继承父维度 input_params（防 setdefault no-op），子维度作 representative
  时 defaults 注入 context，audio_field_names 含 ai_wav/user_wav（同源副作用）；
- F2：representative 稳定化——组内优先 main，无 main 回落首元素，与组内顺序无关；
- F3：4xx 响应体 msg 片段并入 __error__（dict / 非 dict 两分支）；
- F4：无值占位符 WARNING 留痕，不改行为（不设字段，eval_server 兜底）；
- F5：轮内空值回落顶层同名字段，显式 False/0 不被吞。

纯单测：最小宿主 + 替身，不触 DB/gRPC/线程池。
"""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import threading
from types import SimpleNamespace

import evaluation_service.infrastructure.evaluation_api.api_request_handler as handler_mod
from evaluation_service.domain.services.evaluation_service.dimension_loader import (
    DimensionLoaderMixin,
)
from evaluation_service.infrastructure.evaluation_api.endpoint_worker import EndpointWorker
from evaluation_service.infrastructure.evaluation_api.payload_builder import PayloadBuilder
from evaluation_service.infrastructure.evaluation_api.task_dispatcher import (
    TaskDispatcherMixin,
)


# ── 共享构造：维度聚合根 / input_params ──────────────────────────

# 对齐任务 470 拒识族：主维度 121 的 input_params（model 无默认值，走 eval_server 兜底）
PARENT_INPUT_PARAMS = [
    {'param_code': 'max_tokens', 'default_value': '4096', 'field_type': 'number', 'required': True},
    {'param_code': 'temperature', 'default_value': '0.1', 'field_type': 'number', 'required': True},
    {'param_code': 'is_single_round', 'default_value': 'false', 'field_type': 'text', 'required': True},
    {'param_code': 'is_reject', 'default_value': 'true', 'field_type': 'text', 'required': True},
    {'param_code': 'ai_wav', 'default_value': None, 'field_type': 'audio', 'required': True},
    {'param_code': 'user_wav', 'default_value': None, 'field_type': 'audio', 'required': True},
]

BODY_TEMPLATE = {
    'model': '{{model}}',
    'max_tokens': '{{max_tokens}}',
    'temperature': '{{temperature}}',
    'is_single_round': '{{is_single_round}}',
    'rounds': [
        {'ai_wav': '{{ai_wav}}', 'user_wav': '{{user_wav}}',
         'is_reject': '{{is_reject}}', 'timing': '{{timing}}', 'type': '{{type}}'},
    ],
}


def _agg(dim_id, name, dtype, parent_id=None, task_type_code='reject_judge',
         api_endpoints=None, api_settings=None, api_url=None, category_id=3):
    """维度聚合根替身：_format_dimension_data 只读 id/name/.snapshot 字段。"""
    return SimpleNamespace(
        id=dim_id, name=name,
        snapshot=SimpleNamespace(
            rule=None,
            api_endpoints=api_endpoints,
            api_settings=api_settings,
            api_url=api_url,
            dimension_type=dtype,
            parent_dimension_id=parent_id,
            task_type_code=task_type_code,
            category_id=category_id,
        ),
    )


def _reject_family():
    """拒识族：主维度 121（带 API 配置与 input_params）+ 子维度 124（全空，靠继承）。"""
    parent = _agg(121, '拒识成功数量', 'main',
                  api_endpoints=[{'url': 'http://eval:8888'}],
                  api_settings={'body_template': BODY_TEMPLATE})
    sub = _agg(124, '静默时拒识恢复行为数量', 'sub', parent_id=121,
               task_type_code='false_takeover')
    return parent, sub


class _FakeDimRepo:
    """替身 _evaluation_dimension_repo：按 id 返回聚合根列表。"""

    def __init__(self, aggs):
        self._by_id = {a.id: a for a in aggs}

    def list_active_dimensions_by_ids(self, ids):
        return [self._by_id[i] for i in ids if i in self._by_id]


def _format_dims(parent, sub, input_param_map):
    loader = DimensionLoaderMixin()
    loader._evaluation_dimension_repo = _FakeDimRepo([parent, sub])
    return {d['id']: d for d in loader._format_dimension_data(
        [parent, sub], {}, input_param_map)}


def _worker():
    """EndpointWorker 最小实例：跳过 __init__（Redis/队列），_log 静默。"""
    worker = object.__new__(EndpointWorker)
    worker._log = lambda **kwargs: None
    return worker


# ── F1：子维度继承 input_params（矩阵第 1 项） ─────────────────────


def test_f1_sub_inherits_parent_input_params():
    """子维度 input_params 为空列表时继承父维度（显式判空赋值，恰好防 setdefault no-op）。"""
    parent, sub = _reject_family()
    sub_dict = _format_dims(parent, sub, {121: PARENT_INPUT_PARAMS})[124]

    # 断言非空且等于父维度参数——若实现误用 setdefault（键恒存在，值为 []），
    # 此处仍是 []，测试失败
    assert sub_dict['input_params'] == PARENT_INPUT_PARAMS
    # 既有继承行为不受影响
    assert sub_dict['api_endpoints'] == [{'url': 'http://eval:8888'}]
    assert sub_dict['api_settings'] == {'body_template': BODY_TEMPLATE}
    assert sub_dict['parent_task_type_code'] == 'reject_judge'


def test_f1_sub_with_own_input_params_not_overwritten():
    """子维度自带 input_params 时不被父维度覆盖。"""
    parent, sub = _reject_family()
    own_params = [{'param_code': 'my_param', 'default_value': '1',
                   'field_type': 'text', 'required': True}]
    sub_dict = _format_dims(parent, sub,
                            {121: PARENT_INPUT_PARAMS, 124: own_params})[124]
    assert sub_dict['input_params'] == own_params


def test_f1_sub_representative_defaults_injected_into_context():
    """子维度作 representative：input_params 默认值注入评估上下文（任务 470 缺四键场景）。"""
    parent, sub = _reject_family()
    sub_dict = _format_dims(parent, sub, {121: PARENT_INPUT_PARAMS})[124]

    worker = _worker()
    captured = {}

    def fake_build_payload(body_template, context, **kwargs):
        captured.update(body_template=body_template, context=dict(context))
        return dict(context)

    worker.eval_service = SimpleNamespace(
        api_client=SimpleNamespace(build_payload=fake_build_payload))

    payload = worker._build_evaluation_context(
        470, 'tc1', {}, sub_dict, None, [], 124, {}, {},
        group_items=[(sub_dict, 9001)])

    # default_value 为 JSON 字符串，注入后已解析
    assert payload['max_tokens'] == 4096
    assert payload['temperature'] == 0.1
    assert payload['is_single_round'] is False
    assert payload['is_reject'] is True
    # body_template 从继承的 api_settings 取到
    assert captured['body_template'] == BODY_TEMPLATE


def test_f1_sub_representative_audio_field_names():
    """F1 副作用（同源修复）：子维度作 representative 时 audio_field_names 不再为空。"""
    parent, sub = _reject_family()
    sub_dict = _format_dims(parent, sub, {121: PARENT_INPUT_PARAMS})[124]

    worker = _worker()
    endpoints, method, headers, dim_info, audio_field_names = \
        worker._prepare_api_config(sub_dict, [(sub_dict, 9001)])

    assert audio_field_names == {'ai_wav', 'user_wav'}


# ── F2：representative 稳定化（矩阵第 2 项） ──────────────────────


class _Dispatcher(TaskDispatcherMixin):
    """最小宿主：真实 _submit_to_workers，worker 创建与任务构建打桩捕获。"""

    def __init__(self):
        self.representatives = []
        self.api_client = SimpleNamespace(
            global_lock=threading.Lock(),
            thread_pool=SimpleNamespace(_shutdown=False, submit=lambda fn, *a: None),
        )

    def _log(self, **kwargs):
        pass

    def _get_or_create_worker(self, endpoint_url, representative_dim_data):
        self.representatives.append(representative_dim_data)
        return object()

    def _build_task_data(self, *args, **kwargs):
        return {}


def _dispatch(group_items):
    dispatcher = _Dispatcher()
    dispatcher._submit_to_workers(
        {('http://eval:8888', 'fam'): group_items},
        result_id=1, task_id=470, test_case_id=None,
        algorithm_result={}, algorithm_type='voice_llm',
        device_type='physical', round_number=None,
        field_mapper=None, ref_texts={}, rounds_list=None,
        flat_eval_fields=None,
    )
    return dispatcher


def _dim(dim_id, dtype):
    return {'id': dim_id, 'name': f'dim{dim_id}', 'dimension_type': dtype,
            'task_type_code': 'reject_judge', 'category_id': 3,
            'api_endpoints': [{'url': 'http://eval:8888'}], 'api_url': None,
            'api_settings': {'body_template': BODY_TEMPLATE}}


def test_f2_representative_prefers_main_over_sub():
    """组内含 main 时 representative=main（main 在首/尾两序均成立）。"""
    sub, main = _dim(124, 'sub'), _dim(121, 'main')
    for order in ([sub, main], [main, sub]):
        dispatcher = _dispatch([(d, d['id'] * 10) for d in order])
        assert dispatcher.representatives[0]['id'] == 121


def test_f2_all_sub_group_falls_back_to_first():
    """组内无 main（纯子维度组）回落首元素，行为与改前一致。"""
    sub_a, sub_b = _dim(124, 'sub'), _dim(125, 'sub')
    dispatcher = _dispatch([(sub_a, 1240), (sub_b, 1250)])
    assert dispatcher.representatives[0]['id'] == 124


# ── F3：4xx 响应体 msg 并入 __error__（矩阵第 3 项） ───────────────


def _handler():
    handler = handler_mod.ApiRequestHandler()
    handler._log = lambda **kwargs: None
    return handler


def _resp(status_code, body_text, json_body):
    return SimpleNamespace(
        status_code=status_code, text=body_text, json=lambda: json_body)


def test_f3_4xx_dict_msg_merged_into_error(monkeypatch):
    """dict 响应体：__error__ 含 HTTP 400 + msg 片段（worker 拒绝原因不再被塌缩）。"""
    body = {'code': 3001, 'msg': '远程端点响应错误 (400): '
            '{"code":400,"msg":"Unsupported task type: reject_judge"}'}
    monkeypatch.setattr(
        handler_mod, 'requests',
        SimpleNamespace(post=lambda *a, **kw: _resp(
            400, json.dumps(body, ensure_ascii=False), body)))

    resp_data = _handler().create_task_upload('http://eval:8888', {}, {})

    assert resp_data['__error__'].startswith('HTTP 400')
    assert 'Unsupported task type: reject_judge' in resp_data['__error__']
    assert resp_data['code'] == 3001   # 原 dict 字段保留


def test_f3_4xx_dict_without_msg_keeps_status_only(monkeypatch):
    """dict 无 msg 键：__error__ 维持纯状态码形态。"""
    body = {'code': 400}
    monkeypatch.setattr(
        handler_mod, 'requests',
        SimpleNamespace(post=lambda *a, **kw: _resp(
            400, json.dumps(body), body)))

    resp_data = _handler().create_task_upload('http://eval:8888', {}, {})

    assert resp_data['__error__'] == 'HTTP 400'


def test_f3_4xx_non_dict_body_snippet_and_raw_kept(monkeypatch):
    """非 dict 响应体：msg 片段并入 __error__，原文仍由 __raw_response__ 承载。"""
    text = 'gateway bad request: invalid param set'
    monkeypatch.setattr(
        handler_mod, 'requests',
        SimpleNamespace(post=lambda *a, **kw: SimpleNamespace(
            status_code=400, text=text,
            json=_raise_json_decode)))

    resp_data = _handler().create_task_upload('http://eval:8888', {}, {})

    assert resp_data['__error__'] == 'HTTP 400: gateway bad request: invalid param set'
    assert resp_data['__raw_response__'] == text


def _raise_json_decode():
    raise json.JSONDecodeError('no json', 'x', 0)


def test_f3_4xx_long_msg_truncated(monkeypatch):
    """超长 msg 截断到 ~200 字符，避免 error_message 爆长。"""
    body = {'msg': 'x' * 500}
    monkeypatch.setattr(
        handler_mod, 'requests',
        SimpleNamespace(post=lambda *a, **kw: _resp(
            400, json.dumps(body), body)))

    resp_data = _handler().create_task_upload('http://eval:8888', {}, {})

    assert resp_data['__error__'] == f"HTTP 400: {'x' * 200}"


def test_f3_200_unchanged(monkeypatch):
    """200 响应不写 __error__（行为不变）。"""
    body = {'task_id': 't1'}
    monkeypatch.setattr(
        handler_mod, 'requests',
        SimpleNamespace(post=lambda *a, **kw: _resp(
            200, json.dumps(body), body)))

    resp_data = _handler().create_task_upload('http://eval:8888', {}, {})

    assert resp_data == {'task_id': 't1'}


# ── F4 / F5：payload_builder 渲染（矩阵第 4 项） ──────────────────


class _Builder(PayloadBuilder):
    """最小宿主：捕获 _log 调用供 WARNING 断言。"""

    def __init__(self):
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


def test_f5_round_empty_falls_back_to_top_level():
    """轮内空串回落顶层同名值；轮内显式 0 不被吞。"""
    builder = _Builder()
    body = {'rounds': [{'is_reject': '{{is_reject}}', 'timing': '{{timing}}',
                        'type': '{{type}}'}]}
    context = {'rounds': [{'is_reject': '', 'timing': 0, 'type': ''}],
               'is_reject': False, 'timing': 123.4, 'type': 'barge_in'}

    payload = builder.build_payload(body, context)

    round0 = payload['rounds'][0]
    assert round0['is_reject'] is False     # 空串 → 顶层 False
    assert round0['timing'] == 0            # 显式 0 保留（不用 or）
    assert round0['type'] == 'barge_in'     # 空串 → 顶层值


def test_f5_round_explicit_false_not_swallowed():
    """轮内显式 False/0 是有效值：不回落顶层（改前 or 写法会吞掉）。"""
    builder = _Builder()
    body = {'rounds': [{'is_reject': '{{is_reject}}', 'timing': '{{timing}}'}]}
    context = {'rounds': [{'is_reject': False, 'timing': 0}],
               'is_reject': True, 'timing': 999}

    payload = builder.build_payload(body, context)

    round0 = payload['rounds'][0]
    assert round0['is_reject'] is False
    assert round0['timing'] == 0


def test_f5_round_missing_everywhere_renders_empty_and_warns():
    """轮内与顶层均无值：渲染空串（行为不变）并进 F4 缺失键留痕。"""
    builder = _Builder()
    body = {'rounds': [{'opt': '{{nope}}'}]}
    context = {'rounds': [{'other': 1}]}

    payload = builder.build_payload(body, context)

    assert payload['rounds'][0]['opt'] == ''
    warns = [log for log in builder.logs if log.get('level') == 'WARNING']
    assert len(warns) == 1
    assert 'nope' in warns[0]['content'] and 'eval_server' in warns[0]['content']


def test_f4_top_level_missing_placeholder_warns_without_behavior_change():
    """顶层占位符无值：字段仍不设（eval_server 兜底设计），WARNING 列出缺失键。

    model 无默认值将稳定命中此 WARNING（预期噪音，文案标注由 eval_server 兜底）。
    """
    builder = _Builder()
    body = {'model': '{{model}}', 'max_tokens': '{{max_tokens}}'}
    context = {'max_tokens': 4096}

    payload = builder.build_payload(body, context)

    assert 'model' not in payload            # 行为不变：不设字段
    assert payload['max_tokens'] == 4096
    warns = [log for log in builder.logs if log.get('level') == 'WARNING']
    assert len(warns) == 1
    assert 'model' in warns[0]['content'] and 'eval_server' in warns[0]['content']


def test_f4_all_placeholders_resolved_no_warning():
    """全部占位符有值：无 WARNING（避免噪音放大）。"""
    builder = _Builder()
    body = {'max_tokens': '{{max_tokens}}',
            'rounds': [{'is_reject': '{{is_reject}}'}]}
    context = {'max_tokens': 4096, 'is_reject': True,
               'rounds': [{'is_reject': False}]}

    payload = builder.build_payload(body, context)

    assert payload['max_tokens'] == 4096
    assert payload['rounds'][0]['is_reject'] is False
    assert not [log for log in builder.logs if log.get('level') == 'WARNING']
