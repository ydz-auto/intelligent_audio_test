"""用例评估编排混入：evaluate_case 入口及准备/分发编排"""
import json

from shared.algorithm.field_mapper import get_field_mapper


class CaseEvaluationMixin:
    """用例评估的顶层编排：准备数据 → 分发到 worker"""

    def evaluate_case(self, task_id, result_id, test_case_id, algorithm_result, **kwargs):
        field_mapper = get_field_mapper()
        test_type = kwargs.get('test_type', 'api')
        round_number = kwargs.get('round_number')  # 多轮评估: 轮次编号 (None=整体评估, 0-indexed)
        reference_params_col = kwargs.pop('reference_params_col', None)

        # 多轮场景：统一构建 rounds 列表（单轮也走此路径，列表只有一个元素）
        if isinstance(algorithm_result, dict) and algorithm_result.get('rounds'):
            rounds_list = self._build_rounds_list(
                algorithm_result, reference_params_col,
                field_mapper, kwargs.get('algorithm_type', 'translation'),
                test_type, task_id, test_case_id
            )
            if round_number is not None:
                # 指定轮次：只取对应轮
                rounds_list = [rounds_list[round_number]] if round_number < len(rounds_list) else []
            if rounds_list:
                kwargs['rounds'] = rounds_list

        self._log(
            level='DEBUG',
            content=f"[DEBUG evaluate_case] 传入参数: task_id={task_id}, result_id={result_id}, result_id_type={type(result_id)}, test_case_id={test_case_id}, test_type={test_type}, round_number={round_number}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='INFO',
            content=f"用例评估请求: TaskID={task_id}, TestCaseID={test_case_id}, ResultID={result_id}, TestType={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 准备评估数据(加载用例/参考文本/维度配置/维度数据)
        prepared = self._prepare_evaluation_data(
            task_id, result_id, test_case_id, algorithm_result,
            field_mapper, kwargs, test_type
        )
        if prepared is None or prepared is False:
            return prepared if prepared is False else False

        return self._dispatch_to_workers(
            task_id, result_id, test_case_id, algorithm_result,
            prepared, field_mapper, test_type, round_number, kwargs
        )

    def _prepare_evaluation_data(self, task_id, result_id, test_case_id, algorithm_result,
                                  field_mapper, kwargs, test_type):
        """准备评估数据：加载测试用例、参考文本、维度配置、维度数据

        Returns:
            dict: 评估所需数据 (test_case, algorithm_type, ref_texts, dimension_data_list)
            False: 无维度或加载失败，调用方应直接 return False
        """
        # 加载测试用例和参考文本
        case_data = self._load_test_case_and_refs(
            test_case_id, field_mapper, kwargs, task_id
        )
        if case_data is None:
            return False

        test_case = case_data['test_case']
        algorithm_type = case_data['algorithm_type']
        ref_texts = case_data['ref_texts']
        dimensions_config = case_data['dimensions_config']

        # 提取维度ID
        dimension_ids = self._extract_dimension_ids(dimensions_config)

        unique_dimension_ids = list(set(dimension_ids))

        self._log(
            level='DEBUG',
            content=f"用例 {test_case.name} 的维度配置: {json.dumps(dimensions_config, ensure_ascii=False)}, 提取的维度IDs: {dimension_ids}, 去重后: {unique_dimension_ids}",
            task_id=task_id
        )

        if not unique_dimension_ids:
            self._log(level='WARNING', content=f"用例 {test_case.name} 没有配置任何维度，跳过评估", task_id=task_id, test_case_id=test_case_id)
            self.result_processor.mark_test_result_completed(result_id)
            self._post_evaluate_updates(task_id, test_case_id)
            return False

        # 加载维度数据
        dimension_data_list = self._load_dimension_data(
            unique_dimension_ids, task_id, test_case_id, test_case
        )
        if not dimension_data_list:
            self.result_processor.mark_test_result_completed(result_id)
            self._post_evaluate_updates(task_id, test_case_id)
            return False

        self._log(level='INFO', content=f"开始评估 {len(dimension_data_list)} 个维度，分发到端点队列", task_id=task_id, test_case_id=test_case_id)

        # 标记评估状态为 queued
        self._mark_evaluation_queued(task_id, test_case_id)

        return {
            'test_case': test_case,
            'algorithm_type': algorithm_type,
            'ref_texts': ref_texts,
            'dimension_data_list': dimension_data_list,
        }

    def _dispatch_to_workers(self, task_id, result_id, test_case_id, algorithm_result,
                              prepared, field_mapper, test_type, round_number, kwargs):
        """创建维度结果记录并分发评估任务到端点 worker"""
        test_case = prepared['test_case']
        algorithm_type = prepared['algorithm_type']
        ref_texts = prepared['ref_texts']
        dimension_data_list = prepared['dimension_data_list']

        # 创建维度结果记录
        dimension_result_map = self._create_dimension_results(
            dimension_data_list, result_id, task_id, test_case_id, algorithm_type, kwargs
        )

        # 分发评估任务
        rounds_list = kwargs.get('rounds')
        # 提取单轮兼容的扁平字段（answer, correct_answer 等），传给 task_data
        flat_eval_fields = {}
        if isinstance(algorithm_result, dict) and algorithm_result.get('rounds'):
            for k, v in kwargs.items():
                if k not in ('test_type', 'round_number', 'algorithm_type',
                             'reference_params_col', 'rounds'):
                    flat_eval_fields[k] = v
        self._dispatch_evaluation_tasks(
            dimension_data_list, dimension_result_map, result_id, task_id, test_case_id,
            algorithm_result, algorithm_type, test_type, round_number, field_mapper, ref_texts,
            rounds_list, flat_eval_fields
        )

        self._log(
            level='INFO',
            content=f"评估任务已异步提交，开始执行下一个测试用例",
            task_id=task_id,
            test_case_id=test_case_id
        )

        return True
