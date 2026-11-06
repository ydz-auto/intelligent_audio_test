# -*- coding: utf-8 -*-
"""INT-1748 设备输出声明种子（C3）契约测试。

覆盖：
- 种子计划：缺 record_file 时新增（audio_file）；user_wav / ai_wav 由 text 改 audio_file；
- 幂等：已是目标状态时全部 skip，重复执行为 0 变更；
- 软删行恢复（不新造重复行）；user_wav / ai_wav 声明缺失时只提示不凭空插行；
- 端到端（策略层）：按种子后的设备声明解析 rounds 轮内子键，与改造前
  DEVICE_FIELDS 口径逐字段一致（record_file 不再丢、user_wav / ai_wav 类型与
  音频路径归一回到 audio_file）。
"""
import importlib.util
import os
import sys

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.constants.device_fields import DEVICE_FIELDS
from shared.domain.algorithm_result_strategy import VoiceLlmStrategy

_SEED_PATH = os.path.join(
    _REPO_ROOT, 'scripts', 'migrations', '202610',
    'seed_voice_llm_device_output_int1748.py',
)


def _load_seed_module():
    spec = importlib.util.spec_from_file_location('seed_int1748', _SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_seed = _load_seed_module()


def _row(code, param_type, deleted=False, pid=1):
    return {'id': pid, 'param_code': code, 'param_type': param_type, 'deleted': deleted}


def _ops_by_code(ops):
    return {op['param_code']: op for op in ops}


# ---------- 种子计划 ----------

def test_seed_adds_record_file_and_fixes_audio_types():
    """主库现状（9 条设备输出声明、无 record_file、wav 声明为 text）下的计划。"""
    existing = [
        _row('wav_path', 'text', pid=29),
        _row('start_ms', 'timestamp', pid=35),
        _row('end_ms', 'timestamp', pid=36),
        _row('first_frame_ms', 'timestamp', pid=37),
        _row('input_text', 'text', pid=30),
        _row('question', 'text', pid=31),
        _row('answer', 'text', pid=32),
        _row('user_wav', 'text', pid=33),
        _row('ai_wav', 'text', pid=34),
    ]
    ops = _ops_by_code(_seed.plan_device_output_changes(existing))

    assert ops['record_file']['op'] == 'insert'
    assert ops['record_file']['param_type'] == 'audio_file'
    assert ops['user_wav']['op'] == 'update'
    assert ops['user_wav']['from_param_type'] == 'text'
    assert ops['user_wav']['param_type'] == 'audio_file'
    assert ops['ai_wav']['op'] == 'update'
    assert ops['ai_wav']['param_type'] == 'audio_file'
    # 其它声明不动（不在计划里）
    assert {'start_ms', 'end_ms', 'first_frame_ms', 'wav_path',
            'input_text', 'question', 'answer'}.isdisjoint(ops)


def test_seed_is_idempotent_when_already_applied():
    """已按种子落库后再跑：全部 skip（重复执行 0 变更）。"""
    applied = [
        _row('record_file', 'audio_file', pid=40),
        _row('user_wav', 'audio_file', pid=33),
        _row('ai_wav', 'audio_file', pid=34),
    ]
    ops = _seed.plan_device_output_changes(applied)
    assert all(op['op'] == 'skip' for op in ops)
    assert {op['param_code'] for op in ops} == {'record_file', 'user_wav', 'ai_wav'}


def test_seed_restores_soft_deleted_rows():
    """软删行恢复为活行，不新插重复行。"""
    ops = _ops_by_code(_seed.plan_device_output_changes([
        _row('record_file', 'audio_file', deleted=True, pid=41),
        _row('user_wav', 'text', deleted=True, pid=33),
        _row('ai_wav', 'audio_file', pid=34),
    ]))
    assert ops['record_file']['op'] == 'restore'
    assert ops['record_file']['id'] == 41
    assert ops['user_wav']['op'] == 'restore'
    assert ops['ai_wav']['op'] == 'skip'


def test_seed_does_not_invent_missing_audio_declarations():
    """user_wav / ai_wav 声明缺失时只提示，不凭空造行（展示名/排序属数据侧）。"""
    ops = _ops_by_code(_seed.plan_device_output_changes([]))
    assert ops['record_file']['op'] == 'insert'
    assert ops['user_wav']['op'] == 'missing'
    assert ops['ai_wav']['op'] == 'missing'


def test_seed_declaration_shape_matches_baseline_device_fields():
    """种子声明的 record_file 类型与改造前 DEVICE_FIELDS 一致。"""
    decl = {d['param_code']: d for d in _seed.NEW_DEVICE_OUTPUT}['record_file']
    assert decl['param_type'] == DEVICE_FIELDS['record_file']
    assert decl['label'] is None  # 轮内展示名回落 {param_code} (第N轮)，与基线一致
    for code in _seed.TYPE_FIXES:
        assert _seed.TYPE_FIXES[code] == DEVICE_FIELDS[code]


# ---------- 策略层：种子后与改造前口径等价 ----------

def _baseline_round_rows(combined, resource, normalize_audio_path_fn):
    """改造前 VoiceLlmStrategy 的 rounds 展开口径（类型取 DEVICE_FIELDS）。"""
    rows = []
    for r_idx, r_item in enumerate(combined.get('rounds') or []):
        raw_round = r_item.get('round')
        rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
        for sub_key, val in (r_item.get('output') or {}).items():
            if val is None or sub_key == 'evaluation':
                continue
            sub_type = DEVICE_FIELDS.get(sub_key, 'text')
            if sub_type == 'audio_file' and isinstance(val, str) and val:
                val = normalize_audio_path_fn(val)
            rows.append({
                'device': resource,
                'param_code': f'{sub_key}@round:{rn}',
                'param_type': sub_type,
                'label': f'{sub_key} (第{rn}轮)',
                'value': val,
                'round_number': rn,
                'dimension_name': None,
            })
    return rows


def _api_output_fields():
    """C1 种子的 7 条 API 输出声明 + 既有 response_audio（按展开与展示口径）。"""
    defs = [
        ('session_id', 'text', 10, 'session ID'),
        ('round_count', 'number', 20, 'round count'),
        ('total_latency', 'number', 30, 'total latency(ms)'),
        ('context_mode', 'text', 40, 'context mode'),
        ('history_count', 'number', 50, 'history count'),
        ('error', 'text', 60, 'error'),
        ('rounds', 'json', 70, 'round results'),
    ]
    return [
        {'source': 'api', 'source_param': code, 'target_param': code,
         'param_type': ptype, 'label': label, 'ui_order': order}
        for code, ptype, order, label in defs
    ]


def _device_output_fields_after_seed():
    """主库现状 9 条设备输出声明 + 本卡种子（record_file 新增、wav 类型修正）。"""
    rows = [
        ('wav_path', 'text', 0, '录音文件'),
        ('start_ms', 'timestamp', 0, '输入音频开始播放时间'),
        ('end_ms', 'timestamp', 0, '输入音频停止播放时间'),
        ('first_frame_ms', 'timestamp', 0, '录屏开始世界时间'),
        ('input_text', 'text', 10, '录屏文件'),
        ('question', 'text', 11, '用户提问'),
        ('answer', 'text', 12, '小艺回答'),
        ('user_wav', 'audio_file', 13, '用户通道音频'),   # 种子前 text
        ('ai_wav', 'audio_file', 14, '模型通道音频'),     # 种子前 text
        ('record_file', 'audio_file', 15, '录音文件路径'),  # 种子新增
    ]
    return [
        {'source': 'device', 'source_param': code, 'target_param': code,
         'param_type': ptype, 'label': None, 'ui_order': order,
         '_param_name': name}
        for code, ptype, order, name in rows
    ]


def test_round_subkeys_equal_baseline_after_device_seed():
    """种子后轮内子键逐字段等于改造前（record_file 不丢、wav 类型与路径归一一致）。"""
    combined = {
        'session_id': 's1',
        'round_count': 2,
        'rounds': [
            {'round': 0, 'output': {
                'question': '打开空调', 'answer': '已打开',
                'user_wav': '/data/user1.wav', 'ai_wav': '/data/ai1.wav',
                'record_file': '/data/full1.wav',
                'start_ms': 100, 'end_ms': 900, 'first_frame_ms': 50,
                'evaluation': {'skip': 1},
            }},
            {'round': 1, 'output': {
                'question': '关掉', 'answer': '好的',
                'user_wav': '/data/user2.wav', 'ai_wav': '/data/ai2.wav',
                'record_file': '/data/full2.wav',
            }},
        ],
    }
    normalize = lambda p: 'norm:' + p  # noqa: E731

    actual = VoiceLlmStrategy().process_algorithm_result(
        combined, _api_output_fields(), 'api_01', DEVICE_FIELDS,
        None, None, normalize, _device_output_fields_after_seed(),
    )
    actual_rounds = [r for r in actual if '@round:' in r['param_code']]
    expected_rounds = _baseline_round_rows(combined, 'api_01', normalize)

    # 顺序：按轮次、轮内按声明解码顺序（与基线一致）
    def key(row):
        return (row['round_number'], row['param_code'])
    assert sorted(actual_rounds, key=key) == sorted(expected_rounds, key=key)


def test_round_subkey_diffs_before_seed_are_explained():
    """种子前的两处差异可复现（证明种子是差异的唯一来源，不是代码）。"""
    combined = {'rounds': [{'round': 0, 'output': {
        'user_wav': '/data/u.wav', 'record_file': '/data/full.wav',
    }}]}
    pre_seed = [
        {'source': 'device', 'source_param': 'user_wav', 'target_param': 'user_wav',
         'param_type': 'text', 'label': None},
        # 无 record_file 声明
    ]
    rows = VoiceLlmStrategy().process_algorithm_result(
        combined, [{'source': 'api', 'source_param': 'rounds', 'target_param': 'rounds',
                    'param_type': 'json', 'label': 'round results'}],
        'dev_01', DEVICE_FIELDS, None, None, lambda p: 'norm:' + p, pre_seed,
    )
    codes = [r['param_code'] for r in rows if '@round:' in r['param_code']]
    assert codes == ['user_wav@round:1']  # record_file 丢、user_wav 未归一
    assert [r for r in rows if r['param_code'] == 'user_wav@round:1'][0]['value'] == '/data/u.wav'
    assert [r for r in rows if r['param_code'] == 'user_wav@round:1'][0]['param_type'] == 'text'
