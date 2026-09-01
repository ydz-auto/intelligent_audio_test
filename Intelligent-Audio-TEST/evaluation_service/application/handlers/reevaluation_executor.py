import threading
# P1.4: Task/TaskCase/TestResult/TestCase 改为通过 gRPC 调 task_service
# P1-1 DDD: 通过 Repository 访问自有 PO，不再直接 import orm_models / get_db_session
# P0-2 DDD: 业务规则下沉到 domain/services/reevaluation_service.py
from evaluation_service.infrastructure.acl import task_acl_repository, device_result_acl_repository
from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import evaluation_dimension_repository
from shared.utils.log_handler import log_and_emit
from evaluation_service.infrastructure.evaluation_service_host import evaluation_service
from evaluation_service.domain.services.reevaluation_service import reevaluation_service
from shared.utils.result_data_store import load_full_result_data
from shared.utils.status_constants import TaskStatus, ExecutionStatus, EvaluationStatus, ACTIVE_EVALUATION_STATUSES
from shared.models.common_enums import TestType
from sqlalchemy import and_

# 重新评估类型判别符（非任务/用例状态，与 task_service 下发的 reevaluate_type 参数对应）
REEVALUATE_TYPE_ALL = 'all'
REEVALUATE_TYPE_FAILED = 'failed'


class ReevaluationExecutor:
    """重新评估执行器 - 管理重新评估任务的队列

    P1.4 改造：所有 Task/TaskCase/TestResult/TestCase 的访问改为通过 task_acl_repository (gRPC)。
    仅保留 TestResultDimension 的本地 DB 访问（本服务自有 PO）。
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.reevaluation_queue = []
        self.reevaluation_lock = threading.Lock()
        self.is_reevaluating = False
        self.running_task_id = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def submit(self, task_id, reextract_device_output=True, reevaluate_type='all'):
        """提交重新评估任务

        P1.4: Task 读写通过 gRPC 调 task_service。
        """
        with self.reevaluation_lock:
            if task_id == self.running_task_id:
                return False, "任务正在重新评估中"

            for item in self.reevaluation_queue:
                if item['task_id'] == task_id:
                    return False, "任务已在重新评估队列中"

            self.reevaluation_queue.append({
                'task_id': task_id,
                'reextract_device_output': reextract_device_output,
                'reevaluate_type': reevaluate_type
            })

            # P1.4: 通过 gRPC 更新 Task 状态为 reevaluate_queued
            task_acl_repository.update_task_status(task_id, TaskStatus.REEVALUATE_QUEUED)

        log_and_emit('INFO', 'reevaluator',
                     f"重新评估任务已提交: task_id={task_id}, type={reevaluate_type}",
                     task_id=task_id)

        self._check_queue()

        return True, "重新评估任务已提交"

    def _check_queue(self):
        """检查重新评估队列，启动下一个任务"""
        with self.reevaluation_lock:
            if self.is_reevaluating or not self.reevaluation_queue:
                return

            task_info = self.reevaluation_queue.pop(0)
            self.is_reevaluating = True
            self.running_task_id = task_info['task_id']
            task_id = task_info['task_id']
            reextract_device_output = task_info['reextract_device_output']
            reevaluate_type = task_info['reevaluate_type']

        # P1.4: 通过 gRPC 更新 Task 状态为 reevaluating
        task_acl_repository.update_task_status(task_id, TaskStatus.REEVALUATING)

        log_and_emit('INFO', 'reevaluator',
                     f"开始执行重新评估: task_id={task_id}",
                     task_id=task_id)

        # evaluation_service 本地线程池执行重新评估
        import threading
        thread = threading.Thread(
            target=self._run_reevaluation,
            args=(task_id, reextract_device_output, reevaluate_type),
            daemon=True,
        )
        thread.start()

    def _run_reevaluation(self, task_id, reextract_device_output, reevaluate_type):
        """执行重新评估"""
        success = False

        try:
            # 1. 重新提取设备输出（如果需要）
            if reextract_device_output:
                test_results = self._reextract_device_output(task_id, reevaluate_type)
            else:
                # P1.4: 通过 gRPC 读 TestResult
                test_results = task_acl_repository.get_test_results_by_task_and_case(task_id=task_id)

            # 2. 收集需要重新评估的用例
            if reevaluate_type == REEVALUATE_TYPE_ALL:
                cases_to_reevaluate = self._collect_reevaluation_cases_all(
                    task_id, test_results, reextract_device_output
                )
            elif reevaluate_type == REEVALUATE_TYPE_FAILED:
                cases_to_reevaluate = self._collect_reevaluation_cases_failed(
                    task_id, test_results, reextract_device_output
                )
            else:
                cases_to_reevaluate = []

            if not cases_to_reevaluate:
                log_and_emit('WARNING', 'reevaluator',
                             f"没有需要重新评估的用例: task_id={task_id}, test_results_count={len(test_results)}",
                             task_id=task_id)
                success = True
                return

            # 将不满足重新评估条件的用例的评估状态标记为已完成，避免状态不一致
            reevaluated_case_ids = {c['test_case_id'] for c in cases_to_reevaluate}
            # P1.4: 通过 gRPC 读取所有 TaskCase，过滤需要标记的
            all_tc_rels = task_acl_repository.get_task_case_by_ids(task_id=task_id)
            for tc_rel in all_tc_rels:
                tc_case_id = tc_rel.test_case_id
                if (tc_case_id not in reevaluated_case_ids
                        and tc_rel.execution_status == ExecutionStatus.COMPLETED
                        and tc_rel.evaluation_status in ACTIVE_EVALUATION_STATUSES):
                    task_acl_repository.update_task_case_status(
                        task_id=task_id,
                        case_id=str(tc_case_id),
                        evaluation_status=EvaluationStatus.COMPLETED,
                    )

            # 3. 提交用例进行重新评估
            self._submit_cases_for_reevaluation(task_id, cases_to_reevaluate)

            success = True
            log_and_emit('INFO', 'reevaluator',
                         f"重新评估任务已提交: {len(cases_to_reevaluate)} 个用例",
                         task_id=task_id)

        except Exception as e:
            import traceback
            log_and_emit('ERROR', 'reevaluator',
                         f"重新评估失败: {str(e)}, traceback: {traceback.format_exc()}",
                         task_id=task_id)

        finally:
            self._on_complete(task_id, success)

    def _reextract_device_output(self, task_id, reevaluate_type):
        """通过 ACL 仓储重新提取设备输出"""
        reextract_result = device_result_acl_repository.reextract_result(task_id, reevaluate_type)

        if not reextract_result.get('success'):
            log_and_emit('WARNING', 'reevaluator',
                         f"重新提取设备输出失败: {reextract_result.get('message')}",
                         task_id=task_id)
        else:
            log_and_emit('INFO', 'reevaluator',
                         f"重新提取设备输出完成: {reextract_result.get('message')}",
                         task_id=task_id)

        # P1.4: 通过 gRPC 读 TestResult
        test_results = task_acl_repository.get_test_results_by_task_and_case(task_id=task_id)
        return test_results

    def _collect_reevaluation_cases_all(self, task_id, test_results, reextract_device_output):
        """收集所有需要重新评估的用例（all 类型）— Application 层编排。

        P0-2 DDD: 业务规则下沉到 domain/services/reevaluation_service.py。
        Application 只负责：预加载数据（full_data、TaskCase）+ 调用 Domain Service。
        """
        # 1. 预加载 full_data 和 TaskCase（基础设施访问）
        full_data_map = {}
        task_case_map = {}
        for result in test_results:
            tc_id = str(result.test_case_id)
            full_data = load_full_result_data(result.result_data, result.result_data_path)
            full_data_map[tc_id] = full_data or {}

            # 从文件恢复 raw_results，重新映射字段
            algo_result = reevaluation_service.deserialize_algorithm_result(
                result.algorithm_result or {}
            )
            self._remap_fields_from_raw(algo_result, full_data, result.test_case_id, result.id)
            result.algorithm_result = algo_result

            tc_rels = task_acl_repository.get_task_case_by_ids(task_id=task_id, case_ids=[tc_id])
            task_case_map[tc_id] = tc_rels[0] if tc_rels else None

        # 2. 调用 Domain Service 做业务判断（纯逻辑）
        return reevaluation_service.collect_cases_all(
            test_results, full_data_map, task_case_map, reextract_device_output
        )

    def _collect_reevaluation_cases_failed(self, task_id, test_results, reextract_device_output):
        """收集评估失败的用例（failed 类型）— Application 层编排。

        P0-2 DDD: 业务规则下沉到 domain/services/reevaluation_service.py。
        """
        # 1. 预加载 full_data 和 TaskCase
        full_data_map = {}
        task_case_map = {}
        for result in test_results:
            tc_id = str(result.test_case_id)
            full_data = load_full_result_data(result.result_data, result.result_data_path)
            full_data_map[tc_id] = full_data or {}

            algo_result = reevaluation_service.deserialize_algorithm_result(
                result.algorithm_result or {}
            )
            self._remap_fields_from_raw(algo_result, full_data, result.test_case_id, result.id)
            result.algorithm_result = algo_result

            tc_rels = task_acl_repository.get_task_case_by_ids(task_id=task_id, case_ids=[tc_id])
            task_case_map[tc_id] = tc_rels[0] if tc_rels else None

        # 2. 调用 Domain Service
        return reevaluation_service.collect_cases_failed(
            test_results, full_data_map, task_case_map, reextract_device_output
        )

    def _remap_fields_from_raw(self, algo_result, full_data, test_case_id, result_id=None):
        """从 raw_results 重新映射字段（Infrastructure 编排，涉及 ACL 仓储 + field_mapper）"""
        raw_results_list = full_data.get('raw_results_list') if full_data else None
        if not raw_results_list:
            return
        from evaluation_service.infrastructure.acl import algorithm_acl_repository
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))
        algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'
        remapped_results = device_result_acl_repository.convert_results(
            [dict(r, raw_results=r.get('raw_results', {})) for r in raw_results_list],
            algorithm_type
        )
        rounds_in_algo = algo_result.get('rounds', [])
        for ri, remapped in enumerate(remapped_results):
            if ri < len(rounds_in_algo):
                field_defs = algorithm_acl_repository.get_field_mappings(algorithm_type)
                mapped_fields = field_defs.get_mapped_device_fields_list(algorithm_type)
                round_output = rounds_in_algo[ri].setdefault('output', {})
                if isinstance(mapped_fields, list):
                    for f in mapped_fields:
                        target = f.get('code') or f.get('target_param')
                        dim_id = f.get('dimension_id')
                        if dim_id is not None:
                            dim_key = f'{target}__dim_{dim_id}'
                            dim_val = remapped.get(dim_key)
                            if dim_val is not None:
                                round_output[dim_key] = dim_val
                        # 通用 key：重新评估时无条件用 raw_results_list 的值覆盖
                        val = remapped.get(target)
                        if val is not None:
                            round_output[target] = val

        # 写回数据库：raw_results_list 重新映射后的 algo_result 需要持久化
        # JSON 字段应直接存 dict，避免双重序列化
        if result_id is not None:
            task_acl_repository.update_test_result_algorithm_result(
                result_id=result_id,
                algorithm_result=algo_result if isinstance(algo_result, dict) else {},
            )

    def _submit_cases_for_reevaluation(self, task_id, cases_to_reevaluate):
        """提交用例进行重新评估

        P1.4: Task/TestCase 通过 gRPC 读
        """
        for case_info in cases_to_reevaluate:
            test_case_id = case_info['test_case_id']
            result_id = case_info['result_id']
            algorithm_result = case_info['algorithm_result']
            reference_params = case_info.get('reference_params', [])
            device_id = case_info['device_id']

            try:
                # P1.4: 通过 gRPC 读 Task
                task = task_acl_repository.get_task_by_id(task_id)
                test_type = task.type if task and task.type else TestType.API.value

                # P1.4: 通过 gRPC 读 TestCase
                test_case = task_acl_repository.get_test_case_detail(str(test_case_id))
                algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'
                reference_params_col = test_case.reference_params if test_case else None

                # P0-2: 多轮/单轮分发决策委托 Domain Service
                if reevaluation_service.is_multi_round(algorithm_result):
                    self._reevaluate_multi_round(
                        task_id=task_id,
                        result=result_id,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        test_type=test_type,
                        algorithm_type=algorithm_type,
                        reference_params_col=reference_params_col,
                    )
                else:
                    self._reevaluate_single(
                        task_id=task_id,
                        result_id=result_id,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        reference_params=reference_params,
                        test_type=test_type,
                        algorithm_type=algorithm_type,
                        reference_params_col=reference_params_col,
                    )

                log_and_emit('INFO', 'reevaluator',
                             f"已提交评估: test_case_id={test_case_id}, device_id={device_id}",
                             task_id=task_id, test_case_id=test_case_id)

            except Exception as e:
                import traceback
                log_and_emit('ERROR', 'reevaluator',
                             f"重新评估用例失败: {str(e)}, traceback: {traceback.format_exc()}",
                             task_id=task_id, test_case_id=test_case_id)

    def _reevaluate_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type,
                               reference_params_col=None):
        """重新评估多轮结果 — Application 层编排。

        P0-2 DDD: 反序列化委托 Domain Service。
        """
        algorithm_result = reevaluation_service.deserialize_algorithm_result(algorithm_result)
        rounds = algorithm_result.get('rounds', [])
        is_e2e = test_type == TestType.E2E.value

        # 清理旧的维度评估记录（通过 Repository，不直连 DB）
        evaluation_dimension_repository.delete_scores_by_result_id(result)

        # P1.4: 通过 gRPC 更新 TaskCase 状态
        tc_rels = task_acl_repository.get_task_case_by_ids(
            task_id=task_id, case_ids=[str(test_case_id)]
        )
        tc_rel = tc_rels[0] if tc_rels else None
        if tc_rel:
            # 重新评估只更新 evaluation_status，不修改 status（执行结果）
            task_acl_repository.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                evaluation_status=EvaluationStatus.QUEUED,
            )

        # P1.4: 通过 gRPC 读 TestCase
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))

        # 分派到具体的多轮评估实现
        if is_e2e:
            self._reevaluate_e2e_multi_round(
                task_id, result, test_case_id, algorithm_result,
                test_type, algorithm_type, reference_params_col, rounds, test_case
            )
        else:
            self._reevaluate_api_multi_round(
                task_id, result, test_case_id, algorithm_result,
                test_type, algorithm_type, reference_params_col, rounds, test_case
            )

    def _reevaluate_e2e_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type,
                                     reference_params_col, rounds, test_case):
        """E2E多轮评估

        P1.4: test_case 为 TestCaseDetailDTO（来自 gRPC）
        """
        from evaluation_service.infrastructure.acl import algorithm_acl_repository

        # E2E: 一次性评估所有轮（不传 round_number，evaluate_case 构建完整 rounds_list）
        algo_params = {}
        algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
        if algorithm_params_col:
            from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
            algo_params = ParamNormalizerService.normalize_algorithm_params(
                ParamNormalizerService.get_round_algo_params(algorithm_params_col, 1))
        elif test_case and test_case.config:
            config = test_case.config
            config_rounds = config.get('rounds', [])
            if config_rounds and isinstance(config_rounds[0], dict):
                algo_params = config_rounds[0].get('algorithm_params', {})

        full_case_params = {
            'algorithm_type': algorithm_type,
            'algorithm_params': algo_params,
            'reference_params': rounds[0].get('reference_params', []) if rounds else [],
            'reference_params_col': reference_params_col,
        }

        try:
            all_params = algorithm_acl_repository.extract_case_all_params(full_case_params)
            eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
            eval_params['algorithm_type'] = algorithm_type
            eval_params['test_type'] = test_type
            if reference_params_col is not None:
                eval_params['reference_params_col'] = reference_params_col
            if algorithm_params_col is not None:
                eval_params['algorithm_params_col'] = algorithm_params_col

            evaluation_service.evaluate_case(
                task_id=task_id,
                result_id=result,
                test_case_id=test_case_id,
                algorithm_result=algorithm_result,
                **eval_params,
            )

            log_and_emit('INFO', 'reevaluator',
                        f"已提交 E2E 多轮评估: test_case_id={test_case_id}, rounds={len(rounds)}",
                        task_id=task_id, test_case_id=test_case_id)
        except Exception as e:
            import traceback
            log_and_emit('ERROR', 'reevaluator',
                        f"E2E 多轮重新评估失败: error={str(e)}, traceback={traceback.format_exc()}",
                        task_id=task_id, test_case_id=test_case_id)

    def _reevaluate_api_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type,
                                     reference_params_col, rounds, test_case):
        """API多轮逐轮评估

        P1.4: test_case 为 TestCaseDetailDTO（来自 gRPC）
        """
        from evaluation_service.infrastructure.acl import algorithm_acl_repository

        # API: 逐轮评估
        for round_idx, round_data in enumerate(rounds):
            evaluation = round_data.get('round_evaluation', {})
            round_number = round_data.get('round_number', round_idx + 1) - 1

            if not evaluation:
                continue

            algo_params = {}
            algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
            if algorithm_params_col:
                from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
                algo_params = ParamNormalizerService.normalize_algorithm_params(
                    ParamNormalizerService.get_round_algo_params(algorithm_params_col, round_idx + 1))
            elif test_case and test_case.config:
                config = test_case.config
                config_rounds = config.get('rounds', [])
                if round_idx < len(config_rounds) and isinstance(config_rounds[round_idx], dict):
                    algo_params = config_rounds[round_idx].get('algorithm_params', {})

            full_case_params = {
                'algorithm_type': algorithm_type,
                'algorithm_params': algo_params,
                'reference_params': round_data.get('reference_params', []),
                'reference_params_col': reference_params_col,
            }

            try:
                all_params = algorithm_acl_repository.extract_case_all_params(full_case_params)
                eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
                eval_params['algorithm_type'] = algorithm_type
                eval_params['test_type'] = test_type
                if reference_params_col is not None:
                    eval_params['reference_params_col'] = reference_params_col
                if algorithm_params_col is not None:
                    eval_params['algorithm_params_col'] = algorithm_params_col

                evaluation_service.evaluate_case(
                    task_id=task_id,
                    result_id=result,
                    test_case_id=test_case_id,
                    algorithm_result=algorithm_result,
                    round_number=round_number,
                    **eval_params,
                )

                log_and_emit('INFO', 'reevaluator',
                            f"已提交轮次评估: test_case_id={test_case_id}, round={round_number}",
                            task_id=task_id, test_case_id=test_case_id)
            except Exception as e:
                import traceback
                log_and_emit('ERROR', 'reevaluator',
                            f"轮次重新评估失败: round={round_number}, error={str(e)}, traceback={traceback.format_exc()}",
                            task_id=task_id, test_case_id=test_case_id)

        # API 结果没有顶层 aggregated，需从 rounds 中计算
        if not algorithm_result.get('aggregated'):
            self._compute_and_store_api_aggregated(result, algorithm_result)

    def _reevaluate_single(self, task_id, result_id, test_case_id, algorithm_result, reference_params, test_type, algorithm_type,
                           reference_params_col=None):
        """重新评估单轮结果 — Application 层编排。

        P0-2 DDD: 反序列化委托 Domain Service。
        """
        algorithm_result = reevaluation_service.deserialize_algorithm_result(algorithm_result)

        # 清理旧的维度评估记录（通过 Repository，不直连 DB）
        evaluation_dimension_repository.delete_scores_by_result_id(result_id)

        # P1.4: 通过 gRPC 更新 TaskCase 状态
        tc_rels = task_acl_repository.get_task_case_by_ids(
            task_id=task_id, case_ids=[str(test_case_id)]
        )
        tc_rel = tc_rels[0] if tc_rels else None
        if tc_rel:
            # 重新评估只更新 evaluation_status，不修改 status（执行结果）
            task_acl_repository.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                evaluation_status=EvaluationStatus.QUEUED,
            )

        # P1.4: 通过 gRPC 读 TestCase
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))

        # 优先从独立列读取 algorithm_params（按轮分组），兼容旧数据从 config.rounds 读取
        algo_params = {}
        algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
        if algorithm_params_col:
            from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
            algo_params = ParamNormalizerService.normalize_algorithm_params(
                ParamNormalizerService.get_round_algo_params(algorithm_params_col, 1))
        elif test_case and test_case.config:
            config = test_case.config
            rounds = config.get('rounds', [])
            if rounds and isinstance(rounds[0], dict):
                algo_params = rounds[0].get('algorithm_params', {})

        full_case_params = {
            'algorithm_type': algorithm_type,
            'algorithm_params': algo_params,
            'reference_params': reference_params,
            'reference_params_col': reference_params_col,
        }

        from evaluation_service.infrastructure.acl import algorithm_acl_repository
        all_params = algorithm_acl_repository.extract_case_all_params(full_case_params)
        eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = test_type
        if reference_params_col is not None:
            eval_params['reference_params_col'] = reference_params_col
        if algorithm_params_col is not None:
            eval_params['algorithm_params_col'] = algorithm_params_col

        evaluation_service.evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algorithm_result,
            **eval_params
        )

    def _compute_and_store_api_aggregated(self, result_id, algorithm_result):
        """API 结果没有顶层 aggregated，从 rounds 计算 — Application 层编排。

        P0-2 DDD: 聚合计算委托 Domain Service，gRPC 写回留在 Application。
        """
        algo = reevaluation_service.deserialize_algorithm_result(algorithm_result)
        rounds = algo.get('rounds', [])
        if not rounds:
            return

        aggregated = reevaluation_service.compute_api_aggregated(rounds)
        if aggregated:
            algo['aggregated'] = aggregated
            task_acl_repository.update_test_result_algorithm_result(
                result_id=result_id,
                algorithm_result=algo,
            )

    def _on_complete(self, task_id, success):
        """重新评估完成回调

        P1.4: 通过 gRPC 更新 Task 状态
        """
        with self.reevaluation_lock:
            self.is_reevaluating = False
            self.running_task_id = None

        # P1.4: 通过 gRPC 更新 Task 状态
        new_status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        task_acl_repository.update_task_status(task_id, new_status)

        log_and_emit('INFO', 'reevaluator',
                     f"重新评估完成: task_id={task_id}, success={success}",
                     task_id=task_id)

        self._check_queue()
