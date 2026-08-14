# -*- coding: utf-8 -*-
"""数据库操作相关方法。

原 `from task_service.infrastructure.persistence.models import Task, TaskCase, TestCase`
跨服务 PO 直连已改为 gRPC 调用（task_service.TaskDataService / TestCaseConfigService），
避免 shared/ 跨服务 ORM 直连。

依赖通过抽象方法注入，由各 service 的子类提供 ACL 仓储：
- _get_algorithm_acl(): 返回 AlgorithmAclRepository 实例（algorithm_service gRPC 封装）
- _get_task_data_acl(): 返回 TaskDataAclRepository 实例（task_service gRPC 封装）

若子类未实现抽象方法，则延迟 import shared.clients.grpc_clients 作为兜底。
"""
import json


class DbMixin:
    """执行器基类数据库操作方法"""

    def _get_algorithm_acl(self):
        """返回 algorithm_service ACL 仓储 — 由子类实现"""
        raise NotImplementedError("_get_algorithm_acl 必须由子类实现")

    def _get_task_data_acl(self):
        """返回 task_service ACL 仓储 — 由子类实现"""
        raise NotImplementedError("_get_task_data_acl 必须由子类实现")

    def _validate_and_get_data(self, task_id, tc_rel_id):
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads

        task_data_stub = self._get_task_data_acl()._get_stub()

        # 通过 gRPC 查询 TaskCase（按 task_id 拉全量后按 id 过滤，
        # 因为 GetTaskCaseByIds 的 case_ids 按 test_case_id 过滤，非 TaskCase.id）
        tc_rel = None
        try:
            resp = task_data_stub.GetTaskCaseByIds(task_pb.GetTaskCaseByIdsRequest(task_id=int(task_id)))
            if resp.success:
                tcs = _loads(resp.data, []) or []
                tc_rel = next((tc for tc in tcs if tc.get('id') == int(tc_rel_id)), None)
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TaskCase 失败: {e}", task_id=task_id)
        if not tc_rel:
            return {'success': False, 'error': "找不到测试用例关联"}

        # 通过 gRPC 查询 Task
        task = None
        try:
            resp = task_data_stub.GetTaskById(task_pb.GetTaskByIdRequest(task_id=int(task_id)))
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
            tc_stub = self._get_task_data_acl()._get_testcase_stub()
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

        algo_acl = self._get_algorithm_acl()
        case_fields = _get_case_fields(algorithm_type, algo_acl)

        algorithm_params_col = case.get('algorithm_params')

        case_config = case_config.copy() if case_config else {}
        rounds = case_config.get('rounds', [])
        for round_item in rounds:
            if isinstance(round_item, dict):
                rn = round_item.get('round_number', 1)
                round_params = algo_acl.get_round_algo_params(algorithm_params_col, rn)
                if round_params:
                    round_item['algorithm_params'] = round_params

        first_round = rounds[0] if rounds else {}
        case_algorithm_params = algo_acl.normalize_algorithm_params(
            first_round.get('algorithm_params', {}) if isinstance(first_round, dict) else {}
        )

        reference_params_col = case.get('reference_params')
        all_reference_params = []

        if reference_params_col and isinstance(reference_params_col, list):
            for ref_entry in reference_params_col:
                if isinstance(ref_entry, dict):
                    ref_path = ref_entry.get('reference_params_path')
                    if ref_path:
                        round_refs = algo_acl.load_reference_params_file(ref_path)
                        if round_refs:
                            all_reference_params.extend(round_refs)
        else:
            for round_item in rounds:
                if isinstance(round_item, dict):
                    ref_path = round_item.get('reference_params_path')
                    if ref_path:
                        round_refs = algo_acl.load_reference_params_file(ref_path)
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

        result_data['case_fields'] = case_fields

        return {'success': True, 'data': result_data}

    def _update_tc_rel_status(self, tc_rel_id, **kwargs):
        # 通过 ACL 仓储调用 task_service.TaskDataService.UpdateTaskCaseStatus 更新 TaskCase 状态
        task_id = kwargs.pop('task_id', None)
        test_case_id = None
        current_eval = 'pending'
        if task_id is None:
            self._log(
                level='WARNING',
                content=f"_update_tc_rel_status 缺少 task_id，无法通过 gRPC 更新 TaskCase: {tc_rel_id}",
            )
            return

        task_data_acl = self._get_task_data_acl()
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads

        try:
            data_stub = task_data_acl._get_stub()
            resp = data_stub.GetTaskCaseByIds(task_pb.GetTaskCaseByIdsRequest(task_id=int(task_id)))
            if resp.success:
                tcs = _loads(resp.data, []) or []
                tc_rel = next((tc for tc in tcs if tc.get('id') == int(tc_rel_id)), None)
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

        status = kwargs.get('status') or ''
        execution_status = kwargs.get('execution_status') or ''
        error_message = kwargs.get('error_message') or ''
        evaluation_status = kwargs.get('evaluation_status') or ''

        from shared.utils.status_constants import ExecutionStatus as _ES, EvaluationStatus as _EVS
        if execution_status == _ES.COMPLETED and not evaluation_status:
            evaluation_status = _EVS.QUEUED
        elif execution_status == _ES.FAILED and not evaluation_status:
            evaluation_status = _EVS.COMPLETED

        if not status and execution_status:
            from shared.utils.status_utils import derive_task_case_status
            eval_for_derive = evaluation_status or current_eval or _EVS.PENDING
            status = derive_task_case_status(execution_status, eval_for_derive)

        try:
            task_data_acl.update_task_case_status(
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

        try:
            task_data_acl.notify_task_progress(task_id, force=True)
        except Exception as e:
            self._log(
                level='WARNING',
                content=f"_update_tc_rel_status 通知进度失败: {e}",
                task_id=task_id,
            )

    def _save_result(self, task_id, test_case_id, result_data, algo_result, algorithm_type,
                     device_id=None, api_id=None, execution_status='completed', response_time=0,
                     error_message=None, extra_data=None, result_data_path=None):
        """保存测试结果到数据库（通过 ACL 仓储调用 task_service.TaskDataService.SubmitResult）"""
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
            return self._get_task_data_acl().submit_result(task_id, result_payload)
        except Exception as e:
            self._log(
                level='ERROR',
                content=f"[_save_result] gRPC SubmitResult 失败: {e}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            return None


def _get_case_fields(algorithm_type, algo_acl=None):
    """获取算法需要的 case 表字段

    Args:
        algorithm_type: 算法类型
        algo_acl: algorithm_service ACL 仓储（由调用方注入）
    """
    if algo_acl is None:
        from shared.clients.grpc_clients import (
            algo_get_device_params as _get_dev,
            algo_get_api_params as _get_api,
            algo_get_param_mapping as _get_map,
        )
        params = (_get_dev(algorithm_type) or []) + (_get_api(algorithm_type) or [])
        case_fields = {}
        for param in params:
            param_code = param.get('code', '')
            param_type = param.get('param_type', '')
            if param_type in ['direction', 'language']:
                case_fields[param_code] = param_code
        for comp_type in ('device', 'api', 'case', 'reference', 'evaluation'):
            comp_mappings = _get_map(algorithm_type, comp_type) or []
            for mapping in comp_mappings:
                source_param = mapping.get('source_param', '')
                target_key = mapping.get('target_param', source_param)
                source = mapping.get('source', '')
                if source == 'case':
                    case_fields[target_key] = source_param
        return case_fields

    params = (algo_acl.get_device_params(algorithm_type) or []) + (algo_acl.get_api_params(algorithm_type) or [])
    case_fields = {}
    for param in params:
        param_code = param.get('code', '')
        param_type = param.get('param_type', '')
        if param_type in ['direction', 'language']:
            case_fields[param_code] = param_code
    for comp_type in ('device', 'api', 'case', 'reference', 'evaluation'):
        comp_mappings = algo_acl.get_param_mapping(algorithm_type, comp_type) or []
        for mapping in comp_mappings:
            source_param = mapping.get('source_param', '')
            target_key = mapping.get('target_param', source_param)
            source = mapping.get('source', '')
            if source == 'case':
                case_fields[target_key] = source_param
    return case_fields
