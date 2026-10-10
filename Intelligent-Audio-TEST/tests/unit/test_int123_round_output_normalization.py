# -*- coding: utf-8 -*-
"""INT-123 守卫：API 多轮 rounds[].output 纯文本串口径归一，评估整链不崩。

原缺陷（INT-95 主链实机复验，任务 505 / result 4860）：API 多轮链
（APISessionExecutor._aggregate_round_results）产出的 rounds[].output 是
voice_llm 文本回复（纯 str）、轮次编号在 round_number 键（1-indexed），
而评估侧四处按「已映射 dict + round 键（0-indexed）」假定取值：

- round_data_builder._build_single_round: output.get(target_param) →
  'str' object has no attribute 'get'，EvaluateCase gRPC 整链失败；
- round_data_builder._extract_round_eval_data: 非 dict output 被静默丢弃；
- task_dispatcher._build_task_data / endpoint_worker._build_evaluation_context:
  ref_output.get(key) 同型崩溃点。

且执行侧 api_session_executor.execute 把 _submit_evaluation 罩在
except Exception → update_task_case_failure 里，评估提交失败把
execution_status=completed 的用例整体误判 failed。

守卫（纯单测，不触真实 DB/gRPC/OSS/Redis）：
1. normalize_round_output / normalize_round_index 归一口径矩阵；
2. _build_single_round 用 result 4860 实测形状不再崩，轮次归一为 0-indexed；
3. _build_rounds_list 全链（mock 映射）构建出 3 轮评估数据；
4. _build_task_data / _build_evaluation_context ref_output 提取不崩；
5. 评估提交失败仅补 evaluation_status 终态，execution_status 不被动，
   update_task_case_failure 不再被调用。
"""
import os
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.utils.round_data_utils import normalize_round_index, normalize_round_output
from shared.utils.status_constants import EvaluationStatus


# result 4860 实测形状（gRPC JSON 往返后 round_number 为 str，1-indexed）
API_MULTI_ROUND_ALGO_RESULT = {
    'text_output': '你好，有什么可以帮助你的？ 你好，有什么可以帮助你的？',
    'round_count': 3,
    'success_count': 3,
    'total_latency': 3.658,
    'avg_latency': 1.223,
    'rounds': [
        {'round_number': '1', 'input': '', 'input_type': 'text',
         'output': '你好，有什么可以帮助你的？', 'output_audio_path': None,
         'latency': 3.024, 'response_metrics': {'latency': 0.716}, 'success': True},
        {'round_number': '2', 'input': '', 'input_type': 'text',
         'output': '你好，有什么可以帮助你的？', 'output_audio_path': None,
         'latency': 0.304, 'response_metrics': {'latency': 0.26}, 'success': True},
        {'round_number': '3', 'input': '', 'input_type': 'text',
         'output': '你好，有什么可以帮助你的？', 'output_audio_path': None,
         'latency': 0.34, 'response_metrics': {'latency': 0.294}, 'success': True},
    ],
}


# ==================== 1. 归一口径矩阵 ====================

def test_normalize_round_output_matrix():
    assert normalize_round_output({'answer': 'a'}) == {'answer': 'a'}
    assert normalize_round_output('你好') == {'text': '你好'}
    assert normalize_round_output('') == {'text': ''}
    assert normalize_round_output(None) == {}
    assert normalize_round_output(123) == {}


def test_normalize_round_index_matrix():
    # E2E 链：round 键 0-indexed
    assert normalize_round_index({'round': 0}) == 0
    assert normalize_round_index({'round': 2}) == 2
    assert normalize_round_index({'round': '1'}) == 1
    # API 多轮链：round_number 1-indexed（gRPC JSON 往返后可能为 str）
    assert normalize_round_index({'round_number': 1}) == 0
    assert normalize_round_index({'round_number': '3'}) == 2
    # 两者皆缺 / 异常形态 → 0
    assert normalize_round_index({}) == 0
    assert normalize_round_index({'round_number': 0}) == 0
    assert normalize_round_index({'round_number': True}) == 0
    assert normalize_round_index({'round': True}) == 0
    assert normalize_round_index(None) == 0
    # round 键优先（E2E 结构同时携带 round_number 时以 round 为准）
    assert normalize_round_index({'round': 1, 'round_number': '5'}) == 1


# ==================== 2/3. 评估侧构建链（复现栈） ====================

from evaluation_service.domain.services.evaluation_service.round_data_builder import (
    RoundDataBuilderMixin,
)


class _Host(RoundDataBuilderMixin):
    """最小宿主：仅混入被测能力。"""

    def __init__(self):
        self._task_acl_repo = None

    def _log(self, **kwargs):
        pass


@pytest.fixture()
def acl_mock(monkeypatch):
    import evaluation_service.infrastructure.acl as acl_pkg
    instance = acl_pkg.algorithm_acl_repository
    monkeypatch.setattr(instance, 'get_param_mapping',
                        lambda *a, **k: [{'source': 'device', 'source_param': 'answer',
                                          'target_param': 'answer'}])
    monkeypatch.setattr(instance, 'get_reference_params_list', lambda *a, **k: [])
    return instance


def test_build_single_round_with_str_output_no_crash(acl_mock):
    host = _Host()
    field_mapper = MagicMock()
    field_mapper.get_mapped_device_output_field_keys.return_value = ['answer']

    item = host._build_single_round(
        API_MULTI_ROUND_ALGO_RESULT['rounds'][1], None,
        [{'source': 'device', 'source_param': 'answer', 'target_param': 'answer'}],
        'api', 'voice_llm', 505, 'tc1',
        lambda *a, **k: [], lambda *a, **k: {},
    )
    assert item['round'] == 1  # round_number '2' → 0-indexed
    assert isinstance(item, dict)


def test_build_rounds_list_api_multi_round_full_chain(acl_mock):
    """复现 case_evaluation._build_rounds_list → _build_single_round 原崩栈。"""
    host = _Host()
    field_mapper = MagicMock()
    field_mapper.get_mapped_device_output_field_keys.return_value = ['answer']

    rounds_list = host._build_rounds_list(
        API_MULTI_ROUND_ALGO_RESULT, None, field_mapper,
        'voice_llm', 'api', 505, 'tc1',
    )
    assert len(rounds_list) == 3
    assert [item['round'] for item in rounds_list] == [0, 1, 2]


def test_build_rounds_list_e2e_dict_output_unchanged(acl_mock):
    """E2E 已映射 dict 口径回归：映射字段照常取值，round 保持 0-indexed。"""
    host = _Host()
    field_mapper = MagicMock()
    field_mapper.get_mapped_device_output_field_keys.return_value = ['answer']
    e2e_algo_result = {'rounds': [
        {'round': 0, 'output': {'answer': '答案A'}, 'latency': 1.0},
        {'round': 1, 'output': {'answer': '答案B'}, 'latency': 1.2},
    ]}
    rounds_list = host._build_rounds_list(
        e2e_algo_result, None, field_mapper,
        'voice_llm', 'e2e', 505, 'tc1',
    )
    assert [item['round'] for item in rounds_list] == [0, 1]
    assert rounds_list[0]['answer'] == '答案A'
    assert rounds_list[1]['answer'] == '答案B'


# ==================== 4. 分发侧 ref_output 提取 ====================

def test_build_task_data_with_str_round_output_no_crash():
    from evaluation_service.infrastructure.evaluation_api.task_dispatcher import (
        TaskDispatcherMixin,
    )

    host = TaskDispatcherMixin()
    field_mapper = MagicMock()
    field_mapper.get_mapped_device_output_field_keys.return_value = ['answer']

    task_data = host._build_task_data(
        505, 4860, 'tc1', API_MULTI_ROUND_ALGO_RESULT,
        {'id': 72, 'name': '逐轮话轮评估'}, [('dim', 1)],
        'voice_llm', 'api', None, field_mapper, {},
        rounds_list=[{'round': 0}],
    )
    # 原 ref_output.get(key) 对 str 崩溃；归一后安全取字段（文本链无 answer → None）
    assert task_data['algorithm_result'] is API_MULTI_ROUND_ALGO_RESULT


def test_endpoint_worker_context_with_str_round_output_no_crash(monkeypatch):
    from evaluation_service.infrastructure.evaluation_api.endpoint_worker import (
        EndpointWorker,
    )

    worker = object.__new__(EndpointWorker)
    worker.eval_service = MagicMock()
    worker.eval_service.api_client.build_payload.return_value = {}
    monkeypatch.setattr(
        EndpointWorker, '_log', lambda self, **kwargs: None, raising=False)

    payload = worker._build_evaluation_context(
        505, 'tc1', API_MULTI_ROUND_ALGO_RESULT,
        {'id': 72, 'name': '逐轮话轮评估', 'input_params': [], 'api_settings': {}},
        'voice_llm', ['answer'], 72, {}, {},
        group_items=[({'id': 72, 'task_type_code': 'turn_eval'}, 1)],
    )
    assert isinstance(payload, dict)


# ==================== 5. 评估提交失败不降级执行终态 ====================

class _StubExecutor:
    def __init__(self):
        self.execution_engine = MagicMock()
        self._result_processor = MagicMock()
        self._result_processor.create_multi_round_test_result.return_value = 4860
        self._concurrency = MagicMock()
        self._concurrency.acquire.return_value = True

    def _handle_control(self, task_id):
        pass

    def _log(self, **kwargs):
        pass


def test_execute_eval_submit_failure_keeps_execution_completed(monkeypatch):
    """EvaluateCase 提交失败：TaskCase 仅补 evaluation_status=FAILED，
    execution_status 不被动，update_task_case_failure 不再被调用。"""
    import api_test_service.core.api_session_executor as mod

    task_acl = MagicMock()
    monkeypatch.setattr(mod, '_task_data_acl', task_acl)
    algo_acl = MagicMock()
    algo_acl.extract_case_all_params.return_value = {'evaluation': {}}
    monkeypatch.setattr(mod, '_algo_acl', algo_acl)
    eval_acl = MagicMock()
    eval_acl.submit_evaluate_case.side_effect = RuntimeError(
        "EvaluateCase gRPC 调用失败: 'str' object has no attribute 'get'")
    monkeypatch.setattr(mod, '_evaluation_acl', eval_acl)

    executor = _StubExecutor()
    ex = mod.APISessionExecutor(executor)
    api_config = MagicMock()
    api_config.id = 19
    api_config.default_max_process = 1

    ex.execute(505, 9001,
               {'case_name': 'API 多轮用例', 'test_case_id': 'tc1',
                'api_configs': [api_config], 'api_specific_config': {}},
               {'rounds': []})

    executor._result_processor.update_task_case_failure.assert_not_called()
    # 终态回写：只带 evaluation_status 与 error_message，不触 execution_status
    kwargs = task_acl.update_task_case_status.call_args.kwargs
    assert kwargs['evaluation_status'] == EvaluationStatus.FAILED
    assert 'execution_status' not in kwargs
    assert '评估提交失败' in kwargs['error_message']
    # 结果照常创建成功（执行成功事实保留）
    assert executor._result_processor.create_multi_round_test_result.call_args.kwargs['success'] is True


def test_finalize_eval_submit_failure_survives_status_write_error(monkeypatch):
    """终态回写自身失败不外抛（收口路径不得再打断执行循环）。"""
    import api_test_service.core.api_session_executor as mod

    task_acl = MagicMock()
    task_acl.update_task_case_status.side_effect = RuntimeError('grpc down')
    monkeypatch.setattr(mod, '_task_data_acl', task_acl)

    ex = mod.APISessionExecutor(_StubExecutor())
    ex._finalize_evaluation_submit_failure(505, 'tc1', 19, RuntimeError('boom'))
