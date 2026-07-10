import json
import threading
from backend.models.models import Task, TaskCase, TestResult, TestResultDimension
from backend.models.database import db
from backend.utils.web.log_handler import log_and_emit
from backend.services.evaluation.evaluation_service import evaluation_service, get_app
from backend.utils.common.result_data_store import load_full_result_data
from sqlalchemy import and_


class ReevaluationExecutor:
    """重新评估执行器 - 管理重新评估任务的队列"""

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

        Args:
            task_id: 任务ID
            reextract_device_output: 是否重新提取设备输出
            reevaluate_type: 重新评估类型 ('all' 或 'failed')

        Returns:
            (success, message)
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

            task = db.session.query(Task).get(task_id)
            if task:
                task.status = 'reevaluate_queued'
                db.session.commit()

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

        current_app = get_app()
        with current_app.app_context():
            task = db.session.query(Task).get(task_id)
            if task:
                task.status = 'reevaluating'
                db.session.commit()

        log_and_emit('INFO', 'reevaluator',
                     f"开始执行重新评估: task_id={task_id}",
                     task_id=task_id)

        from backend.services.execution.execution_engine import execution_engine
        execution_engine.api_task_pool.submit(
            self._run_reevaluation,
            task_id, reextract_device_output, reevaluate_type
        )

    def _run_reevaluation(self, task_id, reextract_device_output, reevaluate_type):
        """执行重新评估"""
        success = False
        current_app = get_app()

        try:
            with current_app.app_context():
                cases_to_reevaluate = []
                test_results = []

                if reextract_device_output:
                    from backend.services.device.device_result_reextractor import get_device_result_reextractor
                    reextractor = get_device_result_reextractor()

                    if reevaluate_type == 'all':
                        reextract_result = reextractor.reextract_for_task(task_id, evaluation_status=None)
                    else:
                        reextract_result = reextractor.reextract_for_task(task_id, evaluation_status='failed')

                    if not reextract_result.get('success'):
                        log_and_emit('WARNING', 'reevaluator',
                                     f"重新提取设备输出失败: {reextract_result.get('message')}",
                                     task_id=task_id)
                    else:
                        log_and_emit('INFO', 'reevaluator',
                                     f"重新提取设备输出完成: {reextract_result.get('message')}",
                                     task_id=task_id)

                    test_results = db.session.query(TestResult).filter_by(task_id=task_id).all()
                else:
                    test_results = db.session.query(TestResult).filter_by(task_id=task_id).all()

                if reevaluate_type == 'all':
                    for result in test_results:
                        if result.execution_status != 'completed':
                            continue

                        if not result.algorithm_result:
                            continue

                        algo_result = result.algorithm_result or {}
                        # 循环反序列化，处理可能的双重序列化旧数据
                        while isinstance(algo_result, str):
                            try:
                                algo_result = json.loads(algo_result)
                            except (json.JSONDecodeError, ValueError):
                                algo_result = {}
                        if not isinstance(algo_result, dict):
                            algo_result = {}
                        full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                        reference_params = full_data.get(
                            'adjusted_reference_params', []
                        ) if full_data else []

                        tc_rel = db.session.query(TaskCase).filter_by(
                            task_id=task_id,
                            test_case_id=result.test_case_id
                        ).first()

                        if tc_rel:
                            case_info = {
                                'test_case_id': result.test_case_id,
                                'result_id': result.id,
                                'algorithm_result': algo_result,
                                'reference_params': reference_params,
                                'device_id': result.device_id,
                                'task_id': task_id,
                                'reextracted': reextract_device_output
                            }
                            cases_to_reevaluate.append(case_info)

                elif reevaluate_type == 'failed':
                    for result in test_results:
                        if result.execution_status != 'completed':
                            continue

                        tc_rel = db.session.query(TaskCase).filter_by(
                            task_id=task_id,
                            test_case_id=result.test_case_id
                        ).first()

                        if not tc_rel or tc_rel.evaluation_status != 'failed':
                            continue

                        if not result.algorithm_result:
                            continue

                        algo_result = result.algorithm_result or {}
                        # 循环反序列化，处理可能的双重序列化旧数据
                        while isinstance(algo_result, str):
                            try:
                                algo_result = json.loads(algo_result)
                            except (json.JSONDecodeError, ValueError):
                                algo_result = {}
                        if not isinstance(algo_result, dict):
                            algo_result = {}
                        full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                        reference_params = full_data.get(
                            'adjusted_reference_params', []
                        ) if full_data else []
                        result_type = full_data.get(
                            'result_type', 'unknown'
                        ) if full_data else 'unknown'

                        case_info = {
                            'test_case_id': result.test_case_id,
                            'result_id': result.id,
                            'algorithm_result': algo_result,
                            'reference_params': reference_params,
                            'device_id': result.device_id,
                            'task_id': task_id,
                            'reextracted': reextract_device_output,
                            'result_type': result_type
                        }
                        cases_to_reevaluate.append(case_info)

                if not cases_to_reevaluate:
                    log_and_emit('WARNING', 'reevaluator',
                                 f"没有需要重新评估的用例: task_id={task_id}, test_results_count={len(test_results)}",
                                 task_id=task_id)
                    success = True
                    return

                # 将不满足重新评估条件的用例的评估状态标记为已完成，避免状态不一致
                reevaluated_case_ids = {c['test_case_id'] for c in cases_to_reevaluate}
                skipped_tc_rels = db.session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    ~TaskCase.test_case_id.in_(reevaluated_case_ids),
                    TaskCase.execution_status == 'completed',
                    TaskCase.evaluation_status.in_(['pending', 'queued', 'running', 'calculating'])
                ).all()
                for tc_rel in skipped_tc_rels:
                    tc_rel.evaluation_status = 'completed'
                if skipped_tc_rels:
                    db.session.commit()

                from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor

                for case_info in cases_to_reevaluate:
                    test_case_id = case_info['test_case_id']
                    result_id = case_info['result_id']
                    algorithm_result = case_info['algorithm_result']
                    reference_params = case_info.get('reference_params', [])
                    device_id = case_info['device_id']

                    try:
                        task = db.session.query(Task).get(task_id)
                        test_type = task.type if task and task.type else 'api'

                        from backend.models.models import TestCase
                        test_case = db.session.get(TestCase, test_case_id)
                        algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'

                        # 检查是否为多轮结果
                        if algorithm_result and 'rounds' in algorithm_result:
                            self._reevaluate_multi_round(
                                task_id=task_id,
                                result=result_id,
                                test_case_id=test_case_id,
                                algorithm_result=algorithm_result,
                                test_type=test_type,
                                algorithm_type=algorithm_type,
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
                            )

                        log_and_emit('INFO', 'reevaluator',
                                     f"已提交评估: test_case_id={test_case_id}, device_id={device_id}",
                                     task_id=task_id, test_case_id=test_case_id)

                    except Exception as e:
                        import traceback
                        log_and_emit('ERROR', 'reevaluator',
                                     f"重新评估用例失败: {str(e)}, traceback: {traceback.format_exc()}",
                                     task_id=task_id, test_case_id=test_case_id)

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

    def _reevaluate_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type):
        """重新评估多轮结果 — 区分 API 和 E2E

        API 多轮结构: rounds[].round_evaluation, roundNumber (1-indexed)
        E2E 多轮结构: rounds[].evaluation, round (0-indexed)
        """
        # 循环反序列化，处理可能的双重序列化旧数据
        while isinstance(algorithm_result, str):
            try:
                algorithm_result = json.loads(algorithm_result)
            except (json.JSONDecodeError, ValueError):
                algorithm_result = {}
        if not isinstance(algorithm_result, dict):
            algorithm_result = {}
        rounds = algorithm_result.get('rounds', [])
        is_e2e = test_type == 'e2e'

        # 清理旧的维度评估记录
        db.session.query(TestResultDimension).filter_by(
            test_result_id=result
        ).delete()

        tc_rel = db.session.query(TaskCase).filter_by(
            task_id=task_id,
            test_case_id=test_case_id
        ).first()
        if tc_rel:
            tc_rel.evaluation_status = 'queued'
            # 重置 status 为 pending，评估完成后由 update_task_case_status 统一设置最终状态
            if tc_rel.status not in ['stopped', 'skipped']:
                tc_rel.status = 'pending'
        db.session.commit()

        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        from backend.models.models import TestCase

        # 逐轮重新评估
        for round_idx, round_data in enumerate(rounds):
            # 提取评估数据：API 用 round_evaluation，E2E 用 evaluation
            if is_e2e:
                evaluation = round_data.get('evaluation', {})
                round_number = round_data.get('round', round_idx)  # 0-indexed
            else:
                evaluation = round_data.get('round_evaluation', {})
                # API 的 roundNumber 是 1-indexed，转为 0-indexed
                round_number = round_data.get('roundNumber', round_idx + 1) - 1

            if not evaluation:
                continue

            test_case = db.session.get(TestCase, test_case_id)

            # 从本轮的 algorithmParams 读取
            algo_params = {}
            if test_case and test_case.config:
                config = test_case.config
                config_rounds = config.get('rounds', [])
                if round_idx < len(config_rounds) and isinstance(config_rounds[round_idx], dict):
                    algo_params = config_rounds[round_idx].get('algorithmParams', {})

            full_case_params = {
                'algorithm_type': algorithm_type,
                'algorithm_params': algo_params,
                'reference_params': round_data.get('reference_params', []),
            }

            try:
                eval_params = CaseParameterExtractor.get_evaluation_params(
                    case_config=full_case_params,
                    algorithm_result=algorithm_result,
                    test_type=test_type,
                )
                eval_params['algorithm_type'] = algorithm_type
                eval_params['test_type'] = test_type

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
        if not is_e2e and not algorithm_result.get('aggregated'):
            self._compute_and_store_api_aggregated(result, algorithm_result)

    def _reevaluate_single(self, task_id, result_id, test_case_id, algorithm_result, reference_params, test_type, algorithm_type):
        """重新评估单轮结果（现有逻辑）"""
        # 循环反序列化，处理可能的双重序列化旧数据
        while isinstance(algorithm_result, str):
            try:
                algorithm_result = json.loads(algorithm_result)
            except (json.JSONDecodeError, ValueError):
                algorithm_result = {}
        if not isinstance(algorithm_result, dict):
            algorithm_result = {}
        db.session.query(TestResultDimension).filter_by(
            test_result_id=result_id
        ).delete()

        tc_rel = db.session.query(TaskCase).filter_by(
            task_id=task_id,
            test_case_id=test_case_id
        ).first()
        if tc_rel:
            tc_rel.evaluation_status = 'queued'
            # 重置 status 为 pending，评估完成后由 update_task_case_status 统一设置最终状态
            if tc_rel.status not in ['stopped', 'skipped']:
                tc_rel.status = 'pending'

        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        from backend.models.models import TestCase

        test_case = db.session.get(TestCase, test_case_id)

        # 从 rounds[0].algorithmParams 读取
        algo_params = {}
        if test_case and test_case.config:
            config = test_case.config
            rounds = config.get('rounds', [])
            if rounds and isinstance(rounds[0], dict):
                algo_params = rounds[0].get('algorithmParams', {})

        full_case_params = {
            'algorithm_type': algorithm_type,
            'algorithm_params': algo_params,
            'reference_params': reference_params
        }

        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=algorithm_result,
            test_type=test_type
        )
        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = test_type

        db.session.commit()

        evaluation_service.evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algorithm_result,
            **eval_params
        )

    def _compute_and_store_api_aggregated(self, result_id, algorithm_result):
        """API 结果没有顶层 aggregated，从 rounds 的 round_evaluation 中计算"""
        # 循环反序列化，处理可能的双重序列化旧数据
        while isinstance(algorithm_result, str):
            try:
                algorithm_result = json.loads(algorithm_result)
            except (json.JSONDecodeError, ValueError):
                algorithm_result = {}
        if not isinstance(algorithm_result, dict):
            algorithm_result = {}
        rounds = algorithm_result.get('rounds', [])
        if not rounds:
            return

        evals = [r.get('round_evaluation', {}) for r in rounds if r.get('round_evaluation')]

        if evals:
            aggregated = {
                'avg_wer': sum(e.get('wer', 0) for e in evals) / len(evals),
                'avg_llm_judge': sum(e.get('llm_judge', 0) for e in evals) / len(evals) if any('llm_judge' in e for e in evals) else None,
                'avg_latency': sum(r.get('latency', 0) for r in rounds) / len(rounds),
                'round_count': len(rounds),
            }
            algorithm_result['aggregated'] = aggregated

            test_result = db.session.query(TestResult).filter_by(id=result_id).first()
            if test_result:
                test_result.algorithm_result = algorithm_result
                db.session.commit()

    def _on_complete(self, task_id, success):
        """重新评估完成回调"""
        with self.reevaluation_lock:
            self.is_reevaluating = False
            self.running_task_id = None

        current_app = get_app()
        with current_app.app_context():
            task = db.session.query(Task).get(task_id)
            if task:
                task.status = 'completed' if success else 'failed'
                db.session.commit()

        log_and_emit('INFO', 'reevaluator',
                     f"重新评估完成: task_id={task_id}, success={success}",
                     task_id=task_id)

        self._check_queue()
