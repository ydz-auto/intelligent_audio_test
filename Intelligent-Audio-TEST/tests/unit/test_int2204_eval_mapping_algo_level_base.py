# -*- coding: utf-8 -*-
"""INT-2204：带 api_id 作用域时算法类型级映射被打底丢弃的回归单测。

背景：INT-314 冒烟门禁 S4（报告生成）在隔离栈必失败。根因是
``AlgorithmConfigCache._scoped_mapping_buckets`` 在传 ``api_id`` 时只合并了
「策略行 + 实例覆盖行」，把算法类型级（``api_id IS NULL``）的非 api 来源映射
整层丢掉：

- 隔离栈里 voice_llm 的评估映射只有算法类型级 ``source='case_config'`` 行
  （audios / background_noise / interferers，无 param profile 绑定）；
- evaluation_service 以 ``api_id=<实例>`` 调
  ``GetParamMappingForComponent`` 拿到 ``[]`` → 「无 evaluation param
  mappings」→ 用例评估 skipped → 无维度得分 → report_service
  ``_prepare_report_data`` 判断「未找到维度得分数据」直接返回 → 报告不落库，
  ``GET /reports/by_task/{id}`` 恒 404。

期望语义（spec ``api_param_profile``）：
1. ``source='api'`` 的算法类型级默认层已废弃，带作用域时只由「策略 + 实例覆盖」
   提供；
2. 其余来源（case / case_config / reference / device，含 evaluation 桶里的
   维度级行）以算法类型级行为默认层打底；
3. 优先级：实例覆盖 > 策略 > 算法级打底。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
)

ALGO = 'voice_llm'
PROFILE = 21
API_A = 11
API_B = 12
DIM_TURN = 1

RAW_ALGO_LEVEL = [
    # 算法类型级：维度级映射归入 evaluation 桶，source 保留 case_config
    {'id': 1, 'algorithm_type': ALGO, 'api_id': None, 'source': 'case_config',
     'source_param': 'audios', 'target_param': 'played_audios',
     'dimension_id': DIM_TURN, 'dimension_name': '逐轮话轮评估'},
    {'id': 2, 'algorithm_type': ALGO, 'api_id': None, 'source': 'case_config',
     'source_param': 'background_noise', 'target_param': 'background_noise',
     'dimension_id': DIM_TURN, 'dimension_name': '逐轮话轮评估'},
    # 算法类型级 + source='api'：已废弃，带作用域时不应再出现
    {'id': 3, 'algorithm_type': ALGO, 'api_id': None, 'source': 'api',
     'source_param': 'answer', 'target_param': 'transcript',
     'dimension_id': DIM_TURN, 'dimension_name': '逐轮话轮评估'},
    # 非维度级来源桶：算法类型级 reference 行
    {'id': 4, 'algorithm_type': ALGO, 'api_id': None, 'source': 'reference',
     'source_param': 'ref_text', 'target_param': 'ref_text',
     'dimension_id': None},
]


def _bare_cache(mappings=None, profile_mappings=None, bindings=None):
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = {
        'mappings': {
            ALGO: AlgorithmConfigCache._serialize_mappings(
                RAW_ALGO_LEVEL if mappings is None else mappings, None, ALGO)
        },
        'profile_mappings': (
            {PROFILE: AlgorithmConfigCache._serialize_mappings(
                profile_mappings, None, ALGO)} if profile_mappings else {}
        ),
        'api_bindings': bindings or {},
    }
    return cache


def _index(rows):
    return {m['source_param']: m for m in rows}


def test_algo_level_case_config_mapping_survives_api_scope():
    """带 api_id 但无策略绑定：算法级 case_config 维度映射必须保留。"""
    cache = _bare_cache()
    rows = cache.get_param_mapping(ALGO, 'evaluation', API_A)
    by_param = _index(rows)

    assert {'audios', 'background_noise'} <= set(by_param)
    assert by_param['audios']['target_param'] == 'played_audios'
    # 算法级 case_config 维度映射不因作用域丢失
    assert by_param['audios']['source'] == 'case_config'


def test_algo_level_api_source_mapping_deprecated_with_scope():
    """source='api' 的算法级默认层带作用域时仍不返回（只留策略/实例覆盖）。"""
    cache = _bare_cache()

    scoped = cache.get_param_mapping(ALGO, 'evaluation', API_A)
    assert 'answer' not in _index(scoped)

    # 不带作用域时算法级行仍可见（既有口径）
    unscoped = _index(cache.get_param_mapping(ALGO, 'evaluation'))
    assert {'audios', 'background_noise', 'answer'} <= set(unscoped)


def test_non_evaluation_algo_level_bucket_survives_api_scope():
    """非 evaluation 桶（reference 等）的算法级行同样打底保留。"""
    cache = _bare_cache()
    rows = cache.get_param_mapping(ALGO, 'reference', API_A)
    assert [m['source_param'] for m in rows] == ['ref_text']


def test_profile_overrides_algo_level_base_without_duplicate():
    """同一唯一键：策略行覆盖算法级打底行，且不产生重复行。"""
    profile = [
        {'id': 9, 'algorithm_type': ALGO, 'source': 'case_config',
         'source_param': 'audios', 'target_param': 'audios_v2',
         'dimension_id': DIM_TURN, 'dimension_name': '逐轮话轮评估'},
    ]
    cache = _bare_cache(profile_mappings=profile, bindings={API_A: PROFILE})
    rows = cache.get_param_mapping(ALGO, 'evaluation', API_A)
    audios = [m for m in rows if m['source_param'] == 'audios']

    assert len(audios) == 1
    assert audios[0]['target_param'] == 'audios_v2'
    # 未被策略覆盖的打底行仍保留
    assert 'background_noise' in _index(rows)


def test_two_apis_share_base_without_leaking_instance_rows():
    """算法级打底对多个 API 一致可见；实例行不串到别的 API。"""
    override = [
        {'id': 10, 'algorithm_type': ALGO, 'api_id': API_A,
         'source': 'case_config', 'source_param': 'audios',
         'target_param': 'audios_a', 'dimension_id': DIM_TURN,
         'dimension_name': '逐轮话轮评估'},
    ]
    cache = _bare_cache(mappings=RAW_ALGO_LEVEL + override, bindings={})
    a_rows = _index(cache.get_param_mapping(ALGO, 'evaluation', API_A))
    b_rows = _index(cache.get_param_mapping(ALGO, 'evaluation', API_B))

    assert a_rows['audios']['target_param'] == 'audios_a'
    assert a_rows['audios']['api_id'] == API_A
    assert b_rows['audios']['target_param'] == 'played_audios'
    assert b_rows['audios']['api_id'] is None
    assert 'background_noise' in b_rows
