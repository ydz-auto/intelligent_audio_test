"""用例评估编排混入：evaluate_case 入口及准备/分发编排"""
import json

from shared.utils.status_constants import EvaluationStatus, TaskCaseStatus

# domain 层通过 ACL 仓储获取字段映射数据（延迟 import 避免循环依赖）


class CaseEvaluationMixin:
    """用例评估的顶层编排：准备数据 → 分发到 worker"""

    def evaluate_case(self, task_id, result_id, test_case_id, algorithm_result, **kwargs):
        from evaluation_service.infrastructure.acl import algorithm_acl_repository
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        field_mapper = algorithm_acl_repository.get_field_mappings(algorithm_type)
        test_type = kwargs.get('test_type', 'api')
        round_number = kwargs.get('round_number')  # 多轮评估: 轮次编号 (None=整体评估, 0-indexed)
        reference_params_col = kwargs.pop('reference_params_col', None)
        algorithm_params_col = kwargs.pop('algorithm_params_col', None)

        # 多轮场景：统一构建 rounds 列表（单轮也走此路径，列表只有一个元素）
        if isinstance(algorithm_result, dict) and algorithm_result.get('rounds'):
            rounds_list = self._build_rounds_list(
                algorithm_result, reference_params_col,
                field_mapper, kwargs.get('algorithm_type', 'translation'),
                test_type, task_id, test_case_id,
                algorithm_params_col=algorithm_params_col
            )
            if round_number is not None:
                # 指定轮次：只取对应轮
                rounds_list = [rounds_list[round_number]] if round_number < len(rounds_list) else []
            if not rounds_list:
                # INT-118 评估侧尾巴：多轮结果无法构建任何评估轮次数据
                #（如算法类型缺 evaluation param mappings / 指定轮次不存在），
                # 明确 skipped 终态，不再静默进入维度分发
                self._mark_rounds_evaluation_skipped(
                    task_id, result_id, test_case_id,
                    kwargs.get('algorithm_type', 'translation')
                )
                return False
            kwargs['rounds'] = rounds_list

            # INT-126：多轮整体评估入口（round_number=None）补提交逐轮维度。
            # 上传口径把评估维度逐轮注入 rounds[].evaluation.dimensions（case 级
            # config.dimensions 为空，带音频参数的维度配 case 级会被校验拒绝），
            # 而 API 多轮链只提交一次整体评估——旧逻辑整体只取顶层维度，0 维度
            # 空转完成。此处按 round_scope 分流：逐轮维度按轮出分（复用外层已
            # 构建的轮次数据，走既有单轮评估路径），multi 维度归整体评估出分。
            # 已有逐轮 TRD 记录的轮次幂等跳过（E2E 轮次循环/重评链已逐轮提交）。
            if round_number is None:
                fanout_submitted, has_overall_dims = self._fan_out_per_round_evaluations(
                    task_id=task_id, result_id=result_id, test_case_id=test_case_id,
                    algorithm_result=algorithm_result, field_mapper=field_mapper,
                    test_type=test_type, rounds_list=rounds_list, kwargs=kwargs,
                )
                if fanout_submitted and not has_overall_dims:
                    # 无整体口径维度：逐轮链负责 TRD 落库与用例收尾，整体部分无事可做
                    return True

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
            field_mapper, kwargs, test_type, round_number
        )
        if prepared is None or prepared is False:
            return prepared if prepared is False else False

        return self._dispatch_to_workers(
            task_id, result_id, test_case_id, algorithm_result,
            prepared, field_mapper, test_type, round_number, kwargs
        )

    def _mark_rounds_evaluation_skipped(self, task_id, result_id, test_case_id, algorithm_type):
        """多轮结果无法构建评估数据时的显式跳过收尾。

        TestResult 照常收口 completed（执行已发生），TaskCase 终态标 skipped
        并留痕原因，评估流程状态推进到 completed 避免悬挂在 queued。
        """
        reason = f"算法类型 {algorithm_type} 无 evaluation param mappings 或评估轮次数据为空，评估跳过(skipped)"
        self._log(
            level='WARNING',
            content=f"用例评估跳过(skipped): test_case_id={test_case_id}, {reason}",
            task_id=task_id, test_case_id=test_case_id
        )
        try:
            self.result_processor.mark_test_result_completed(result_id)
            self._task_acl_repo.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                status=TaskCaseStatus.SKIPPED,
                evaluation_status=EvaluationStatus.COMPLETED,
                error_message=reason,
            )
            self._post_evaluate_updates(task_id, test_case_id)
        except Exception as e:
            self._log(
                level='ERROR',
                content=f"用例评估跳过(skipped)收尾失败: test_case_id={test_case_id}, error={e}",
                task_id=task_id, test_case_id=test_case_id
            )

    def _fan_out_per_round_evaluations(self, task_id, result_id, test_case_id,
                                        algorithm_result, field_mapper, test_type,
                                        rounds_list, kwargs):
        """多轮整体评估入口的逐轮维度补提交（INT-126）。

        上传口径把评估维度逐轮注入 rounds[].evaluation.dimensions，整体评估入口
        （round_number=None）按 round_scope 分流补提交：

        - 轮次注入的非 multi 维度（per_round）→ 按轮提交评估（round_number=N，
          复用外层已构建的轮次数据，走既有单轮评估路径），逐轮出分；
        - round_scope=multi 维度 → 归整体评估出分（_merge_dimensions_config
          整体路径合并轮次注入的整体维度，由调用方继续走整体分发）。

        幂等：已存在逐轮 TRD 记录的轮次跳过——E2E 链在轮次循环已逐轮提交、
        重评链先逐轮后整体，整体入口不重复评估。

        Returns:
            tuple: (fanout_submitted, has_overall_dims)
                fanout_submitted: 是否补提交了至少一轮逐轮评估
                has_overall_dims: 是否存在整体口径维度（顶层或轮次注入的 multi）
        """
        test_case = self._task_acl_repo.get_test_case_detail(str(test_case_id))
        config = getattr(test_case, 'config', None) or {}
        if not isinstance(config, dict):
            return False, True
        config_rounds = config.get('rounds')
        if not isinstance(config_rounds, list) or not config_rounds:
            return False, True

        already_submitted_rounds = set()
        if result_id:
            try:
                for score in self._evaluation_dimension_repo.list_scores_by_result_id(result_id):
                    round_no = getattr(score, 'round_number', None)
                    if round_no is not None:
                        already_submitted_rounds.add(round_no)
            except Exception as e:
                self._log(
                    level='WARNING',
                    content=f"整体评估入口读取已有逐轮维度记录失败，跳过幂等检查: {e}",
                    task_id=task_id, test_case_id=test_case_id
                )

        fanout_submitted = False
        for round_idx in range(min(len(config_rounds), len(rounds_list))):
            round_item = config_rounds[round_idx]
            if not isinstance(round_item, dict):
                continue
            evaluation = round_item.get('evaluation')
            if isinstance(evaluation, dict) and evaluation.get('enabled', True) is False:
                continue
            round_dims = self._merge_dimensions_config(config, round_number=round_idx)
            if not round_dims:
                continue
            if round_idx in already_submitted_rounds:
                continue

            round_kwargs = dict(kwargs)
            round_kwargs['round_number'] = round_idx
            round_kwargs['rounds'] = [rounds_list[round_idx]]
            try:
                prepared = self._prepare_evaluation_data(
                    task_id, result_id, test_case_id, algorithm_result,
                    field_mapper, round_kwargs, test_type, round_idx
                )
                if prepared is None or prepared is False:
                    continue
                self._dispatch_to_workers(
                    task_id, result_id, test_case_id, algorithm_result,
                    prepared, field_mapper, test_type, round_idx, round_kwargs
                )
                fanout_submitted = True
                self._log(
                    level='INFO',
                    content=f"整体评估入口补提交逐轮评估: round={round_idx}, dimensions={self._extract_dimension_ids(round_dims)}",
                    task_id=task_id, test_case_id=test_case_id
                )
            except Exception as e:
                self._log(
                    level='ERROR',
                    content=f"整体评估入口逐轮评估补提交失败: round={round_idx}, error={e}",
                    task_id=task_id, test_case_id=test_case_id
                )

        has_overall_dims = bool(self._merge_dimensions_config(config, round_number=None))
        return fanout_submitted, has_overall_dims

    def _prepare_evaluation_data(self, task_id, result_id, test_case_id, algorithm_result,
                                  field_mapper, kwargs, test_type, round_number=None):
        """准备评估数据：加载测试用例、参考文本、维度配置、维度数据

        round_number 传导到维度配置加载：单轮评估只取该轮维度，整体评估只取顶层维度。

        Returns:
            dict: 评估所需数据 (test_case, algorithm_type, ref_texts, dimension_data_list)
            False: 无维度或加载失败，调用方应直接 return False
        """
        # 加载测试用例和参考文本
        case_data = self._load_test_case_and_refs(
            test_case_id, field_mapper, kwargs, task_id, round_number
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

        # P1.4: test_case 为 TestCaseDetailDTO（来自 gRPC）
        case_name = getattr(test_case, 'name', None) or str(test_case_id)

        self._log(
            level='DEBUG',
            content=f"用例 {case_name} 的维度配置: {json.dumps(dimensions_config, ensure_ascii=False)}, 提取的维度IDs: {dimension_ids}, 去重后: {unique_dimension_ids}",
            task_id=task_id
        )

        if not unique_dimension_ids:
            self._log(level='WARNING', content=f"用例 {case_name} 没有配置任何维度，跳过评估", task_id=task_id, test_case_id=test_case_id)
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
