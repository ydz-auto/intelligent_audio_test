# -*- coding: utf-8 -*-
"""
BaseExecutor — 执行器基类（共享内核 / Shared Kernel）

由 task_service/core/base_executor.py 迁移至 shared/infrastructure/，
供 api_test_service 与 task_service 共用。

迁移说明：
- 原直接调用 `from task_service.evaluation.evaluation_service import evaluation_service`
  改为通过 gRPC 调用 task_service 的 ExecutionService.EvaluateCase。
  `_evaluate_result` 不再直接调用 evaluation_service，而是委托给
  `_submit_evaluation_grpc`（位于 shared.clients.grpc_clients）。
"""
import threading
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from shared.utils.log_handler import log_and_emit
from shared.algorithm.field_mapper import get_field_mapper
from shared.algorithm.algorithm_config_loader import get_config_loader
from shared.models.database import db
from shared.models.models import utc8now, Task, TaskCase, TestCase
import json


class BaseExecutor:
    """执行器基类"""

    def __init__(self, execution_engine=None):
        self.execution_engine = execution_engine
        self._thread_ctx = threading.local()
        self.current_test_case_id = None
        self.current_case_field_values = {}
        self.utc_plus_8 = timezone(timedelta(hours=8))

    def _handle_control(self, task_id):
        """处理暂停和停止逻辑（从中央存储获取事件）"""
        stop_event, pause_event = self._get_control_events(task_id)

        if stop_event is not None and stop_event.is_set():
            raise Exception("任务已停止")

        if pause_event is not None and not pause_event.is_set():
            self._log(level='INFO', content="检测到暂停指令，等待恢复...", task_id=task_id)
            while pause_event is not None and not pause_event.is_set():
                if stop_event is not None and stop_event.is_set():
                    raise Exception("任务已停止")
                pause_event.wait(timeout=0.5)
            self._log(level='INFO', content="任务已恢复执行", task_id=task_id)

    def _get_control_events(self, task_id):
        """获取控制事件

        直接从本进程的 execution_engine 单例获取 threading.Event 对象。
        execution_engine 是进程内单例，stop_flags/pause_flags
        是进程内 Event，无需跨进程获取。
        """
        engine = self.execution_engine
        if engine is None:
            return None, None
        stop_event = engine.stop_flags.get(task_id)
        pause_event = engine.pause_flags.get(task_id)
        return stop_event, pause_event

    def _log(self, level, content, task_id=None, test_case_id=None, device_id=None, api_id=None, category='execution', **kwargs):
        """统一日志记录方法"""
        final_test_case_id = test_case_id or getattr(self._thread_ctx, 'current_test_case_id', None) or self.current_test_case_id

        log_and_emit(
            level=level,
            module='Engine',
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            test_case_id=final_test_case_id,
            device_id=device_id,
            api_id=api_id,
            **kwargs
        )

    def _execute_extra_params(self, algorithm_type, passed_kwargs=None, include_format_strings=True):
        """从配置动态获取算法特定参数"""
        if passed_kwargs is None:
            passed_kwargs = {}

        if isinstance(passed_kwargs, dict):
            if 'algorithm_type' in passed_kwargs:
                case_field_values = passed_kwargs
                passed_kwargs = {}
            else:
                case_field_values = getattr(self, 'current_case_field_values', {})
        else:
            case_field_values = getattr(self, 'current_case_field_values', {})

        field_mapper = get_field_mapper()
        extra_config = field_mapper._get_algorithm_extra_config(algorithm_type)

        result_params = {}

        if extra_config.get('needs_extra_params'):
            case_fields = extra_config.get('case_fields', {})
            format_strings = extra_config.get('format_strings', {})
            db_model_name = extra_config.get('db_model')
            db_id_field = extra_config.get('db_id_field')

            db_model = None
            if db_model_name:
                import importlib
                model_module = importlib.import_module('shared.models.models')
                db_model = getattr(model_module, db_model_name, None)

            if format_strings:
                db_lang_fields = extra_config.get('db_lang_fields', {})
                default_lang = extra_config.get('default_lang', {})
            else:
                db_lang_fields = {}
                default_lang = {}

            for param_name, case_field in case_fields.items():
                param_value = case_field_values.get(param_name)

                format_str = format_strings.get(param_name)
                if format_str and param_value and db_model:
                    local_db_session = db.session()
                    try:
                        db_record = local_db_session.query(db_model).get(param_value)
                        if db_record:
                            format_kwargs = {}
                            for key, field in db_lang_fields.items():
                                format_kwargs[key] = getattr(db_record, field, default_lang.get(key))
                            result_params[param_name] = format_str.format(**format_kwargs)
                            if db_id_field:
                                result_params[db_id_field] = param_value
                    finally:
                        local_db_session.close()
                elif format_str and param_value:
                    result_params[param_name] = format_str.format(value=param_value)
                elif param_value is not None:
                    result_params[param_name] = param_value

            if include_format_strings and format_strings:
                for param_name, format_str in format_strings.items():
                    if param_name not in result_params:
                        format_kwargs = {k: default_lang.get(k, '') for k in db_lang_fields.keys()}
                        format_value = format_str.format(**format_kwargs)
                        result_params[param_name] = format_value

        return result_params

    def _get_result_mapper(self):
        """获取结果映射器"""
        # 跨服务调用：通过 gRPC DeviceResultService 获取结果采集器
        from shared.clients.grpc_clients import get_device_result_service_stub
        return _DeviceResultCollectorProxy(get_device_result_service_stub())

    def _process_results(self, task_id, test_case_id, all_results, case_config=None,
                        case_reference_params=None, algorithm_type='translation',
                        device_id_field='device_id', api_id_field='api_id',
                        result_data_extra=None, **kwargs):
        """处理测试结果 - 通用方法"""
        self._log(
            level='DEBUG',
            content=f"[_process_results] 开始处理结果 task_id={task_id}, test_case_id={test_case_id}, algorithm_type={algorithm_type}, results_count={len(all_results) if all_results else 0}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        if case_config:
            self._log(
                level='DEBUG',
                content=f"[_process_results] case_config: {json.dumps(case_config, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if case_reference_params:
            self._log(
                level='DEBUG',
                content=f"[_process_results] case_reference_params: {json.dumps(case_reference_params, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        adjusted_reference_params = None
        for res in all_results:
            if 'adjusted_reference_params' in res:
                adjusted_reference_params = res.get('adjusted_reference_params')
                if adjusted_reference_params:
                    self._log(
                        level='DEBUG',
                        content=f"[_process_results] 使用调整后的参考参数",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    case_reference_params = adjusted_reference_params
                break

        field_mapper = get_field_mapper()

        if result_data_extra is None:
            result_data_extra = {}

        if case_config:
            extra_config = field_mapper._get_algorithm_extra_config(algorithm_type)
            output_keys = extra_config.get('output_keys', {})
            for key, config_key in output_keys.items():
                if config_key not in result_data_extra and config_key in case_config:
                    result_data_extra[config_key] = case_config[config_key]

        config_loader = get_config_loader()
        import copy
        all_results = copy.deepcopy(all_results)

        self._log(
            level='DEBUG',
            content=f"[_process_results] after deepcopy: all_results id={id(all_results)}, results_count={len(all_results)}, raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10] if all_results else 'empty'}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_process_results] before get_result_mapper: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        collector = self._get_result_mapper()

        self._log(
            level='DEBUG',
            content=f"[_process_results] after get_result_mapper: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        case_params = case_config or {}

        self._log(
            level='DEBUG',
            content=f"[_process_results] after case_params: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        mapped_output_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)

        self._log(
            level='DEBUG',
            content=f"[_process_results] after mapped_output_keys: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        import copy
        all_results = copy.deepcopy(all_results)

        self._log(
            level='DEBUG',
            content=f"[_process_results] after 2nd deepcopy: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_process_results] before convert_results: all_results id={id(all_results)}, results_count={len(all_results)}, raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:5] if all_results else 'empty'}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        all_results = collector.convert_results(all_results, algorithm_type)

        execution_success = True
        all_eval_items = []

        for res in all_results:
            raw_results = res.get('raw_results', {})
            success = raw_results.get('success', False)

            result_type = res.get('result_type', 'default')

            if not success:
                execution_success = False

            algo_result = {}
            for key in mapped_output_keys:
                if res.get(key):
                    algo_result[key] = res[key]

            result_data_to_save = res.copy()
            if result_type and result_type != 'default':
                result_data_to_save['result_type'] = result_type

            from shared.utils.result_data_store import write_result_data_file, split_result_data
            device_sn = res.get('device_sn', 'unknown')
            result_data_path = write_result_data_file(task_id, test_case_id, device_sn, result_data_to_save)
            lightweight_data, _ = split_result_data(result_data_to_save)

            result_id = self._save_result(
                task_id=task_id,
                test_case_id=test_case_id,
                result_data=lightweight_data,
                algo_result=algo_result,
                algorithm_type=algorithm_type,
                device_id=res.get(device_id_field),
                api_id=res.get(api_id_field),
                execution_status='completed' if success else 'failed',
                response_time=450 if success else 0,
                error_message=None if success else "采集结果失败",
                extra_data=result_data_extra,
                result_data_path=result_data_path
            )

            self._log(
                level='DEBUG',
                content=f"[_process_results] 保存结果 result_id={result_id}, result_type={result_type}, success={success}, device_id={res.get(device_id_field)}, api_id={res.get(api_id_field)}",
                task_id=task_id,
                test_case_id=test_case_id,
                device_id=res.get(device_id_field),
                api_id=res.get(api_id_field)
            )

            if algo_result:
                self._log(
                    level='DEBUG',
                    content=f"[_process_results] algo_result: {json.dumps(algo_result, ensure_ascii=False, indent=2)[:500]}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    device_id=res.get(device_id_field),
                    api_id=res.get(api_id_field)
                )

            if success:
                eval_item = {
                    'result_id': result_id,
                    'res': res,
                    'test_case_id': test_case_id
                }
                if 'round_number' in res:
                    eval_item['round_number'] = res['round_number']
                all_eval_items.append(eval_item)

        self._log(
            level='DEBUG',
            content=f"[_process_results] 处理完成 task_id={task_id}, test_case_id={test_case_id}, execution_success={execution_success}, eval_items_count={len(all_eval_items)}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        return {
            'execution_success': execution_success,
            'all_eval_items': all_eval_items,
            'case_params': case_params,
            'case_reference_params': case_reference_params,
            'algorithm_type': algorithm_type
        }

    def _evaluate_result(self, task_id, result_id, test_case_id, algo_result, case_config=None,
                        case_reference_params=None, algorithm_type='translation', test_type='api',
                        case_algorithm_params=None, round_number=None,
                        reference_params_col=None):
        """提交评估 - 通用方法

        迁移后改为通过 gRPC 调用 task_service 的 ExecutionService.EvaluateCase。
        """
        self._log(
            level='DEBUG',
            content=f"[DEBUG _evaluate_result] 传入参数: task_id={task_id}, result_id={result_id}, result_id_type={type(result_id)}, test_case_id={test_case_id}, algorithm_type={algorithm_type}, test_type={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] 开始评估 task_id={task_id}, result_id={result_id}, test_case_id={test_case_id}, algorithm_type={algorithm_type}, test_type={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        if case_config:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] case_config: {json.dumps(case_config, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if case_reference_params:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] case_reference_params: {json.dumps(case_reference_params, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if case_algorithm_params:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] case_algorithm_params: {json.dumps(case_algorithm_params, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if algo_result:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] algo_result: {json.dumps(algo_result, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        from shared.algorithm.case_parameter_extractor import CaseParameterExtractor

        case_params = case_config or {}
        algorithm_params = case_params.get('algorithm_params', case_params)

        if case_algorithm_params:
            if isinstance(case_algorithm_params, list):
                case_algorithm_params_dict = {}
                for item in case_algorithm_params:
                    if isinstance(item, dict) and 'field_code' in item:
                        case_algorithm_params_dict[item['field_code']] = item.get('field_value')
                case_algorithm_params = case_algorithm_params_dict

            if isinstance(algorithm_params, dict):
                algorithm_params = {**case_algorithm_params, **algorithm_params}
            else:
                algorithm_params = case_algorithm_params

        if case_reference_params:
            reference_params = case_reference_params
        else:
            reference_params = case_params.get('reference_params', {})

        full_case_params = {
            'algorithm_type': algorithm_type,
            'algorithm_params': algorithm_params,
            'reference_params': reference_params,
            'reference_params_col': reference_params_col,
            'rounds': case_config.get('rounds') if case_config else None,
        }

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] algorithm_params: {json.dumps(algorithm_params, ensure_ascii=False, indent=2)[:500]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] reference_params: {json.dumps(reference_params, ensure_ascii=False, indent=2)[:500]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=algo_result,
            test_type=test_type
        )

        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = test_type
        if round_number is not None:
            eval_params['round_number'] = round_number
        if reference_params_col is not None:
            eval_params['reference_params_col'] = reference_params_col

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] 调用评估服务(通过gRPC) task_id={task_id}, result_id={result_id}, eval_params={json.dumps(eval_params, ensure_ascii=False, indent=2)[:500]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 通过 gRPC 调用 task_service 的 EvaluateCase
        from shared.clients.grpc_clients import submit_evaluate_case
        submit_evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algo_result,
            eval_params=eval_params,
        )

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] 评估已提交 task_id={task_id}, result_id={result_id}, test_case_id={test_case_id}",
            task_id=task_id,
            test_case_id=test_case_id
        )

    def _log_case_result(self, task_id, case_name, res, ref_fields=None, algorithm_type='translation', **kwargs):
        """记录用例结果日志 - 通用方法"""
        collector = self._get_result_mapper()

        log_content = f"用例 {case_name}: " + collector.build_case_result_log(algorithm_type, res, ref_fields, **kwargs)

        raw_results = res.get('raw_results', {})
        success = raw_results.get('success', False)
        test_case_id = kwargs.pop('test_case_id', None)

        self._log(
            level='INFO' if success else 'WARNING',
            content=log_content,
            task_id=task_id,
            test_case_id=test_case_id,
            device_id=res.get('device_id'),
            api_id=res.get('api_id')
        )

    def _validate_and_get_data(self, task_id, tc_rel_id):
        local_db_session = db.session()
        try:
            task = local_db_session.query(Task).get(task_id)
            if not task:
                return {'success': False, 'error': "任务不存在"}
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if not tc_rel:
                return {'success': False, 'error': "找不到测试用例关联"}
            case = local_db_session.query(TestCase).get(tc_rel.test_case_id)
            if not case:
                return {'success': False, "error": "找不到测试用例"}

            case_config = case.config or {}
            algorithm_type = case.algorithm_type if hasattr(case, 'algorithm_type') and case.algorithm_type else None
            if not algorithm_type:
                algorithm_type = case_config.get('algorithm_type')
            if not algorithm_type:
                algorithm_type = 'translation'

            self._log(
                level='DEBUG',
                content=f"[_validate_and_get_data] case.algorithm_type={case.algorithm_type}, case_config.algorithm_type={case_config.get('algorithm_type')}, final algorithm_type={algorithm_type}",
                task_id=task_id,
                test_case_id=tc_rel.test_case_id
            )

            field_mapper = get_field_mapper()
            case_fields = field_mapper.get_case_fields(algorithm_type)

            from shared.algorithm.case_parameter_extractor import _get_round_algo_params, _normalize_algorithm_params
            algorithm_params_col = getattr(case, 'algorithm_params', None)

            case_config = case_config.copy() if case_config else {}
            rounds = case_config.get('rounds', [])
            for round_item in rounds:
                if isinstance(round_item, dict):
                    rn = round_item.get('round_number', 1)
                    round_params = _get_round_algo_params(algorithm_params_col, rn)
                    if round_params:
                        round_item['algorithm_params'] = round_params

            first_round = rounds[0] if rounds else {}
            case_algorithm_params = _normalize_algorithm_params(
                first_round.get('algorithm_params', {}) if isinstance(first_round, dict) else {}
            )

            from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
            reference_params_col = getattr(case, 'reference_params', None)
            all_reference_params = []

            if reference_params_col and isinstance(reference_params_col, list):
                for ref_entry in reference_params_col:
                    if isinstance(ref_entry, dict):
                        ref_path = ref_entry.get('reference_params_path')
                        if ref_path:
                            round_refs = ReferenceParamsGenerator.load_from_file(ref_path)
                            if round_refs:
                                all_reference_params.extend(round_refs)
            else:
                for round_item in rounds:
                    if isinstance(round_item, dict):
                        ref_path = round_item.get('reference_params_path')
                        if ref_path:
                            round_refs = ReferenceParamsGenerator.load_from_file(ref_path)
                            if round_refs:
                                all_reference_params.extend(round_refs)

            case_reference_params = all_reference_params if all_reference_params else {}

            if case_algorithm_params:
                case_config['algorithm_params'] = case_algorithm_params

            result_data = {
                'case_name': case.name,
                'case_config': case_config,
                'case_reference_params': case_reference_params,
                'reference_params_col': reference_params_col if isinstance(reference_params_col, list) else None,
                'case_algorithm_params': case_algorithm_params,
                'test_case_id': tc_rel.test_case_id,
                'tc_rel_id': tc_rel_id,
                'algorithm_type': algorithm_type,
                'task_name': task.name if task else None,
            }

            for config_key, case_field in case_fields.items():
                result_data[config_key] = getattr(case, case_field, None)

            return {'success': True, 'data': result_data}
        finally:
            local_db_session.close()

    def _update_tc_rel_status(self, tc_rel_id, **kwargs):
        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if tc_rel:
                for key, value in kwargs.items():
                    setattr(tc_rel, key, value)
                if 'execution_status' in kwargs:
                    if kwargs['execution_status'] == 'running':
                        tc_rel.started_at = datetime.now(self.utc_plus_8)
                        tc_rel.evaluation_status = 'queued'
                    elif kwargs['execution_status'] in ['completed', 'failed']:
                        tc_rel.completed_at = datetime.now(self.utc_plus_8)
                        if tc_rel.evaluation_status in ['queued', 'pending']:
                            tc_rel.evaluation_status = 'completed'
                local_db_session.commit()

                task_id = tc_rel.task_id
                if task_id and self.execution_engine:
                    self.execution_engine._emit_progress(task_id, force=True)
        finally:
            local_db_session.close()


class _DeviceResultCollectorProxy:
    """设备结果采集器代理：将本地对象方法调用封装为 gRPC DeviceResultService 调用"""

    def __init__(self, stub):
        self._stub = stub

    def convert_results(self, all_results, algorithm_type):
        import json as _json
        from shared.proto import e2e_service_pb2
        req = e2e_service_pb2.CollectResultRequest(
            task_id='',
            collect_config=_json.dumps({
                'action': 'convert_results',
                'all_results': all_results,
                'algorithm_type': algorithm_type,
            })
        )
        resp = self._stub.CollectResult(req)
        if not resp.success or not resp.data:
            return all_results
        return _json.loads(resp.data)

    def build_case_result_log(self, algorithm_type, res, ref_fields=None, **kwargs):
        import json as _json
        from shared.proto import e2e_service_pb2
        req = e2e_service_pb2.CollectResultRequest(
            task_id='',
            collect_config=_json.dumps({
                'action': 'build_case_result_log',
                'algorithm_type': algorithm_type,
                'res': res,
                'ref_fields': ref_fields,
                'kwargs': kwargs,
            })
        )
        resp = self._stub.CollectResult(req)
        if not resp.success or not resp.data:
            return ''
        return resp.data

    def collect_raw_results(self, task_id, test_case_id, device_info_list, extra_params, log_callback=None, **kwargs):
        import json as _json
        from shared.proto import e2e_service_pb2
        req = e2e_service_pb2.CollectResultRequest(
            task_id=str(task_id),
            collect_config=_json.dumps({
                'action': 'collect_raw_results',
                'test_case_id': test_case_id,
                'device_info_list': device_info_list,
                'extra_params': extra_params,
                'kwargs': kwargs,
            })
        )
        resp = self._stub.CollectResult(req)
        if not resp.success or not resp.data:
            return []
        return _json.loads(resp.data)

    def _save_result(self, task_id, test_case_id, result_data, algo_result, algorithm_type,
                     device_id=None, api_id=None, execution_status='completed', response_time=0,
                     error_message=None, extra_data=None, result_data_path=None):
        """保存测试结果到数据库"""
        insert_sql = text("""
            INSERT INTO test_results (task_id, test_case_id, device_id, api_id, algorithm_type, execution_status, response_time, algorithm_result, execution_steps, result_data, result_data_path, error_message, created_at)
            VALUES (:task_id, :test_case_id, :device_id, :api_id, :algorithm_type, :execution_status, :response_time, :algorithm_result, :execution_steps, :result_data, :result_data_path, :error_message, :created_at)
            RETURNING id
        """)

        params = {
            'task_id': task_id,
            'test_case_id': test_case_id,
            'device_id': device_id,
            'api_id': api_id,
            'algorithm_type': algorithm_type,
            'execution_status': execution_status,
            'response_time': response_time,
            'algorithm_result': json.dumps(algo_result) if algo_result else None,
            'execution_steps': '[]',
            'result_data': json.dumps(result_data) if result_data else None,
            'result_data_path': result_data_path or None,
            'error_message': error_message,
            'created_at': utc8now()
        }

        with db.engine.connect() as conn:
            result = conn.execute(insert_sql, params)
            result_id = result.scalar()
            conn.commit()

        return result_id
