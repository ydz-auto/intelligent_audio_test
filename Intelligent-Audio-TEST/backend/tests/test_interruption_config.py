# -*- coding: utf-8 -*-
"""打断 / 回到原话题 配置链路测试（不依赖真实数据库）

设计：
- is_interruption：config.rounds 结构字段（执行控制），schema 接受
- is_return_to_topic：reference_params 体系，经 source='reference' 映射，_build_rounds_list 按轮读
- original_topic：用例级 config 字段（无标注来源），evaluate_case 从 config 注入 kwargs
"""
import pytest


# ────────────────────────────────────────────────────────
# 1. Schema 字段接受与序列化（纯 pydantic，无 DB）
# ────────────────────────────────────────────────────────
def test_round_config_item_accepts_is_interruption_snake():
    from backend.schemas.testcase import RoundConfigItem

    item = RoundConfigItem(round_number=2, is_interruption=True)
    assert item.is_interruption is True


def test_round_config_item_accepts_is_interruption_camel():
    from backend.schemas.testcase import RoundConfigItem

    item = RoundConfigItem.model_validate({'roundNumber': 3, 'isInterruption': True})
    assert item.is_interruption is True
    dumped = item.model_dump(by_alias=True, exclude_none=True)
    assert dumped['is_interruption'] is True  # alias=snake, camelCase 由 success_response 层转换


def test_test_case_config_accepts_original_topic():
    from backend.schemas.testcase import TestCaseConfig

    cfg = TestCaseConfig.model_validate({'originalTopic': '今天聊一下天气'})
    assert cfg.original_topic == '今天聊一下天气'
    dumped = cfg.model_dump(by_alias=True, exclude_none=True)
    assert dumped['original_topic'] == '今天聊一下天气'


# ────────────────────────────────────────────────────────
# 2. _build_rounds_list 经 source='reference' 按轮读 is_return_to_topic（无 DB）
#    模拟：reference 映射 + ref param 定义 + 按轮 ref 文件内容
# ────────────────────────────────────────────────────────
def test_build_rounds_list_reads_is_return_to_topic_from_reference(monkeypatch):
    from backend.services.evaluation.evaluation_service import EvaluationService
    import backend.utils.algorithm.case_parameter_extractor as cpe_mod

    # 打桩 loader：返回一条 source='reference' 映射 + is_return_to_topic 参考参数定义
    class _StubLoader:
        def get_param_mapping(self, algorithm_type, kind):
            return [{'source': 'reference', 'source_param': 'is_return_to_topic',
                     'target_param': 'is_return_to_topic'}]

        def get_reference_params(self, algorithm_type):
            return [{'code': 'is_return_to_topic', 'type': 'boolean'}]

    monkeypatch.setattr(cpe_mod.CaseParameterExtractor, '_get_loader', lambda: _StubLoader())

    # 打桩按轮 ref 文件读取：round0→True, round1→False
    def _fake_load_round_ref_file(col, round_number):
        val = (round_number == 1)  # round_number 是 1-indexed
        return {'is_return_to_topic': {'code': 'is_return_to_topic', 'type': 'boolean', 'value': val}}

    monkeypatch.setattr(cpe_mod.CaseParameterExtractor, '_load_round_ref_file', _fake_load_round_ref_file)

    class _StubFieldMapper:
        def get_mapped_device_output_field_keys(self, algorithm_type):
            return []

    class _StubSelf:
        @staticmethod
        def _log(**kwargs):
            pass

    algorithm_result = {'rounds': [{'round': 0, 'output': {}}, {'round': 1, 'output': {}}]}
    rounds_list = EvaluationService._build_rounds_list(
        _StubSelf(), algorithm_result, 'fake_col', _StubFieldMapper(),
        'voice_llm', 'e2e', task_id=None, test_case_id=None,
    )
    assert len(rounds_list) == 2
    assert rounds_list[0]['is_return_to_topic'] is True
    assert rounds_list[1]['is_return_to_topic'] is False


# ────────────────────────────────────────────────────────
# 3. 旧"随结果携带 is_return_to_topic"已撤销——build_algorithm_result 不应再写出该字段
# ────────────────────────────────────────────────────────
def test_build_algorithm_result_does_not_carry_is_return_to_topic(monkeypatch):
    from backend.services.execution.e2e_aggregator import E2EAggregator

    class _StubFieldMapper:
        def get_mapped_device_output_fields(self, algorithm_type):
            return []

    import backend.utils.algorithm.field_mapper as fm_mod
    monkeypatch.setattr(fm_mod, 'get_field_mapper', lambda: _StubFieldMapper())

    class _StubExecutor:
        @staticmethod
        def _log(**kwargs):
            pass

    agg = E2EAggregator(_StubExecutor())
    case_config = {'rounds': [{'audios': [], 'is_return_to_topic': True}]}
    all_round_results = [{'round_number': 0, 'response_time': 1.0}]
    result = agg.build_algorithm_result('tid', all_round_results, case_config, 'voice_llm')
    # is_return_to_topic 走 reference 体系，不应再出现在 algo_result.rounds 里
    assert 'is_return_to_topic' not in result['rounds'][0]
