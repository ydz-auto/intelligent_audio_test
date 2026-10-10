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

        # 重新评估前清理旧评估任务（方案A+B）：
        # A. 从回调注册表移除同 task_id 的旧 ctx —— 旧回调到达时被幂等忽略，不污染新结果；
        # B. 逐个通知子服务 cancel_task —— 真正停止/抑制旧任务的计算结果与回调。
        self._cancel_previous_evaluations(task_id)

        log_and_emit('INFO', 'reevaluator',
                     f"重新评估任务已提交: task_id={task_id}, type={reevaluate_type}",
                     task_id=task_id)

        self._check_queue()

        return True, "重新评估任务已提交"

    def _cancel_previous_evaluations(self, task_id):
        """取消该任务此前已提交的评估任务（方案A+B）。

        方案A：从回调注册表移除同 task_id 的旧 ctx，旧回调到达时被幂等忽略；
        方案B：逐个调用子服务 cancel_task 端点，子服务计算线程完成后
        检查取消标志并跳过写结果/回调，避免旧任务覆盖新评估结果。
        """
        try:
            from backend.services.evaluation.eval_callback_registry import eval_callback_registry
            import requests

            old_tasks = eval_callback_registry.pop_by_task(task_id)
            if not old_tasks:
                return

            canceled = 0
            for eval_task_id, endpoint_url in old_tasks:
                if not endpoint_url:
                    continue
                try:
                    cancel_url = f"{endpoint_url.rstrip('/')}/api/cancel_task/{eval_task_id}"
                    resp = requests.delete(cancel_url, timeout=5)
                    if resp.status_code < 300:
                        canceled += 1
                except Exception as e:
                    log_and_emit('WARNING', 'reevaluator',
                                 f"通知子服务取消评估任务失败: eval_task_id={eval_task_id}, err={e}",
                                 task_id=task_id)

            log_and_emit('INFO', 'reevaluator',
                         f"重新评估前清理旧评估任务: task_id={task_id}, "
                         f"移除注册={len(old_tasks)}, 子服务取消={canceled}",
                         task_id=task_id)
        except Exception as e:
            log_and_emit('WARNING', 'reevaluator',
                         f"清理旧评估任务异常: err={e}", task_id=task_id)

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

                        # DEBUG: 重新评估读取状态
                        _rr_out = algo_result.get('rounds', [{}])[0].get('output', {}) if isinstance(algo_result, dict) else {}
                        log_and_emit('DEBUG', 'reevaluator',
                                     f"[reevaluate READ] result_id={result.id}, result_data_path={getattr(result, 'result_data_path', None)!r}, full_data_keys={list(full_data.keys()) if full_data else 'None'}, output_record_file={_rr_out.get('record_file', '<MISSING>')!r}",
                                     task_id=task_id, test_case_id=result.test_case_id)

                        # 从文件恢复 raw_results，重新映射字段（修复多对一映射字段丢失问题）
                        raw_results_list = full_data.get('raw_results_list') if full_data else None
                        if raw_results_list:
                            from backend.services.device.device_result_collector import get_device_result_collector
                            from backend.models.models import TestCase
                            test_case = db.session.get(TestCase, result.test_case_id)
                            algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'
                            collector = get_device_result_collector()
                            remapped_results = collector.convert_results(
                                [dict(r, raw_results=r.get('raw_results', {})) for r in raw_results_list],
                                algorithm_type
                            )
                            # 用重新映射的字段更新 algo_result.rounds[].output
                            rounds_in_algo = algo_result.get('rounds', [])
                            for ri, remapped in enumerate(remapped_results):
                                if ri < len(rounds_in_algo):
                                    from backend.utils.algorithm.field_mapper import get_field_mapper
                                    fm = get_field_mapper()
                                    mapped_fields = fm.get_mapped_device_output_fields(algorithm_type)
                                    round_output = rounds_in_algo[ri].setdefault('output', {})
                                    if isinstance(mapped_fields, list):
                                        for f in mapped_fields:
                                            target = f.get('code')
                                            dim_id = f.get('dimension_id')
                                            # 维度专属 key
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
                        result.algorithm_result = algo_result if isinstance(algo_result, dict) else {}
                        db.session.commit()

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
                                'reextracted': reextract_device_output,
                                'reevaluate_type': reevaluate_type
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

                        # DEBUG: 重新评估读取状态
                        _rr_out = algo_result.get('rounds', [{}])[0].get('output', {}) if isinstance(algo_result, dict) else {}
                        log_and_emit('DEBUG', 'reevaluator',
                                     f"[reevaluate READ] result_id={result.id}, result_data_path={getattr(result, 'result_data_path', None)!r}, full_data_keys={list(full_data.keys()) if full_data else 'None'}, output_record_file={_rr_out.get('record_file', '<MISSING>')!r}",
                                     task_id=task_id, test_case_id=result.test_case_id)

                        # 从文件恢复 raw_results，重新映射字段（修复多对一映射字段丢失问题）
                        raw_results_list = full_data.get('raw_results_list') if full_data else None
                        if raw_results_list:
                            from backend.services.device.device_result_collector import get_device_result_collector
                            from backend.models.models import TestCase
                            test_case = db.session.get(TestCase, result.test_case_id)
                            algorithm_type = test_case.algorithm_type if test_case and test_case.algorithm_type else 'translation'
                            collector = get_device_result_collector()
                            remapped_results = collector.convert_results(
                                [dict(r, raw_results=r.get('raw_results', {})) for r in raw_results_list],
                                algorithm_type
                            )
                            # 用重新映射的字段更新 algo_result.rounds[].output
                            rounds_in_algo = algo_result.get('rounds', [])
                            for ri, remapped in enumerate(remapped_results):
                                if ri < len(rounds_in_algo):
                                    from backend.utils.algorithm.field_mapper import get_field_mapper
                                    fm = get_field_mapper()
                                    mapped_fields = fm.get_mapped_device_output_fields(algorithm_type)
                                    round_output = rounds_in_algo[ri].setdefault('output', {})
                                    if isinstance(mapped_fields, list):
                                        for f in mapped_fields:
                                            target = f.get('code')
                                            dim_id = f.get('dimension_id')
                                            # 维度专属 key
                                            if dim_id is not None:
                                                dim_key = f'{target}__dim_{dim_id}'
                                                dim_val = remapped.get(dim_key)
                                                if dim_val is not None:
                                                    round_output[dim_key] = dim_val
                                            # 通用 key：重新评估时无条件用 raw_results_list 的值覆盖
                                            val = remapped.get(target)
                                            if val is not None:
                                                round_output[target] = val
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
                            'result_type': result_type,
                            'reevaluate_type': reevaluate_type
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
                        reference_params_col = getattr(test_case, 'reference_params', None) if test_case else None

                        # 检查是否为多轮结果
                        if algorithm_result and 'rounds' in algorithm_result:
                            _eval_ok = self._reevaluate_multi_round(
                                task_id=task_id,
                                result=result_id,
                                test_case_id=test_case_id,
                                algorithm_result=algorithm_result,
                                test_type=test_type,
                                algorithm_type=algorithm_type,
                                reference_params_col=reference_params_col,
                                reevaluate_type=case_info.get('reevaluate_type'),
                            )
                        else:
                            _eval_ok = self._reevaluate_single(
                                task_id=task_id,
                                result_id=result_id,
                                test_case_id=test_case_id,
                                algorithm_result=algorithm_result,
                                reference_params=reference_params,
                                test_type=test_type,
                                algorithm_type=algorithm_type,
                                reference_params_col=reference_params_col,
                                reevaluate_type=case_info.get('reevaluate_type'),
                            )

                        if _eval_ok is not False:
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

    def _reevaluate_multi_round(self, task_id, result, test_case_id, algorithm_result, test_type, algorithm_type,
                               reference_params_col=None, reevaluate_type=None):
        """重新评估多轮结果 — 区分 API 和 E2E

        API 多轮结构: rounds[].round_evaluation, roundNumber (1-indexed) — 逐轮评估
        E2E 多轮结构: rounds[].evaluation, round (0-indexed) — 一次性评估所有轮

        reevaluate_type='failed' 时只重评失败的维度（按 TRD 定位到轮次），
        已完成维度的 TRD 保留不动（_create_dimension_results 会按
        (result, dim, round) 复用并重置 pending），其余类型全量重评。

        返回值: True=已提交评估, False=跳过评估(无维度), None=异常
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

        # 只重评失败维度：按 (round_number -> set(dim_id)) 收集失败的维度，保留已完成维度的 TRD
        failed_dims_by_round = {}
        if reevaluate_type == 'failed':
            failed_trds = db.session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == result,
                TestResultDimension.evaluation_status == 'failed'
            ).all()
            for trd in failed_trds:
                failed_dims_by_round.setdefault(trd.round_number, set()).add(trd.dimension_id)
            if not failed_dims_by_round:
                return False  # 没有失败的维度，无需重新评估
        else:
            # 全量重评：清理旧的维度评估记录
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

        test_case = db.session.get(TestCase, test_case_id)

        if is_e2e:
            # E2E: 逐轮评估（每轮各自的 dimensions）+ 整体评估（顶层 config.dimensions）
            case_config = test_case.config if test_case else {}
            config_rounds = case_config.get('rounds', []) if case_config else []
            any_submitted = False

            # 逐轮评估
            for round_idx in range(len(rounds)):
                # 检查本轮是否配置了评估维度
                _round_eval_enabled = True
                if config_rounds and round_idx < len(config_rounds):
                    _round_eval = config_rounds[round_idx].get('evaluation', {})
                    if isinstance(_round_eval, dict):
                        if _round_eval.get('enabled', True) is False:
                            _round_eval_enabled = False
                        elif not _round_eval.get('dimensions'):
                            _round_eval_enabled = False

                if not _round_eval_enabled:
                    continue

                # 只重评失败维度：本轮无失败维度则跳过
                dimension_filter = None
                if reevaluate_type == 'failed':
                    round_failed = failed_dims_by_round.get(round_idx)
                    if not round_failed:
                        continue
                    dimension_filter = list(round_failed)

                # 获取本轮算法参数
                algo_params = {}
                algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
                if algorithm_params_col:
                    from backend.utils.algorithm.case_parameter_extractor import _get_round_algo_params, _normalize_algorithm_params
                    algo_params = _normalize_algorithm_params(_get_round_algo_params(algorithm_params_col, round_idx + 1))
                elif config_rounds and round_idx < len(config_rounds) and isinstance(config_rounds[round_idx], dict):
                    algo_params = config_rounds[round_idx].get('algorithm_params', {})

                full_case_params = {
                    'algorithm_type': algorithm_type,
                    'algorithm_params': algo_params,
                    'reference_params': rounds[round_idx].get('reference_params', []) if round_idx < len(rounds) else [],
                    'reference_params_col': reference_params_col,
                    'rounds': (test_case.config or {}).get('rounds') if test_case else None,
                }

                try:
                    eval_params = CaseParameterExtractor.get_evaluation_params(
                        case_config=full_case_params,
                        algorithm_result=algorithm_result,
                        test_type=test_type,
                    )
                    eval_params['algorithm_type'] = algorithm_type
                    eval_params['test_type'] = test_type
                    if reference_params_col is not None:
                        eval_params['reference_params_col'] = reference_params_col
                    if dimension_filter is not None:
                        eval_params['dimension_filter_ids'] = dimension_filter

                    _eval_ok = evaluation_service.evaluate_case(
                        task_id=task_id,
                        result_id=result,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        round_number=round_idx,
                        **eval_params,
                    )

                    if _eval_ok is not False:
                        any_submitted = True
                        log_and_emit('INFO', 'reevaluator',
                                    f"已提交 E2E 轮次评估: test_case_id={test_case_id}, round={round_idx}",
                                    task_id=task_id, test_case_id=test_case_id)
                except Exception as e:
                    import traceback
                    log_and_emit('ERROR', 'reevaluator',
                                f"E2E 轮次重新评估失败: round={round_idx}, error={str(e)}, traceback={traceback.format_exc()}",
                                task_id=task_id, test_case_id=test_case_id)

            # 整体评估：仅当配置了顶层 config.dimensions 时才提交
            _has_overall_dims = bool(case_config.get('dimensions')) if case_config else False
            if _has_overall_dims:
                # 只重评失败维度：整体（round_number=None）无失败维度则跳过
                dimension_filter = None
                if reevaluate_type == 'failed':
                    overall_failed = failed_dims_by_round.get(None)
                    if not overall_failed:
                        dimension_filter = []  # 明确跳过整体提交
                    else:
                        dimension_filter = list(overall_failed)

                if dimension_filter == []:
                    pass  # 无整体失败维度，跳过
                else:
                    algo_params = {}
                    algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
                    if algorithm_params_col:
                        from backend.utils.algorithm.case_parameter_extractor import _get_round_algo_params, _normalize_algorithm_params
                        algo_params = _normalize_algorithm_params(_get_round_algo_params(algorithm_params_col, 1))
                    elif config_rounds and isinstance(config_rounds[0], dict):
                        algo_params = config_rounds[0].get('algorithm_params', {})

                    full_case_params = {
                        'algorithm_type': algorithm_type,
                        'algorithm_params': algo_params,
                        'reference_params': rounds[0].get('reference_params', []) if rounds else [],
                        'reference_params_col': reference_params_col,
                        'rounds': (test_case.config or {}).get('rounds') if test_case else None,
                    }

                    try:
                        eval_params = CaseParameterExtractor.get_evaluation_params(
                            case_config=full_case_params,
                            algorithm_result=algorithm_result,
                            test_type=test_type,
                        )
                        eval_params['algorithm_type'] = algorithm_type
                        eval_params['test_type'] = test_type
                        if reference_params_col is not None:
                            eval_params['reference_params_col'] = reference_params_col
                        if dimension_filter is not None:
                            eval_params['dimension_filter_ids'] = dimension_filter

                        _eval_ok = evaluation_service.evaluate_case(
                            task_id=task_id,
                            result_id=result,
                            test_case_id=test_case_id,
                            algorithm_result=algorithm_result,
                            **eval_params,
                        )

                        if _eval_ok is not False:
                            any_submitted = True
                            log_and_emit('INFO', 'reevaluator',
                                        f"已提交 E2E 整体评估: test_case_id={test_case_id}, rounds={len(rounds)}",
                                        task_id=task_id, test_case_id=test_case_id)
                    except Exception as e:
                        import traceback
                        log_and_emit('ERROR', 'reevaluator',
                                    f"E2E 整体重新评估失败: error={str(e)}, traceback={traceback.format_exc()}",
                                    task_id=task_id, test_case_id=test_case_id)

            return True if any_submitted else False

        else:
            # API: 逐轮评估
            for round_idx, round_data in enumerate(rounds):
                evaluation = round_data.get('round_evaluation', {})
                round_number = round_data.get('round_number', round_idx + 1) - 1

                if not evaluation:
                    continue

                # 只重评失败维度：本轮无失败维度则跳过
                dimension_filter = None
                if reevaluate_type == 'failed':
                    round_failed = failed_dims_by_round.get(round_number)
                    if not round_failed:
                        continue
                    dimension_filter = list(round_failed)

                algo_params = {}
                algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
                if algorithm_params_col:
                    from backend.utils.algorithm.case_parameter_extractor import _get_round_algo_params, _normalize_algorithm_params
                    algo_params = _normalize_algorithm_params(_get_round_algo_params(algorithm_params_col, round_idx + 1))
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
                    'rounds': (test_case.config or {}).get('rounds') if test_case else None,
                }

                try:
                    eval_params = CaseParameterExtractor.get_evaluation_params(
                        case_config=full_case_params,
                        algorithm_result=algorithm_result,
                        test_type=test_type,
                    )
                    eval_params['algorithm_type'] = algorithm_type
                    eval_params['test_type'] = test_type
                    if reference_params_col is not None:
                        eval_params['reference_params_col'] = reference_params_col
                    if dimension_filter is not None:
                        eval_params['dimension_filter_ids'] = dimension_filter

                    _eval_ok = evaluation_service.evaluate_case(
                        task_id=task_id,
                        result_id=result,
                        test_case_id=test_case_id,
                        algorithm_result=algorithm_result,
                        round_number=round_number,
                        **eval_params,
                    )

                    if _eval_ok is not False:
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
            return True

    def _reevaluate_single(self, task_id, result_id, test_case_id, algorithm_result, reference_params, test_type, algorithm_type,
                           reference_params_col=None, reevaluate_type=None):
        """重新评估单轮结果（现有逻辑）

        reevaluate_type='failed' 时只重评失败的维度，已完成维度的 TRD 保留不动。

        返回值: True=已提交评估, False=跳过评估(无维度)
        """
        # 循环反序列化，处理可能的双重序列化旧数据
        while isinstance(algorithm_result, str):
            try:
                algorithm_result = json.loads(algorithm_result)
            except (json.JSONDecodeError, ValueError):
                algorithm_result = {}
        if not isinstance(algorithm_result, dict):
            algorithm_result = {}
        # 只重评失败维度：收集失败的维度，保留已完成维度的 TRD
        failed_dim_ids = None
        if reevaluate_type == 'failed':
            failed_trds = db.session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == result_id,
                TestResultDimension.evaluation_status == 'failed'
            ).all()
            failed_dim_ids = {trd.dimension_id for trd in failed_trds}
            if not failed_dim_ids:
                return False  # 没有失败的维度，无需重新评估
        else:
            # 全量重评：清理旧的维度评估记录
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

        # 优先从独立列读取 algorithm_params（按轮分组），兼容旧数据从 config.rounds 读取
        algo_params = {}
        algorithm_params_col = getattr(test_case, 'algorithm_params', None) if test_case else None
        if algorithm_params_col:
            from backend.utils.algorithm.case_parameter_extractor import _get_round_algo_params, _normalize_algorithm_params
            algo_params = _normalize_algorithm_params(_get_round_algo_params(algorithm_params_col, 1))
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
            'rounds': (test_case.config or {}).get('rounds') if test_case else None,
        }

        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=algorithm_result,
            test_type=test_type
        )
        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = test_type
        if reference_params_col is not None:
            eval_params['reference_params_col'] = reference_params_col

        db.session.commit()

        if failed_dim_ids is not None:
            eval_params['dimension_filter_ids'] = list(failed_dim_ids)

        return evaluation_service.evaluate_case(
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
        """重新评估提交阶段完成回调。

        注意：这里只代表"评估任务已全部提交"，评估本身仍在后台计算。
        因此不再直接把任务置为 completed——提交成功时置为 running，
        由 maybe_finalize（所有用例评估到终态后触发）最终置 completed；
        仅当提交本身失败时才置 failed。
        """
        current_app = get_app()
        with current_app.app_context():
            task = db.session.query(Task).get(task_id)
            if task:
                task.status = 'running' if success else 'failed'
                db.session.commit()

        if not success:
            # 提交失败：任务收尾并释放重新评估队列
            with self.reevaluation_lock:
                self.is_reevaluating = False
                self.running_task_id = None
            self._check_queue()

        log_and_emit('INFO', 'reevaluator',
                     f"重新评估任务提交完成: task_id={task_id}, success={success}（评估仍在后台计算，任务状态=running）",
                     task_id=task_id)

    def maybe_finalize(self, task_id):
        """检查重新评估是否真正完成（所有已执行用例的评估都到终态）。

        由评估结果回调（on_complete/on_failed）在写结果后调用；
        仅当该任务确实是当前重新评估处理中的任务时才收尾，
        普通执行引擎评估任务不受影响。

        服务重启兼容（修复）：app.py 启动恢复会把"重新评估中"的任务以及
        进行中的用例/维度置为 failed，但评估实际在远端 eval_server 继续执行，
        回调仍会把用例逐个置回 completed。这里在用例全部到达终态后统一收尾为
        completed；当当前进程已不再跟踪该任务（如重启后 running_task_id 清空）时，
        仅对确系被重启恢复误标过的重新评估任务（整任务执行均已完成 + 用例带
        "服务重启"标记）兜底收尾，避免误改普通执行中被中断/真实失败的任务。
        """
        current_app = get_app()
        with current_app.app_context():
            # 只检查已执行完成的用例（未执行用例不参与重新评估）
            tcs = db.session.query(TaskCase).filter_by(
                task_id=task_id,
                execution_status='completed',
                deleted=False
            ).all()
            if not tcs:
                return False

            # 仍有用例在评估，继续等待
            if any(tc.evaluation_status in ('queued', 'running', 'calculating') for tc in tcs):
                return False

            task = db.session.query(Task).get(task_id)
            if not task:
                return False
            if task.status not in ('running', 'failed', 'reevaluating', 'reevaluate_queued'):
                return False

            with self.reevaluation_lock:
                is_current_task = (self.running_task_id == task_id)

            if not is_current_task:
                # 服务重启后进程态丢失：仅当该任务确为被重启恢复误标的重新评估任务时才兜底收尾。
                # 重新评估不重跑执行，其用例 execution_status 应全部为 completed；
                # 普通执行任务被重启中断时会有执行失败的用例，不会被误收尾。
                all_tcs = db.session.query(TaskCase).filter_by(
                    task_id=task_id, deleted=False).all()
                all_exec_completed = all(tc.execution_status == 'completed' for tc in all_tcs)
                restart_marked = any(
                    (tc.error_message or '').startswith('服务重启')
                    for tc in tcs
                )
                if not (all_exec_completed and restart_marked):
                    return False

            if task.status != 'completed':
                task.status = 'completed'
                db.session.commit()

            log_and_emit('INFO', 'reevaluator',
                         f"重新评估完成: task_id={task_id}，任务状态更新为 completed",
                         task_id=task_id)

        # 释放重新评估队列，启动下一个排队任务（仅当自己仍是当前处理任务时）
        with self.reevaluation_lock:
            if self.running_task_id == task_id:
                self.is_reevaluating = False
                self.running_task_id = None
        self._check_queue()
        return True
