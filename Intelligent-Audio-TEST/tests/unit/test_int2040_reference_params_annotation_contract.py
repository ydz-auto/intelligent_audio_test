# -*- coding: utf-8 -*-
"""INT-2040 守卫：voice_llm 参考参数恒为 0（标注键名 / 定义口径 / 空值判定）。

缺陷（INT-2038 复走复现，2026-10-26）：保存 voice_llm 用例后
`GET /testcases/{id}` 的 `reference_params` 恒为 `[]`，
`GET /testcases/{id}/rounds/1/ref-params` 404「第 1 轮未生成参考参数」。
服务端日志 `GenerateReferenceParams ... audio_ids: [2100, 2099]` /
`Preloaded 2 audios, 2 annotations` / `Generated 0 reference params for round 1`
——取数正常，生成器把取到的标注全部过滤掉了。三层原因：

1. 生成器按 `annotation_code` / `annotation_format` 键读标注，而
   audio_service.GetAudiosByIds 实返的是 `format` / `code` / `data` /
   `source_language` / `target_language`（`audio_query_handler.py:196-203`），
   `ann_field(ann,'annotation_code')` 恒 None → 每条标注都被 continue。
2. `algorithm_reference_params` 的 7 行定义把「segment 字段名」当
   annotation_code、把「segment 字段值类型」当 annotation_format，与主库
   真实标注（code=voice_llm / format=json 一统）对不上。
3. `_generate_single_param` 的 `if not value` 把合法的 `False` / `0` 当空丢弃。

本文件夹具一律用 **audio_service 真实返回形状**（code / format / data /
source_language / target_language），参考参数定义一律带真实过滤
（annotation_code=voice_llm / annotation_format=json）——现有 test_int124 之所以
没抓到本缺陷，正是它 monkeypatch 的 ref_param 没设这两个过滤，等于绕过了
出问题的分支。
"""
import ast
import os
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from algorithm_service.application.queries.reference_params_queries import (
    ReferenceParamsQueryHandler,
)
from algorithm_service.domain.services.audio_analysis import AudioAnalysisService
from algorithm_service.infrastructure.acl.audio_acl_repository import (
    AudioACLRepository,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# 主库真实标注形态（audio_service._audio_to_dict → annotations[]）
VOICE_LLM_ANNOTATION = {
    'code': 'voice_llm',
    'format': 'json',
    'data': {
        'segments': [
            {
                'query': '用户：刚才是什么声音？',
                'correct_answer': '枪声',
                'env_type': '安静室内',
                'text': ' ',
                'is_reject': False,
            },
        ],
    },
    'source_language': '',
    'target_language': '',
}

# 主库真实定义（INT-2040 订正后口径）
VOICE_LLM_DEFINITIONS = [
    {'code': 'query', 'param_type': 'text', 'annotation_code': 'voice_llm',
     'annotation_format': 'json', 'field_path': 'segments[].query', 'merge_mode': 'first'},
    {'code': 'correct_answer', 'param_type': 'text', 'annotation_code': 'voice_llm',
     'annotation_format': 'json', 'field_path': 'segments[].correct_answer',
     'merge_mode': 'join'},
    {'code': 'env_type', 'param_type': 'text', 'annotation_code': 'voice_llm',
     'annotation_format': 'json', 'field_path': 'segments[].env_type', 'merge_mode': 'join'},
    {'code': 'is_reject', 'param_type': 'text', 'annotation_code': 'voice_llm',
     'annotation_format': 'json', 'field_path': 'segments[].is_reject', 'merge_mode': 'first'},
    # 真实标注里没有这三个字段：修完仍为空是数据现状，不是缺陷
    {'code': 'pause', 'param_type': 'json', 'annotation_code': 'voice_llm',
     'annotation_format': 'json', 'field_path': 'segments[].pause', 'merge_mode': 'first'},
    {'code': 'input_lastword', 'param_type': 'json', 'annotation_code': 'voice_llm',
     'annotation_format': 'json', 'field_path': 'segments[].input_lastword',
     'merge_mode': 'first'},
    {'code': 'is_return_to_topic', 'param_type': 'boolean', 'annotation_code': 'voice_llm',
     'annotation_format': 'json', 'field_path': 'segments[].is_return_to_topic',
     'merge_mode': 'first'},
]


def _preload_context(annotations=None):
    """按 ACL 口径构造 _preload_context（走真实归一，不手写归一后的键）。"""
    raw = annotations if annotations is not None else [VOICE_LLM_ANNOTATION]
    return {
        'audio_map': {2100: object()},
        'annotation_map': {2100: AudioACLRepository._normalize_annotations(raw)},
        'duration_map': {2100: 3.2},
    }


def _config(**overrides):
    config = {
        'algorithm_type': 'voice_llm',
        'test_type': 'api',
        'audios': [{'audio_id': 2100}],
        '_record_test_type': 'api',
        '_preload_context': _preload_context(),
    }
    config.update(overrides)
    return config


def _generate(definition, config=None):
    return ReferenceParamsQueryHandler._generate_single_param(
        config or _config(), definition)


# ──────────────────── ACL 归一（键名口径，根因 1） ────────────────────

class TestAnnotationKeyNormalization:

    def test_normalizes_peer_keys_to_domain_keys(self):
        """对端 code / format → 领域 annotation_code / annotation_format。"""
        ann = AudioACLRepository._normalize_annotation(dict(VOICE_LLM_ANNOTATION))

        assert ann['annotation_code'] == 'voice_llm'
        assert ann['annotation_format'] == 'json'
        assert ann['data'] == VOICE_LLM_ANNOTATION['data']
        assert ann['source_language'] == ''
        assert ann['target_language'] == ''
        # 不留指向对端原始键的兼容分支（devloop §3.1 不写兼容层 / 双口径）
        assert 'code' not in ann
        assert 'format' not in ann

    def test_preload_annotation_map_shape(self, monkeypatch):
        """preload_audio_data 出口：annotation_map 的每条标注都是归一后的键。"""
        from algorithm_service.domain.dto import AudioDTO

        raw_audio = AudioDTO(
            id=2100, duration=3.2, annotations=[dict(VOICE_LLM_ANNOTATION)])
        monkeypatch.setattr(AudioACLRepository, 'fetch_audios_by_ids',
                            staticmethod(lambda ids: {2100: raw_audio}))

        ctx = AudioACLRepository.preload_audio_data([2100])

        ann = ctx['annotation_map'][2100][0]
        assert ann['annotation_code'] == 'voice_llm'
        assert ann['annotation_format'] == 'json'
        assert 'code' not in ann and 'format' not in ann

    def test_fetch_annotations_by_audio_id_outlet_normalized(self, monkeypatch):
        """fetch_annotations_by_audio_id 出口同样归一（另一条出口）。"""
        from algorithm_service.domain.dto import AudioDTO

        raw_audio = AudioDTO(id=2100, annotations=[dict(VOICE_LLM_ANNOTATION)])
        monkeypatch.setattr(AudioACLRepository, 'fetch_audio_by_id',
                            staticmethod(lambda audio_id: raw_audio))

        anns = AudioACLRepository.fetch_annotations_by_audio_id(2100)

        assert anns[0]['annotation_code'] == 'voice_llm'
        assert anns[0]['annotation_format'] == 'json'

    def test_empty_and_non_dict_annotations_pass_through(self):
        assert AudioACLRepository._normalize_annotations([]) == []
        assert AudioACLRepository._normalize_annotations(None) == []
        sentinel = object()
        assert AudioACLRepository._normalize_annotations([sentinel]) == [sentinel]


# ──────────────────── 定义过滤 + 取值（根因 2） ────────────────────

class TestGenerateWithRealAnnotationShape:

    def test_query_param_extracted_with_real_filter(self):
        """真实标注形状 + 真实定义过滤 → query 取到 segments[].query 原文。"""
        defs = {d['code']: d for d in VOICE_LLM_DEFINITIONS}

        param = _generate(defs['query'])

        assert param == {
            'code': 'query',
            'type': 'text',
            'value': '用户：刚才是什么声音？',
            'annotation_code': 'voice_llm',
            'annotation_format': 'json',
        }

    def test_correct_answer_and_env_type_extracted(self):
        defs = {d['code']: d for d in VOICE_LLM_DEFINITIONS}

        assert _generate(defs['correct_answer'])['value'] == '枪声'
        assert _generate(defs['env_type'])['value'] == '安静室内'

    def test_absent_segment_fields_stay_empty(self):
        """真实标注里没有 pause / input_lastword / is_return_to_topic：数据现状，为空。"""
        defs = {d['code']: d for d in VOICE_LLM_DEFINITIONS}

        for code in ('pause', 'input_lastword', 'is_return_to_topic'):
            assert _generate(defs[code]) is None, f'{code} 不应凭空造值'

    def test_format_filter_mismatch_skips_annotation(self):
        """定义仍写错格式（text / boolean）就一条都取不到——原缺陷形态锚点。"""
        stale = dict(VOICE_LLM_DEFINITIONS[0], annotation_format='text')

        assert _generate(stale) is None

    def test_annotation_code_filter_mismatch_skips_annotation(self):
        """annotation_code 填 segment 字段名（旧定义形态）同样取不到。"""
        stale = dict(VOICE_LLM_DEFINITIONS[0], annotation_code='query')

        assert _generate(stale) is None

    def test_no_compat_branch_on_peer_keys(self):
        """domain 只读归一后的键：只带 code / format 的未归一标注不被识别。"""
        config = _config(_preload_context={
            'audio_map': {2100: object()},
            # 绕过 ACL 直接塞对端原始键（模拟「做了兼容分支」的反例）
            'annotation_map': {2100: [dict(VOICE_LLM_ANNOTATION)]},
            'duration_map': {2100: 3.2},
        })

        assert _generate(VOICE_LLM_DEFINITIONS[0], config) is None


# ──────────────────── 空值判定（根因 3） ────────────────────

class TestEmptyValueJudgement:

    def test_boolean_false_is_kept(self):
        """`False` 是合法取值，不得当空丢弃（旧 `if not value` 会把 is_reject 吞掉）。"""
        param = _generate(VOICE_LLM_DEFINITIONS[3])

        assert param is not None
        assert param['value'] is False

    def test_zero_is_kept(self):
        config = _config(_preload_context={
            'audio_map': {2100: object()},
            'annotation_map': {2100: [{'annotation_code': 'voice_llm',
                                       'annotation_format': 'json',
                                       'data': {'segments': [{'pause': 0}]}}]},
            'duration_map': {2100: 3.2},
        })

        param = _generate(VOICE_LLM_DEFINITIONS[4], config)

        assert param is not None and param['value'] == 0

    @pytest.mark.parametrize('value', [None, '', []])
    def test_empty_values_dropped(self, value):
        assert ReferenceParamsQueryHandler._is_empty_value(value) is True

    @pytest.mark.parametrize('value', [False, 0, 'x', ['a'], {'segments': []}])
    def test_non_empty_values_kept(self, value):
        assert ReferenceParamsQueryHandler._is_empty_value(value) is False


# ──────────────────── speaker 提取：type 死分支已清理 ────────────────────

class TestSpeakersFromAnnotations:

    def test_reads_normalized_annotation_code(self):
        anns = {2100: [{'annotation_code': 'diarization', 'annotation_format': 'json',
                        'data': {'segments': [{'speaker': 'spk1'}]}}]}

        assert AudioAnalysisService.extract_speakers_from_annotations(2100, anns) == {'spk1'}

    def test_legacy_type_key_no_longer_recognized(self):
        """`type` 不是 audio_service 标注契约里的键，死分支已删。"""
        anns = {2100: [{'type': 'diarization',
                        'data': {'segments': [{'speaker': 'spk1'}]}}]}

        assert AudioAnalysisService.extract_speakers_from_annotations(2100, anns) == set()


# ──────────────────── 种子 / 幂等迁移口径一致 ────────────────────

def _seed_ref_params_rows():
    """AST 解析 seed_voice_llm.py 的 Step 6 ref_params 字面量（不执行脚本）。"""
    path = os.path.join(REPO_ROOT, 'scripts', 'migrations', '202609',
                        'seed_voice_llm.py')
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=path)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'ref_params'
                        for t in node.targets)
                and isinstance(node.value, ast.List)):
            return ast.literal_eval(node.value)
    raise AssertionError('seed_voice_llm.py 里没找到 ref_params 定义')


def _migration_module():
    mig_dir = os.path.join(REPO_ROOT, 'scripts', 'migrations', '202610')
    if mig_dir not in sys.path:
        sys.path.insert(0, mig_dir)
    import fix_voice_llm_reference_params_definitions as mig
    return mig


def test_seed_definitions_match_document_vocabulary():
    rows = _seed_ref_params_rows()
    by_code = {r[1]: r for r in rows}

    assert set(by_code) == {d['code'] for d in VOICE_LLM_DEFINITIONS}
    for definition in VOICE_LLM_DEFINITIONS:
        (_algo, _code, _name, param_type, annotation_code, annotation_format,
         field_path, _merge_mode, _help_text) = by_code[definition['code']]
        assert annotation_code == 'voice_llm', definition['code']
        assert annotation_format == 'json', definition['code']
        assert field_path == f'segments[].{definition["code"]}', definition['code']
        # param_type / merge_mode 与主库现值一致（全新库 == 老库订正后）
        assert param_type == definition['param_type'], definition['code']
        assert _merge_mode == definition['merge_mode'], definition['code']


def test_migration_targets_match_definitions():
    mig = _migration_module()

    assert mig.ALGORITHM_TYPE == 'voice_llm'
    assert mig.TARGET_ANNOTATION_CODE == 'voice_llm'
    assert mig.TARGET_ANNOTATION_FORMAT == 'json'
    assert dict(mig.TARGET_ROWS) == {
        d['code']: f'segments[].{d["code"]}' for d in VOICE_LLM_DEFINITIONS}


def test_migration_needs_fix_only_on_drift():
    """幂等判定：只有取值与目标不一致的行才进 UPDATE。"""
    mig = _migration_module()
    target = ('voice_llm', 'json', 'segments[].query')

    assert mig._needs_fix((25, 'query', 'voice_llm', 'text', 'query')) is True
    assert mig._needs_fix((25, 'query', 'query', 'json', 'segments[].query')) is True
    assert mig._needs_fix((25, 'query') + target) is False


def test_migration_is_wired_before_analyze():
    """迁移脚本必须进引导链，且排在 ANALYZE 兜底之前（ANALYZE 保持末位）。"""
    path = os.path.join(REPO_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
    with open(path, encoding='utf-8') as f:
        source = f.read()

    marker = "('python', 'scripts/migrations/202610/fix_voice_llm_reference_params_definitions.py'"
    analyze = "('python', 'scripts/migrations/202610/analyze_stale_statistics_int1741.py'"
    assert marker in source, '迁移脚本没接进 BOOTSTRAP_STEPS'
    assert source.index(marker) < source.index(analyze), '迁移脚本须排在 ANALYZE 之前'
