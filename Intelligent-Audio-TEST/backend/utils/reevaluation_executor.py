import threading
from backend.models.models import Task, TaskCase, TestResult, TestResultDimension
from backend.models.database import db
from backend.utils.log_handler import log_and_emit
from backend.utils.evaluation_service import evaluation_service, get_app
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

        from backend.utils.execution_engine import execution_engine
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
                    from backend.utils.device_result_reextractor import get_device_result_reextractor
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
                        reference_params = result.result_data.get(
                            'adjusted_reference_params', []
                        ) if result.result_data else []

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
                        reference_params = result.result_data.get(
                            'adjusted_reference_params', []
                        ) if result.result_data else []
                        result_type = result.result_data.get(
                            'result_type', 'unknown'
                        ) if result.result_data else 'unknown'

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

                from backend.algorithm.case_parameter_extractor import CaseParameterExtractor

                for case_info in cases_to_reevaluate:
                    test_case_id = case_info['test_case_id']
                    result_id = case_info['result_id']
                    algorithm_result = case_info['algorithm_result']
                    reference_params = case_info.get('reference_params', [])
                    device_id = case_info['device_id']

                    try:
                        db.session.query(TestResultDimension).filter_by(
                            test_result_id=result_id
                        ).delete()

                        tc_rel = db.session.query(TaskCase).filter_by(
                            task_id=task_id,
                            test_case_id=test_case_id
                        ).first()
                        if tc_rel:
                            tc_rel.evaluation_status = 'queued'

                        task = db.session.query(Task).get(task_id)
                        test_type = task.type if task and task.type else 'api'

                        from backend.models.models import TestCase
                        test_case = db.session.get(TestCase, test_case_id)
                        algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'

                        full_case_params = {
                            'algorithm_type': algorithm_type,
                            'algorithm_params': test_case.algorithm_params if test_case and test_case.algorithm_params else {},
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
