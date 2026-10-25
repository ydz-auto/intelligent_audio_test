# -*- coding: utf-8 -*-
"""INT-1746 / C1 守卫：三条 API 执行链的 rounds[i].output 统一为映射后 dict。

C0（INT-1745）裁定 1/2（2026-10-24）：
- 映射责任在执行侧：执行链产出轮次时即生成 ``{target_param: value}``，
  评估侧只按 ``output.get(target_param)`` 取值；
- ``rounds[i].output`` 子字典强制，轮次元字段（round_number / latency /
  success / mode / answer_text …）留作兄弟键，**不平铺进 output**；
- 输出字段声明归属 ``algorithm_api_params(direction=output)``，零声明时
  ``meta`` 解析器逐键兜底；
- 未配 ``source='api'`` 映射的老算法按全等兜底（source_param 即 target_param）。

覆盖：
1. 声明提取的文本兜底（HTTP 链 ``output`` / WS 链 ``text`` 同一声明跨链生效）；
2. build_eval_output：api/device 映射、case/reference 跳过、零映射全等兜底 + 日志；
3. 单轮链 extract_final_result 走同一映射入口；
4. 多轮链：output 子字典 + answer_text 兄弟键 + 聚合 text_output 派生；
5. Realtime：普通轮 / 打断轮 output 子字典（WS ``text`` 兜底）；
6. 存量字符串 output 的归一路径不回归。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.api_output_extractor import (
    build_eval_output,
    extract_api_output_fields,
    extract_declared_output_fields,
)
from shared.utils.round_data_utils import normalize_round_output


def _field_mappings(*, api_output=None, eval_output=None):
    """构造 GetFieldMappings 口径（original 段）。"""
    return {
        'original': {
            'api': {'input': {}, 'output': api_output or {}},
            'evaluation': {'input': {}, 'output': eval_output or {}},
        },
    }


def _api_out(*codes):
    return {code: {'code': code, 'direction': 'output'} for code in codes}


def _eval_entry(source, source_param, target_param):
    return {'source': source, 'source_param': source_param,
            'target_param': target_param, 'transform_type': 'none'}


class _LogExecutorStub:
    """执行器替身：仅提供链依赖的 _log / _handle_control"""

    def __init__(self):
        self.logs = []

    def _log(self, level='INFO', content='', task_id=None, **kwargs):
        self.logs.append((level, content))

    def _handle_control(self, task_id):
        pass


# ==================== 1. 声明提取的文本兜底 ====================

def test_declared_text_output_falls_back_to_round_text():
    """文本型 + 空 field_path + 评估消费该字段 + 响应里没有该键 → 取轮次规范文本。"""
    defs = {'answer': {'code': 'answer', 'param_type': 'text'}}
    values = extract_declared_output_fields(
        defs, {'asr_text': 'x'}, text_output='你好呀',
        text_fallback_codes={'answer'})
    assert values == {'answer': '你好呀'}


def test_declared_text_display_field_does_not_take_text_fallback():
    """会话级展示文本字段（非评估消费）不拿回复文本兜底，避免污染展示值。"""
    defs = {'session_id': {'code': 'session_id', 'param_type': 'text'},
            'answer': {'code': 'answer', 'param_type': 'text'}}
    values = extract_declared_output_fields(
        defs, {}, text_output='你好呀', text_fallback_codes={'answer'})
    assert values == {'session_id': None, 'answer': '你好呀'}
    # 不传兜底集合 = 不兜底（默认关闭）
    assert extract_declared_output_fields(
        defs, {}, text_output='你好呀') == {'session_id': None, 'answer': None}


def test_declared_audio_output_does_not_take_text_fallback():
    """非文本型字段不参与文本兜底（response_audio 不会被文本填满）。"""
    defs = {'response_audio': {'code': 'response_audio',
                               'param_type': 'audio_file'}}
    values = extract_declared_output_fields(
        defs, {}, text_output='你好呀')
    assert values == {'response_audio': None}


def test_declared_value_wins_over_text_fallback():
    """响应里真有该键时以响应为准，规范文本只做缺值兜底。"""
    defs = {'answer': {'code': 'answer', 'param_type': 'text'}}
    values = extract_declared_output_fields(
        defs, {'answer': '厂商原文'}, text_output='兜底文本',
        text_fallback_codes={'answer'})
    assert values == {'answer': '厂商原文'}


def test_extract_api_output_fields_passes_text_output_through():
    mappings = _field_mappings(
        api_output={
            'answer': {'code': 'answer', 'param_type': 'text'},
        },
        eval_output={'answer': _eval_entry('api', 'answer', 'answer')})
    values, source = extract_api_output_fields(
        mappings, {'text': 'WS 文本'}, text_output='WS 文本')
    assert source == 'declared'
    assert values == {'answer': 'WS 文本'}


def test_extract_with_session_level_declarations_keeps_round_output_clean():
    """种子的 8 条声明 + 只映射 answer：其余文本声明不拿回复文本兜底。"""
    mappings = _field_mappings(
        api_output={
            'answer': {'code': 'answer', 'param_type': 'text'},
            'session_id': {'code': 'session_id', 'param_type': 'text'},
            'round_count': {'code': 'round_count', 'param_type': 'number'},
            'total_latency': {'code': 'total_latency', 'param_type': 'number'},
            'context_mode': {'code': 'context_mode', 'param_type': 'text'},
            'history_count': {'code': 'history_count', 'param_type': 'number'},
            'error': {'code': 'error', 'param_type': 'text'},
            'rounds': {'code': 'rounds', 'param_type': 'json'},
            'response_audio': {'code': 'response_audio',
                               'param_type': 'audio_file'},
        },
        eval_output={'answer': _eval_entry('api', 'answer', 'answer')})
    values, _ = extract_api_output_fields(
        mappings, {'output': '厂商回复'}, text_output='厂商回复')
    assert values['answer'] == '厂商回复'
    for code in ('session_id', 'context_mode', 'error', 'round_count',
                 'total_latency', 'history_count', 'rounds',
                 'response_audio'):
        assert values[code] is None, f'{code} 不应被填值'
    assert build_eval_output(mappings, values) == {'answer': '厂商回复'}


# ==================== 2. build_eval_output ====================

def test_build_eval_output_maps_api_and_device_sources():
    mappings = _field_mappings(eval_output={
        'answer': _eval_entry('api', 'answer', 'answer'),
        'question': _eval_entry('device', 'question', 'question'),
        'score': _eval_entry('evaluation', 'score', 'score'),
    })
    out = build_eval_output(mappings, {'answer': '答', 'question': '问'})
    # evaluation 来源由评估侧产出，执行侧不写（这里也没有对应的 api 值）
    assert out == {'answer': '答', 'question': '问'}


def test_build_eval_output_keeps_unmapped_output_fields():
    """没配映射的输出字段按自身参数名保留（评估侧按 mapped 键读、报告要展示）。"""
    mappings = _field_mappings(eval_output={
        'answer': _eval_entry('api', 'answer', 'answer'),
    })
    out = build_eval_output(
        mappings, {'answer': '答', 'response_audio': 'oss://a.wav'})
    assert out == {'answer': '答', 'response_audio': 'oss://a.wav'}


def test_build_eval_output_skips_case_and_reference_sources():
    """case/reference 来源不由执行侧解析（评估侧按轮自行加载）。"""
    mappings = _field_mappings(eval_output={
        'answer': _eval_entry('api', 'answer', 'answer'),
        'query': _eval_entry('reference', 'query', 'query'),
        'correct_answer': _eval_entry('case', 'correctAnswer', 'correct_answer'),
    })
    out = build_eval_output(mappings, {'answer': '答'})
    assert out == {'answer': '答'}


def test_build_eval_output_maps_renamed_target():
    mappings = _field_mappings(eval_output={
        'answer_text': _eval_entry('api', 'asr_result', 'answer_text'),
    })
    out = build_eval_output(mappings, {'asr_result': '识别文本'})
    assert out == {'answer_text': '识别文本'}


def test_build_eval_output_identity_fallback_with_log():
    """零 api/device 映射：全等兜底（键不变）并打一条日志。"""
    logs = []
    out = build_eval_output(
        _field_mappings(eval_output={
            'query': _eval_entry('reference', 'query', 'query'),
        }),
        {'asr_result': '识别文本', 'translation': '译文'},
        log=lambda level, msg: logs.append((level, msg)))
    assert out == {'asr_result': '识别文本', 'translation': '译文'}
    assert len(logs) == 1 and logs[0][0] == 'INFO'
    assert 'asr_result' in logs[0][1]


def test_build_eval_output_mapping_missing_value_omitted():
    """映射存在但执行侧没取到该字段 → 不写该 target（评估侧得 None）。"""
    mappings = _field_mappings(eval_output={
        'answer': _eval_entry('api', 'answer', 'answer'),
    })
    assert build_eval_output(mappings, {}) == {}


# ==================== 3. 单轮链 ====================

def _patch_single_round_acl(monkeypatch, field_mappings):
    from api_test_service.core import api_task_runner as runner_mod
    monkeypatch.setattr(runner_mod._algo_acl, 'get_field_mappings',
                        lambda algorithm_type, api_id=None: field_mappings)
    monkeypatch.setattr(runner_mod._algo_acl, 'get_device_params',
                        lambda algorithm_type, api_id=None: [])
    monkeypatch.setattr(runner_mod._algo_acl, 'get_api_params',
                        lambda algorithm_type, api_id=None: [])
    monkeypatch.setattr(runner_mod._algo_acl, 'get_param_mapping',
                        lambda algorithm_type, comp_type, api_id=None: [])
    return runner_mod


def _make_runner(monkeypatch, field_mappings):
    runner_mod = _patch_single_round_acl(monkeypatch, field_mappings)
    executor = _LogExecutorStub()
    return runner_mod.APITaskRunner(executor), executor


def test_single_round_applies_eval_mapping(monkeypatch):
    """单轮与多轮/Realtime 走同一映射入口：param_code → target_param。"""
    mappings = _field_mappings(
        api_output=_api_out('asr_result'),
        eval_output={'answer_text': _eval_entry('api', 'asr_result', 'answer_text')})
    runner, _ = _make_runner(monkeypatch, mappings)
    algo_results, _ = runner.extract_final_result(
        1, {'json': {'code': 0, 'data': {'asr_result': '识别文本'}},
            'latency': 5, 'asr': '', 'trans': '', 'output': ''}, 'translation')
    assert algo_results == {'answer_text': '识别文本'}


def test_single_round_without_api_mapping_keeps_keys(monkeypatch):
    """未配 source='api' 映射：键不变（存量口径不回归）并留一条日志。"""
    mappings = _field_mappings(
        api_output=_api_out('asr_result', 'translation'),
        eval_output={'query': _eval_entry('reference', 'query', 'query')})
    runner, executor = _make_runner(monkeypatch, mappings)
    algo_results, _ = runner.extract_final_result(
        1, {'json': {'code': 0, 'data': {'asr_result': '识别文本'}},
            'latency': 5, 'asr': '', 'trans': '', 'output': ''}, 'translation')
    assert algo_results == {'asr_result': '识别文本', 'translation': ''}
    assert any('全等映射' in content for _, content in executor.logs)


# ==================== 4. 多轮链 ====================

def _make_session_executor():
    from api_test_service.core.api_session_executor import APISessionExecutor
    executor = APISessionExecutor.__new__(APISessionExecutor)
    executor._executor = _LogExecutorStub()
    return executor


def test_multi_round_output_subdict_and_answer_text_sibling():
    """output 只装 target_param 键；answer_text / round_number 等同级，不平铺。"""
    executor = _make_session_executor()
    mappings = _field_mappings(
        api_output={'answer': {'code': 'answer', 'param_type': 'text'}},
        eval_output={'answer': _eval_entry('api', 'answer', 'answer')})
    round_result = {
        'round_number': 2,
        'answer_text': '你好，有什么可以帮助你的？',
        'latency': 0.3,
        'success': True,
        'raw_response': {'json': {'asr_text': '你好'}},
    }
    executor._attach_api_output_fields(
        round_result, mappings, 'voice_llm', task_id=1, unwrap_execute_result=True)

    assert round_result['output'] == {'answer': '你好，有什么可以帮助你的？'}
    assert set(round_result['output']) == {'answer'}
    # 元字段是兄弟键，不在 output 里
    for meta_key in ('round_number', 'answer_text', 'latency', 'success'):
        assert meta_key not in round_result['output']


def test_multi_round_aggregate_text_output_from_answer_text():
    """text_output 由各轮 answer_text 派生，不再拼接 output（已是 dict）。"""
    from api_test_service.core.session_context import SessionContext

    executor = _make_session_executor()
    session = SessionContext(session_id='s-int1746', config={'session_timeout': 5})
    rounds = [
        {'round_number': 1, 'answer_text': '第一轮', 'output': {'answer': '第一轮'},
         'latency': 0.2, 'success': True},
        {'round_number': 2, 'answer_text': '第二轮', 'output': {'answer': '第二轮'},
         'latency': 0.4, 'success': True},
    ]
    ar = executor._aggregate_round_results(rounds, session)['algorithm_result']
    assert ar['text_output'] == '第一轮 第二轮'
    assert [r['output'] for r in ar['rounds']] == [{'answer': '第一轮'},
                                                   {'answer': '第二轮'}]


def test_multi_round_legacy_string_output_normalized():
    """存量字符串 output（历史 / 失败轮）归一为 answer_text + 空 output dict。"""
    from api_test_service.core.session_context import SessionContext

    executor = _make_session_executor()
    session = SessionContext(session_id='s-int1746b', config={'session_timeout': 5})
    rounds = [{'round_number': 1, 'output': '历史文本', 'latency': 0.1,
               'success': True}]
    ar = executor._aggregate_round_results(rounds, session)['algorithm_result']
    assert ar['rounds'][0]['output'] == {}
    assert ar['rounds'][0]['answer_text'] == '历史文本'
    assert ar['text_output'] == '历史文本'


# ==================== 5. Realtime 链 ====================

def _make_realtime_executor():
    from api_test_service.core.realtime_session_executor import (
        RealtimeSessionExecutor,
    )
    executor = RealtimeSessionExecutor.__new__(RealtimeSessionExecutor)
    executor._executor = _LogExecutorStub()
    return executor


def _patch_realtime_acl(monkeypatch, field_mappings):
    from api_test_service.core import realtime_session_executor as rt_mod
    monkeypatch.setattr(rt_mod._algo_acl, 'get_field_mappings',
                        lambda algorithm_type, api_id=None: field_mappings)
    return rt_mod


def test_realtime_normal_round_output_subdict(monkeypatch):
    """普通轮：WS 聚合输出 ``text`` → 声明 answer → output.answer。"""
    mappings = _field_mappings(
        api_output={'answer': {'code': 'answer', 'param_type': 'text'}},
        eval_output={'answer': _eval_entry('api', 'answer', 'answer')})
    _patch_realtime_acl(monkeypatch, mappings)
    executor = _make_realtime_executor()
    ws_output = {'text': 'AI 回复文本', 'ai_complete': True,
                 'barge_in_detected': False}
    out = executor._collect_eval_fields(
        {}, ws_output, 'voice_llm', text_output='AI 回复文本')
    assert out == {'answer': 'AI 回复文本'}


def test_realtime_barge_in_round_output_subdict(monkeypatch):
    """打断轮与普通轮同构：output 是 {target_param: value}，不混元字段。"""
    mappings = _field_mappings(
        api_output={'answer': {'code': 'answer', 'param_type': 'text'}},
        eval_output={'answer': _eval_entry('api', 'answer', 'answer')})
    _patch_realtime_acl(monkeypatch, mappings)
    executor = _make_realtime_executor()
    ws_output = {'text': '打断后重答', 'barge_in_detected': True}
    out = executor._collect_eval_fields(
        {}, ws_output, 'voice_llm', text_output='打断后重答')
    assert out == {'answer': '打断后重答'}
    assert 'barge_in_detected' not in out


def test_realtime_zero_api_mapping_identity_fallback(monkeypatch):
    """未配 api 映射：按参数名全等映射（键不变）且不报错。"""
    mappings = _field_mappings(
        api_output={'asr_result': {'code': 'asr_result', 'param_type': 'text'}},
        eval_output={'query': _eval_entry('reference', 'query', 'query')})
    _patch_realtime_acl(monkeypatch, mappings)
    executor = _make_realtime_executor()
    out = executor._collect_eval_fields(
        {}, {'asr_result': '识别文本'}, 'voice_llm')
    assert out == {'asr_result': '识别文本'}


# ==================== 6. 读取侧兼容 ====================

def test_normalize_round_output_dict_short_circuit():
    """新链产出的 dict 原样返回（不改写 target_param 结构）。"""
    mapped = {'answer': '答', 'question': '问'}
    assert normalize_round_output(mapped) == mapped
    # 存量字符串仍归一为 {'text': str}
    assert normalize_round_output('历史文本') == {'text': '历史文本'}


# ==================== 7. 种子形状可达性 ====================

def _load_seed_module():
    import importlib.util
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'scripts', 'migrations', '202610', 'seed_api_eval_mapping_int1746.py')
    spec = importlib.util.spec_from_file_location('_seed_int1746', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_declares_voice_llm_display_output_fields():
    """A 段声明集合：answer + 7 条展示字段，rounds 最后，不重复插 response_audio。

    C3（INT-1748）删掉 ``VoiceLlmStrategy.get_output_fields`` 的硬编码 7 字段后，
    这 7 条只剩种子一个来源（需求规划师 2026-10-24 08:05Z 种子边界）。
    """
    seed = _load_seed_module()
    decls = seed.API_OUTPUT_DECLS

    assert all(d['algorithm_type'] == 'voice_llm' and d['direction'] == 'output'
               for d in decls)
    codes = [d['param_code'] for d in decls]
    assert sorted(codes) == sorted([
        'answer', 'session_id', 'round_count', 'total_latency',
        'context_mode', 'history_count', 'error', 'rounds'])
    assert len(codes) == len(set(codes)), '声明 param_code 不能重复'
    assert 'response_audio' not in codes, '主库已有，重复插会破坏幂等语义'

    types = {d['param_code']: d['param_type'] for d in decls}
    assert types['rounds'] == 'json'
    for code in ('answer', 'session_id', 'context_mode', 'error'):
        assert types[code] == 'text'
    for code in ('round_count', 'total_latency', 'history_count'):
        assert types[code] == 'number'

    assert max(decls, key=lambda d: d['ui_order'])['param_code'] == 'rounds'
    orders = [d['ui_order'] for d in decls]
    assert len(orders) == len(set(orders)), 'ui_order 不能重复'


def _stub_field_definition_cache(monkeypatch, *, api_params, mappings):
    from algorithm_service.application.queries import field_mapping_queries as q
    from types import SimpleNamespace
    cache = SimpleNamespace(
        get_device_params=lambda algorithm_type, api_id=None: [],
        get_api_params=lambda algorithm_type, api_id=None: api_params,
        get_reference_params=lambda algorithm_type, api_id=None: [],
        get_param_mapping=lambda algorithm_type, component, api_id=None: (
            mappings if component == 'evaluation' else []),
        get_case_params=lambda algorithm_type, api_id=None: [],
    )
    monkeypatch.setattr(q, 'get_config_cache', lambda: cache)
    return q.FieldMappingQueryHandler.get_field_definitions('voice_llm')


def test_seed_shape_makes_eval_mapping_visible(monkeypatch):
    """声明 + source='api' 映射两件齐备 → 映射可见，8 条声明全进 api.output。"""
    seed = _load_seed_module()
    api_params = [
        {'code': d['param_code'], 'direction': d['direction'],
         'param_type': d['param_type'], 'label': d['param_name']}
        for d in seed.API_OUTPUT_DECLS
    ] + [{'code': 'response_audio', 'direction': 'output',
          'param_type': 'audio_file'}]
    defs = _stub_field_definition_cache(
        monkeypatch,
        api_params=api_params,
        mappings=[{'source': 'api', 'source_param': 'answer',
                   'target_param': 'answer', 'dimension_id': 1,
                   'transform_type': 'none'}],
    )
    entry = defs['original']['evaluation']['output']['answer']
    assert entry['source'] == 'api'
    assert entry['target_param'] == 'answer'
    # 8 条种子声明 + 存量 response_audio 全部可见（C3 展示清单的来源）
    expected = {d['param_code'] for d in seed.API_OUTPUT_DECLS} | {'response_audio'}
    assert set(defs['original']['api']['output']) == expected
    assert set(defs['mapped']['api']) == expected


def test_mapping_without_api_declaration_is_dropped(monkeypatch):
    """只有映射、没有输出声明 → handler 丢弃该映射（「两者缺一不可」）。"""
    defs = _stub_field_definition_cache(
        monkeypatch,
        api_params=[{'code': 'response_audio', 'direction': 'output',
                     'param_type': 'audio_file'}],
        mappings=[{'source': 'api', 'source_param': 'answer',
                   'target_param': 'answer', 'dimension_id': 1,
                   'transform_type': 'none'}],
    )
    assert 'answer' not in defs['original']['evaluation']['output']
