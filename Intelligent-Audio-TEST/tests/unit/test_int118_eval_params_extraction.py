# -*- coding: utf-8 -*-
"""INT-118 守卫：voice_llm 评估参数提取链修复（ExtractCaseAllParams 不再 AttributeError）。

原缺陷（INT-95 主链实机验收，task 494）：algorithm_service DDD 迁移时
`ReferenceParamsGeneratorQueryHandler` 留成 `pass` 空壳，
`CaseParameterQueryHandler.get_evaluation_params` 的 reference /
adjusted_reference 分支调它的 `get_all_reference_params` →
AttributeError("type object 'ReferenceParamsGeneratorQueryHandler' has no
attribute 'get_all_reference_params'") → ExtractCaseAllParams gRPC 整链失败 →
api_test_service ACL 回退 ExtractedCaseParamsDTO()（evaluation=None）→
`eval_params['algorithm_type']` 对 None 赋值 →
"'NoneType' object does not support item assignment" → 多轮任务整链 failed。

修复（commit 49048302）：
1. 两处调用点改接真身 `ReferenceParamsQueryHandler`（reference_params_queries），
   删除死壳类；
2. api_test_service `_submit_evaluation` 评估参数为空时显式 WARNING
   （容错路径守卫在 tests/integration 链级用例，本文件不触 gRPC）。

本文件为纯单测：真实 QueryHandler 代码路径 + 桩掉 config cache（映射数据
边界），不触 DB/gRPC/OSS/Redis。映射数据形状对齐 ParamMapping PO 序列化
（_get_evaluation_mappings 输出：source/source_param/target_param/
transform_type）。
"""
import os

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from algorithm_service.application.queries import case_parameter_queries as cpq
from algorithm_service.application.queries.case_parameter_queries import (
    CaseParameterQueryHandler,
)


# ──────────────────────────── 桩与数据 ────────────────────────────

class _FakeConfigCache:
    """config cache 最小替身：只提供 get_evaluation_params 消费的三个入口。"""

    def __init__(self, evaluation_mappings):
        self._evaluation_mappings = evaluation_mappings

    def get_param_mapping(self, algorithm_type, component_type):
        assert component_type == 'evaluation'
        return self._evaluation_mappings

    def get_device_params(self, algorithm_type):
        return []

    def get_api_params(self, algorithm_type):
        return []


# voice_llm 评估映射（reference / adjusted_reference / case 三来源，
# 覆盖 49048302 修复的两个调用点 + case 分支）
VOICE_LLM_EVAL_MAPPINGS = [
    {'source': 'reference', 'source_param': 'ref_text',
     'target_param': 'reference_text', 'transform_type': 'none'},
    {'source': 'adjusted_reference', 'source_param': 'adjusted_ref',
     'target_param': 'adjusted_reference_text', 'transform_type': 'none'},
    {'source': 'case', 'source_param': 'scene',
     'target_param': 'scene_name', 'transform_type': 'none'},
]

# voice_llm 多轮用例形态：算法参数为 [{field_code, field_value}] 独立列，
# 参考参数为 [{code, type, value}] 直接列表（get_all_reference_params
# normalize 路径）
VOICE_LLM_CASE_CONFIG = {
    'algorithm_type': 'voice_llm',
    'algorithm_params': [{'field_code': 'scene', 'field_value': 'narrative'}],
    'reference_params': [
        {'code': 'ref_text', 'type': 'text', 'value': '今天天气怎么样'},
        {'code': 'adjusted_ref', 'type': 'text', 'value': '拒识话术标准文本'},
    ],
}


@pytest.fixture()
def voice_llm_cache(monkeypatch):
    """把 case_parameter_queries 模块内的 get_config_cache 指到替身。

    修复点在 QueryHandler 调用侧（ReferenceParamsQueryHandler 接线），
    cache 是映射数据边界，桩掉不影响被测代码路径。
    """
    fake = _FakeConfigCache(VOICE_LLM_EVAL_MAPPINGS)
    monkeypatch.setattr(cpq, 'get_config_cache', lambda: fake)
    return fake


# ──────────────────────────── 根因回归 ────────────────────────────

def test_dead_shell_class_removed():
    """死壳类 ReferenceParamsGeneratorQueryHandler 已删除（防回潮探针）。"""
    assert not hasattr(cpq, 'ReferenceParamsGeneratorQueryHandler'), (
        '死壳类 ReferenceParamsGeneratorQueryHandler 不应再存在'
        '（存在即回退到 AttributeError 崩溃链）')


def test_get_evaluation_params_reference_source_extracts_value(voice_llm_cache):
    """reference 分支：修复前此调用抛
    AttributeError('...no attribute get_all_reference_params')。"""
    params = CaseParameterQueryHandler.get_evaluation_params(
        VOICE_LLM_CASE_CONFIG, test_type='api')
    assert params.get('reference_text') == '今天天气怎么样'


def test_get_evaluation_params_adjusted_reference_source_extracts_value(
        voice_llm_cache):
    """adjusted_reference 分支：同型崩溃点（case_parameter_queries.py:147）。"""
    params = CaseParameterQueryHandler.get_evaluation_params(
        VOICE_LLM_CASE_CONFIG, test_type='api')
    assert params.get('adjusted_reference_text') == '拒识话术标准文本'


def test_get_evaluation_params_case_source_extracts_value(voice_llm_cache):
    """case 分支回归：算法参数 [{field_code, field_value}] 归一后取值。"""
    params = CaseParameterQueryHandler.get_evaluation_params(
        VOICE_LLM_CASE_CONFIG, test_type='api')
    assert params.get('scene_name') == 'narrative'


def test_get_evaluation_params_missing_ref_param_yields_no_key(
        voice_llm_cache):
    """参考参数缺 code 匹配项 → 目标键不注入（不抛错、不注入 None）。"""
    config = dict(VOICE_LLM_CASE_CONFIG)
    config['reference_params'] = [
        {'code': 'other_ref', 'type': 'text', 'value': 'x'}]
    params = CaseParameterQueryHandler.get_evaluation_params(
        config, test_type='api')
    assert 'reference_text' not in params
    assert 'adjusted_reference_text' not in params
    assert params.get('scene_name') == 'narrative'


# ──────────────────────────── ExtractCaseAllParams 载荷 ────────────────────────────

def test_get_all_params_voice_llm_evaluation_nonempty(voice_llm_cache):
    """get_all_params（ExtractCaseAllParams servicer 底座）对 voice_llm 配置
    返回非空 evaluation 段——api_test_service._submit_evaluation 消费的
    正是这个载荷。修复前整条 gRPC 失败 → ACL 回退 evaluation=None。"""
    all_params = CaseParameterQueryHandler.get_all_params(VOICE_LLM_CASE_CONFIG)
    assert all_params['algorithm_type'] == 'voice_llm'
    assert isinstance(all_params['evaluation'], dict)
    assert all_params['evaluation'], 'evaluation 参数不应为空'
    assert all_params['evaluation'].get('reference_text') == '今天天气怎么样'


def test_get_all_params_device_api_sections_present(voice_llm_cache):
    """device/api 段与 evaluation 段同源提取（extract_case_all_params 四服务
    消费方契约：三段键恒存在）。"""
    all_params = CaseParameterQueryHandler.get_all_params(VOICE_LLM_CASE_CONFIG)
    assert set(all_params) == {'algorithm_type', 'device', 'api', 'evaluation'}
    assert all_params['device'] == {}
    assert all_params['api'] == {}
