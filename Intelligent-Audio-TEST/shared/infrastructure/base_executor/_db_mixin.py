# -*- coding: utf-8 -*-
"""数据库操作相关方法。

原 `from task_service.infrastructure.persistence.models import Task, TaskCase, TestCase`
跨服务 PO 直连已改为 gRPC 调用（task_service.TaskDataService / TestCaseConfigService），
避免 shared/ 跨服务 ORM 直连。
"""
import json

from shared.clients.grpc_clients import (
    algo_get_device_params,
    algo_get_api_params,
    algo_get_param_mapping,
    algo_get_round_algo_params,
    algo_normalize_algorithm_params,
    algo_load_reference_params_file,
)


class DbMixin:
    """执行器基类数据库操作方法"""

    def _validate_and_get_data(self, task_id, tc_rel_id):
        # 延迟 import + try/except 容错
        from shared.clients.grpc_clients import (
            get_task_data_service_stub,
            get_testcase_config_service_stub,
        )
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads

        data_stub = get_task_data_service_stub()

        # 通过 gRPC 查询 TaskCase（按 task_id 拉全量后按 id 过滤，
        # 因为 GetTaskCaseByIds 的 case_ids 按 test_case_id 过滤，非 TaskCase.id）
        tc_rel = None
        try:
            resp = data_stub.GetTaskCaseByIds(task_pb.GetTaskCaseByIdsRequest(task_id=int(task_id)))
            if resp.success:
                tcs = _loads(resp.data, []) or []
                tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TaskCase 失败: {e}", task_id=task_id)
        if not tc_rel:
            return {'success': False, 'error': "找不到测试用例关联"}

        # 通过 gRPC 查询 Task
        task = None
        try:
            resp = data_stub.GetTaskById(task_pb.GetTaskByIdRequest(task_id=int(task_id)))
            if resp.success:
                task = _loads(resp.data, {}) or {}
        except Exception as e:
            self._log(level='WARNING', content=f"查询 Task 失败: {e}", task_id=task_id)
        if not task:
            return {'success': False, 'error': "任务不存在"}

        # 通过 gRPC 查询 TestCase 详情
        tc_rel_test_case_id = tc_rel.get('test_case_id')
        case = None
        try:
            tc_stub = get_testcase_config_service_stub()
            resp = tc_stub.GetTestCaseDetail(task_pb.GetTestCaseDetailRequest(tc_id=str(tc_rel_test_case_id)))
            if resp.success:
                case = _loads(resp.data, {}) or {}
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TestCase 失败: {e}", task_id=task_id)
        if not case:
            return {'success': False, 'error': "找不到测试用例"}

        case_config = case.get('config') or {}
        algorithm_type = case.get('algorithm_type') if case.get('algorithm_type') else None
        if not algorithm_type:
            algorithm_type = case_config.get('algorithm_type')
        if not algorithm_type:
            algorithm_type = 'translation'

        self._log(
            level='DEBUG',
            content=f"[_validate_and_get_data] case.algorithm_type={case.get('algorithm_type')}, case_config.algorithm_type={case_config.get('algorithm_type')}, final algorithm_type={algorithm_type}",
            task_id=task_id,
            test_case_id=tc_rel_test_case_id
        )

        case_fields = _get_case_fields(algorithm_type)

        algorithm_params_col = case.get('algorithm_params')

        case_config = case_config.copy() if case_config else {}
        rounds = case_config.get('rounds', [])
        for round_item in rounds:
            if isinstance(round_item, dict):
                rn = round_item.get('round_number', 1)
                round_params = algo_get_round_algo_params(algorithm_params_col, rn)
                if round_params:
                    round_item['algorithm_params'] = round_params

        first_round = rounds[0] if rounds else {}
        case_algorithm_params = algo_normalize_algorithm_params(
            first_round.get('algorithm_params', {}) if isinstance(first_round, dict) else {}
        )

        reference_params_col = case.get('reference_params')
        all_reference_params = []

        if reference_params_col and isinstance(reference_params_col, list):
            for ref_entry in reference_params_col:
                if isinstance(ref_entry, dict):
                    ref_path = ref_entry.get('reference_params_path')
                    if ref_path:
                        round_refs = algo_load_reference_params_file(ref_path)
                        if round_refs:
                            all_reference_params.extend(round_refs)
        else:
            for round_item in rounds:
                if isinstance(round_item, dict):
                    ref_path = round_item.get('reference_params_path')
                    if ref_path:
                        round_refs = algo_load_reference_params_file(ref_path)
                        if round_refs:
                            all_reference_params.extend(round_refs)

        case_reference_params = all_reference_params if all_reference_params else {}

        if case_algorithm_params:
            case_config['algorithm_params'] = case_algorithm_params

        result_data = {
            'case_name': case.get('name'),
            'case_config': case_config,
            'case_reference_params': case_reference_params,
            'reference_params_col': reference_params_col if isinstance(reference_params_col, list) else None,
            'case_algorithm_params': case_algorithm_params,
            'test_case_id': tc_rel_test_case_id,
            'tc_rel_id': tc_rel_id,
            'algorithm_type': algorithm_type,
            'task_name': task.get('name') if task else None,
        }

        for config_key, case_field in case_fields.items():
            result_data[config_key] = case.get(case_field)

        return {'success': True, 'data': result_data}

    def _update_tc_rel_status(self, tc_rel_id, **kwargs):
        # 通过 gRPC 调用 task_service.TaskDataService.UpdateTaskCaseStatus 更新 TaskCase 状态，
        # 替代直连 TaskCase PO。联动逻辑（running -> evaluation_status=queued;
        # completed/failed -> evaluation_status=completed）在客户端侧复现。
        # TODO(gRPC): started_at / completed_at 时间戳由 task_service 侧在
        # UpdateTaskCaseStatus 仓储层根据 execution_status 自动设置，当前 proto 未暴露，
        # 需扩展 task_service proto 增加时间戳字段或专用 RPC 后由服务端统一维护。
        from shared.clients.grpc_clients import (
            get_task_data_service_stub,
            update_task_case_status,
            notify_task_progress,
        )
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads

        # 1. 通过 gRPC 按 tc_rel_id 查询 TaskCase，拿到 test_case_id 与当前状态
        #    GetTaskCaseByIds 的 case_ids 按 test_case_id 过滤，非 TaskCase.id，
        #    因此按 task_id 拉全量后按 id 过滤。
        # task_id 由调用方通过 kwargs 传入（gRPC UpdateTaskCaseStatus 需 task_id+test_case_id）
        task_id = kwargs.pop('task_id', None)
        test_case_id = None
        current_eval = 'pending'
        if task_id is None:
            # 无 task_id 时无法走 gRPC（UpdateTaskCaseStatus 需 task_id+test_case_id）
            self._log(
                level='WARNING',
                content=f"_update_tc_rel_status 缺少 task_id，无法通过 gRPC 更新 TaskCase: {tc_rel_id}",
            )
            return
        try:
            data_stub = get_task_data_service_stub()
            resp = data_stub.GetTaskCaseByIds(task_pb.GetTaskCaseByIdsRequest(task_id=int(task_id)))
            if resp.success:
                tcs = _loads(resp.data, []) or []
                tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
                if tc_rel:
                    test_case_id = tc_rel.get('test_case_id')
                    current_eval = tc_rel.get('evaluation_status', 'pending')
        except Exception as e:
            self._log(
                level='WARNING',
                content=f"_update_tc_rel_status 查询 TaskCase 失败: {e}",
                task_id=task_id,
            )
            return

        if not test_case_id:
            self._log(
                level='WARNING',
                content=f"_update_tc_rel_status 找不到 TaskCase: tc_rel_id={tc_rel_id}, task_id={task_id}",
                task_id=task_id,
            )
            return

        # 2. 提取 gRPC 支持的字段
        status = kwargs.get('status') or ''
        execution_status = kwargs.get('execution_status') or ''
        error_message = kwargs.get('error_message') or ''
        evaluation_status = kwargs.get('evaluation_status') or ''

        # 3. 复现原直连 PO 的联动逻辑
        #    running -> evaluation_status=queued（除非调用方显式指定）
        #    completed/failed -> evaluation_status=completed（若当前为 queued/pending）
        if execution_status == 'running' and not evaluation_status:
            evaluation_status = 'queued'
        elif execution_status in ('completed', 'failed'):
            if not evaluation_status and current_eval in ('queued', 'pending'):
                evaluation_status = 'completed'

        # 4. 通过 gRPC 更新
        try:
            update_task_case_status(
                task_id=task_id,
                case_id=test_case_id,
                status=status,
                execution_status=execution_status,
                evaluation_status=evaluation_status,
                error_message=error_message,
            )
        except Exception as e:
            self._log(
                level='ERROR',
                content=f"_update_tc_rel_status gRPC 更新失败: {e}",
                task_id=task_id,
                test_case_id=test_case_id,
            )
            return

        # 5. 通过 gRPC 通知进度（替代 execution_engine._emit_progress）
        try:
            notify_task_progress(task_id, force=True)
        except Exception as e:
            self._log(
                level='WARNING',
                content=f"_update_tc_rel_status 通知进度失败: {e}",
                task_id=task_id,
            )

    def _save_result(self, task_id, test_case_id, result_data, algo_result, algorithm_type,
                     device_id=None, api_id=None, execution_status='completed', response_time=0,
                     error_message=None, extra_data=None, result_data_path=None):
        """保存测试结果到数据库（通过 gRPC 调用 task_service.TaskDataService.SubmitResult）

        test_results 表属于 task_service，shared 层不再直连写表，
        统一通过 gRPC SubmitResult 跨服务写入。
        """
        from shared.clients.grpc_clients import submit_result
        result_payload = {
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
        }
        try:
            return submit_result(task_id, result_payload)
        except Exception as e:
            self._log(
                level='ERROR',
                content=f"[_save_result] gRPC SubmitResult 失败: {e}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            return None


def _get_case_fields(algorithm_type):
    """获取算法需要的 case 表字段（迁移自 FieldMapper.get_case_fields）

    返回 {param_code: param_code}（或 mapping 的 {target_key: source_param}）。
    扫描 device_params + api_params 中 source=='case_table' 或 param_type
    in ['direction', 'language'] 的字段，以及 param mappings 中 source=='case_table' 的映射。
    """
    case_fields = {}
    params = (algo_get_device_params(algorithm_type) or []) + (algo_get_api_params(algorithm_type) or [])
    for param in params:
        param_code = param.get('code', '')
        param_type = param.get('param_type', '')
        source = param.get('source', '')
        if source == 'case_table' or param_type in ['direction', 'language']:
            case_fields[param_code] = param_code

    for comp_type in ('device', 'api', 'case', 'reference', 'evaluation'):
        comp_mappings = algo_get_param_mapping(algorithm_type, comp_type) or []
        for mapping in comp_mappings:
            source_param = mapping.get('source_param', '')
            target_key = mapping.get('target_key', source_param)
            source = mapping.get('source', '')
            if source == 'case_table':
                case_fields[target_key] = source_param

    return case_fields
