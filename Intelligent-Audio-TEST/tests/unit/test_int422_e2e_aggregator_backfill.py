# -*- coding: utf-8 -*-
"""INT-422 回归：E2E 评估聚合回填不再静默失败（NameError 被吞）。

缺陷：e2e_test_service/application/services/e2e_aggregator.py 在
update_algorithm_result_evaluation 中调用 deserialize_algorithm_result，
但 import 区漏导该名字，NameError 被 :41 的 try 吞掉，
导致"把各轮评估分数回填到 rounds[].evaluation 并计算 aggregated"的
设计功能 100% 静默失败（result_id 每次运行必现 [aggregate] 更新失败）。

本用例锁定修复：
- 模块必须能解析 deserialize_algorithm_result（漏 import 回归防线）；
- update_algorithm_result_evaluation 真实执行回填（修复前该路径 NameError，
  update_test_result_algorithm_result 永不被调用）；
- 覆盖双重序列化历史数据（algorithm_result 为 JSON 字符串）兼容；
- 聚合回填失败升级为 WARNING 级任务告警（不静默存活）。
"""
import json
import os
from unittest.mock import MagicMock, patch

# BaseConfig 在 import 时校验环境变量（与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import e2e_test_service.application.services.e2e_aggregator as aggregator_mod
from e2e_test_service.application.services.e2e_aggregator import E2EAggregator
from e2e_test_service.domain.dto.e2e_acl_dto import DimensionResultDTO
from e2e_test_service.domain.dto import e2e_acl_dto as e2e_dto  # TestResultDTO 经模块引用，避免 pytest 误采集
from shared.utils.redis_pubsub import EventChannel, EventType


class _FakeExecutor:
    """最小执行器宿主：仅提供 _log 供聚合器记录（聚合器通过 self._executor._log 取日志）。"""

    def __init__(self):
        self.logs = []

    def _log(self, level, content, **kwargs):
        self.logs.append({'level': level, 'content': content, **kwargs})


def _make_aggregator(algorithm_result, dim_results, repo=None):
    """构造带 mock ACL 仓储的 E2EAggregator。

    __init__ 内部实例化 TaskDataAclRepositoryImpl()，patch 后返回传入的 repo。
    调用方传入自定义 repo 时由其自行配置返回语义；默认走通用 TestResult 回填。
    """
    executor = _FakeExecutor()
    if repo is None:
        repo = MagicMock()
        repo.get_test_result_by_id.return_value = e2e_dto.TestResultDTO(id=51, algorithm_result=algorithm_result)
        repo.get_dimension_results_by_result_ids.return_value = dim_results
        repo.update_test_result_algorithm_result.return_value = True
    with patch('e2e_test_service.application.services.e2e_aggregator.TaskDataAclRepositoryImpl',
               return_value=repo):
        aggregator = E2EAggregator(executor)
    return aggregator, executor, repo


def _algo_result_dict():
    """模拟 _finalize_rounds 构建后的 algo_result（evaluation 待回填）。"""
    return {
        'test_type': 'e2e',
        'algorithm_type': 'translation',
        'total_rounds': 2,
        'rounds': [
            {'round_number': 0, 'output': {'record_file': 'r0.wav'}},
            {'round_number': 1, 'output': {'record_file': 'r1.wav'}},
        ],
        'aggregated': {},
    }


def _dim_results(*items):
    """构造维度评估结果：items 为 (round_number, dimension_name, score)。"""
    return [
        DimensionResultDTO(
            result_id=51,
            dimension_name=name,
            round_number=rn,
            score=score,
            evaluation_status='completed',
        )
        for rn, name, score in items
    ]


class TestDeserializeImportGuard:
    """漏 import 回归防线：模块必须能解析 deserialize_algorithm_result。"""

    def test_module_exposes_deserialize_algorithm_result(self):
        assert hasattr(aggregator_mod, 'deserialize_algorithm_result')


class TestAggregationBackfill:
    """update_algorithm_result_evaluation 真实回填（修复前必 NameError 且不写库）。"""

    def test_backfill_writes_rounds_evaluation_and_aggregated(self):
        aggregator, executor, repo = _make_aggregator(
            json.dumps(_algo_result_dict()),  # 双重序列化历史数据
            _dim_results((0, 'WER', 0.85), (1, 'WER', 0.75), (0, 'LLM_judge', 0.9)),
        )

        aggregator.update_algorithm_result_evaluation('t1', 51)

        repo.update_test_result_algorithm_result.assert_called_once()
        result_id, written = repo.update_test_result_algorithm_result.call_args[0]
        assert result_id == 51
        written_obj = json.loads(written)

        assert written_obj['rounds'][0]['evaluation'] == {'wer': 0.85, 'llm_judge': 0.9}
        assert written_obj['rounds'][1]['evaluation'] == {'wer': 0.75}
        assert written_obj['aggregated']['avg_wer'] == 0.8
        assert written_obj['aggregated']['avg_llm_judge'] == 0.9

        # 回填过程不得有任何 ERROR（NameError 被吞时期该断言必失败）
        assert not any(l['level'] == 'ERROR' for l in executor.logs)

    def test_backfill_dict_input_no_double_serialization(self):
        # algorithm_result 已是 dict（非历史双重序列化）也应正常工作
        aggregator, executor, repo = _make_aggregator(
            _algo_result_dict(),
            _dim_results((0, 'WER', 0.85), (1, 'WER', 0.75)),
        )

        aggregator.update_algorithm_result_evaluation('t1', 51)

        repo.update_test_result_algorithm_result.assert_called_once()
        _, written = repo.update_test_result_algorithm_result.call_args[0]
        written_obj = json.loads(written)
        assert written_obj['rounds'][0]['evaluation'] == {'wer': 0.85}
        assert written_obj['rounds'][1]['evaluation'] == {'wer': 0.75}
        assert not any(l['level'] == 'ERROR' for l in executor.logs)

    def test_missing_test_result_returns_without_error(self):
        # TestResult 不存在分支：仅记 ERROR 日志，不写库也不抛
        repo = MagicMock()
        repo.get_test_result_by_id.return_value = None
        aggregator, executor, _ = _make_aggregator('{}', [], repo=repo)

        aggregator.update_algorithm_result_evaluation('t1', 51)

        repo.update_test_result_algorithm_result.assert_not_called()
        assert any(l['level'] == 'ERROR' for l in executor.logs)


class TestBackfillFailureEscalation:
    """聚合回填失败升级为 WARNING 级任务告警（不静默存活）。

    审计 P2：不得整类 patch EventManager——那会掩盖 EventManager() 无参构造
    TypeError（生产死代码），测试假绿灯。本用例构造真 EventManager 并仅
    patch EventBus.publish 锁定真实发布路径：若实现回退为 EventManager()
    无参构造，emit_alert 前的 TypeError 会使 publish 不被调用，断言必失败。
    """

    def test_failure_publishes_warning_alert(self):
        repo = MagicMock()
        repo.get_test_result_by_id.side_effect = RuntimeError('db down')
        aggregator, executor, _ = _make_aggregator('{}', [], repo=repo)

        with patch('shared.utils.redis_pubsub.EventBus.publish') as mock_publish:
            aggregator.update_algorithm_result_evaluation('t1', 51)

        mock_publish.assert_called_once()
        channel, event_type, payload = mock_publish.call_args[0]
        assert channel == EventChannel.TASK_EVENTS
        assert event_type == EventType.TASK_ALERT
        assert payload['event'] == 'error_alert'
        assert payload['task_id'] == 't1'  # task_id 透传
        assert payload['data']['level'] == 'warning'  # WARNING 级任务告警
        assert any(l['level'] == 'ERROR' for l in executor.logs)
