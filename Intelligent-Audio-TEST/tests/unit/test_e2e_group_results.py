# -*- coding: utf-8 -*-
"""E2E 组执行结果（e2e_test_service）：每设备一条 TestResult、逐设备收口。

规格：specs/group-execution/spec.md
评估侧按路由行（results_by_device[row.device_id]）逐行取结果，缺行会卡住
评估收口；因此组执行必须每台设备一条结果、逐设备聚合/评估/回写，
用例完成事件只在组内最后一台设备回写时发布一次。
"""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor

_CASE_CONFIG = {'rounds': [{'round_number': 1, 'audios': []}]}


def _host():
    ex = E2EExecutor.__new__(E2EExecutor)
    ex._log = MagicMock()
    ex._handle_control = MagicMock()
    ex._aggregator = MagicMock()
    ex._aggregator.build_algorithm_result.return_value = {'rounds': [{'output': {}}]}
    ex._aggregator.process_results.return_value = True
    ex._task_data_repo = MagicMock()
    ex._device_manager = MagicMock()
    ex._device_manager.get_ui_capture_degraded.return_value = None
    ex._save_result = MagicMock(side_effect=[11, 22])
    ex._prepare_audio_files = MagicMock()
    ex._audio_local_paths = {}
    return ex


class TestPrepareRoundResults:

    def test_one_result_per_device(self):
        """组执行准备阶段：每台设备各预创建一条 TestResult。"""
        ex = _host()
        ex._device_manager.get_device_info.return_value = {
            'success': True,
            'data': {'device_info_list': [
                {'device_id': 1, 'device_name': 'd1', 'device_sn': 'SN-A'},
                {'device_id': 2, 'device_name': 'd2', 'device_sn': 'SN-B'},
            ]},
        }

        device_info_list, result_ids = ex._prepare_rounds(
            't1', 'tc1',
            data={'case_algorithm_params': None, 'case_name': 'c', 'test_case_id': 'c1'},
            case_config=_CASE_CONFIG, algorithm_type='voice_llm',
            case_field_values={}, rounds=[{'round_number': 1}],
            test_case_id='c1', device_ids=[1, 2],
        )

        assert len(device_info_list) == 2
        assert result_ids == {1: 11, 2: 22}
        saved_device_ids = [c.kwargs['device_id'] for c in ex._save_result.call_args_list]
        assert saved_device_ids == [1, 2]

    def test_degrade_trace_filtered_per_device(self):
        """降级留痕只写进对应设备的结果，不串到其他设备。"""
        ex = _host()
        ex._device_manager.get_device_info.return_value = {
            'success': True,
            'data': {'device_info_list': [
                {'device_id': 1, 'device_name': 'd1', 'device_sn': 'SN-A'},
                {'device_id': 2, 'device_name': 'd2', 'device_sn': 'SN-B'},
            ]},
        }
        ex._device_manager.get_ui_capture_degraded.return_value = [
            {'device_name': 'd1', 'degrade_reason': 'hypium_missing'}]

        ex._prepare_rounds(
            't1', 'tc1',
            data={'case_algorithm_params': None, 'case_name': 'c', 'test_case_id': 'c1'},
            case_config=_CASE_CONFIG, algorithm_type='voice_llm',
            case_field_values={}, rounds=[{'round_number': 1}],
            test_case_id='c1', device_ids=[1, 2],
        )

        assert ex._save_result.call_args_list[0].kwargs['result_data']['ui_capture_degraded'] == [
            {'device_name': 'd1', 'degrade_reason': 'hypium_missing'}]
        assert 'ui_capture_degraded' not in ex._save_result.call_args_list[1].kwargs['result_data']


class TestGroupResultsMapping:

    def test_group_results_by_device(self):
        """扁平结果按 device_id 拆分为设备分组。"""
        from e2e_test_service.application.services.e2e_executor.finalization_mixin import (
            FinalizationMixin,
        )

        grouped = FinalizationMixin._group_results_by_device(
            [{'device_id': 1, 'round_number': 1}, {'device_id': 2, 'round_number': 1},
             {'device_id': 1, 'round_number': 2}],
            {1: 11, 2: 22},
        )
        assert [len(grouped[1]), len(grouped[2])] == [2, 1]

    def test_group_results_falls_back_to_device_sn(self):
        """采集结果缺 device_id → 按 device_sn 归属到对应设备。"""
        ex = _host()
        grouped = ex._group_tagged_results(
            [{'device_id': None, 'device_sn': 'SN-B', 'round_number': 1}],
            {1: 11, 2: 22},
            {'SN-B': 2},
        )
        assert list(grouped.keys()) == [2]


class TestFinalizePerDevice:

    def _finalize(self):
        ex = _host()
        device_info_list = [
            {'device_id': 1, 'device_name': 'd1', 'device_sn': 'SN-A'},
            {'device_id': 2, 'device_name': 'd2', 'device_sn': 'SN-B'},
        ]
        with patch(
            'e2e_test_service.application.services.e2e_executor.finalization_mixin.write_result_data_file',
            MagicMock(return_value=None),
        ):
            success = ex._finalize_rounds(
                't1', 'tc1',
                data={'case_algorithm_params': None},
                case_config=_CASE_CONFIG, case_name='c',
                algorithm_type='voice_llm', test_case_id='c1',
                result_ids={1: 11, 2: 22},
                all_round_results=[{'device_id': 1, 'response_time': 100},
                                   {'device_id': 2, 'response_time': 200}],
                execution_success=True,
                case_reference_params=None, last_adjusted_ref_params=None,
                device_info_list=device_info_list,
                tc_rel_ids={1: 101, 2: 102},
            )
        return ex, success

    def test_each_device_updates_own_result(self):
        """每台设备各自更新自己的 TestResult（不共用一条）。"""
        ex, success = self._finalize()
        assert success is True
        updated_ids = [c.kwargs['result_id'] for c in ex._aggregator.update_test_result.call_args_list]
        assert updated_ids == [11, 22]

    def test_event_published_only_on_last_device(self):
        """用例完成事件只在组内最后一台设备回写时发布（其余 publish_event=False）。"""
        ex, _ = self._finalize()
        flags = [c.kwargs['publish_event'] for c in ex._aggregator.process_results.call_args_list]
        row_ids = [c.args[2] for c in ex._aggregator.process_results.call_args_list]
        assert flags == [False, True]
        assert row_ids == [101, 102]


class TestProcessResultsPublishGate:

    def _aggregator(self):
        from e2e_test_service.application.services.e2e_aggregator import E2EAggregator

        executor = MagicMock()
        executor._log = MagicMock()
        agg = E2EAggregator(executor)
        agg._task_data_repo = MagicMock()
        agg._task_data_repo.get_task_case_by_ids.return_value = [MagicMock()]
        return agg

    def test_publish_skipped_when_flag_false(self):
        """publish_event=False（组内非最后一台）：不发布用例事件。"""
        agg = self._aggregator()
        with patch('shared.utils.redis_pubsub.EventBus') as bus:
            agg.process_results(
                't1', 'c', 101, 'c1',
                [{'round_number': 1, 'raw_results': {'success': True}}],
                publish_event=False, precreated_result_id=11,
                precomputed_execution_success=True,
            )
        bus.return_value.publish.assert_not_called()

    def test_publish_once_on_last_device(self):
        """默认 publish_event=True：发布一次用例完成事件。"""
        agg = self._aggregator()
        with patch('shared.utils.redis_pubsub.EventBus') as bus:
            agg.process_results(
                't1', 'c', 102, 'c1',
                [{'round_number': 1, 'raw_results': {'success': True}}],
                precreated_result_id=22,
                precomputed_execution_success=True,
            )
        bus.return_value.publish.assert_called_once()
