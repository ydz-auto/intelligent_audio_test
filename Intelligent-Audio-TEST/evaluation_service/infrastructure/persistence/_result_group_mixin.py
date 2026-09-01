# -*- coding: utf-8 -*-
"""分组维度结果处理与算法结果快照混入

负责一组维度的评估结果处理流程编排，以及
algorithm_results 扁平快照的预提取与写回。
"""
import json

from shared.models.database import get_db_session
from shared.utils.status_constants import ExecutionStatus
from shared.utils.json_utils import deserialize_algorithm_result
from shared.models.common_enums import TestType
from evaluation_service.infrastructure.acl import task_acl_repository


class GroupResultMixin:
    """分组维度处理与 algorithm_results 快照方法"""

    def mark_test_result_completed(self, result_id):
        """
        标记 TestResult 完成（用于没有评估维度的场景）

        P1.4: 通过 gRPC 调 task_service.UpdateTestResultStatus
        """
        ok = task_acl_repository.update_test_result_status(
            result_id=result_id,
            execution_status=ExecutionStatus.COMPLETED,
        )
        self._log(
            level='DEBUG' if ok else 'ERROR',
            category='database',
            content=f"标记 TestResult {result_id} 为完成状态: {'成功' if ok else '失败'}"
        )

        # 预提取 algorithm_results 快照（无评估维度场景）
        if ok:
            try:
                tr = task_acl_repository.get_test_result_by_id(result_id)
                if tr:
                    self._build_and_store_algorithm_results(
                        result_id,
                        getattr(tr, 'task_id', None),
                        getattr(tr, 'test_case_id', None)
                    )
            except Exception as e:
                self._log(
                    level='WARNING',
                    category='execution',
                    content=f"预提取 algorithm_results 失败: {e}",
                )

    def process_group_dimension_results(self, resp_data, group_items, task_id, test_case_id, result_id, api_request_body, test_type=TestType.API.value):
        """
        处理一组维度的评估结果

        P1.4: TestResult 通过 gRPC 读取（task_service）；TestResultDimension 本地写（自有 PO）

        Args:
            resp_data: API响应数据
            group_items: 维度组项列表 [(dim_data, dimension_result_id), ...]
            task_id: 任务ID
            test_case_id: 用例ID
            result_id: 结果ID
            api_request_body: API请求体
            test_type: 测试类型 (api 或 e2e)
        """
        # 使用单个数据库会话处理整组维度的更新（仅 TestResultDimension）
        local_db_session = get_db_session()
        try:
            # 获取api_id和device_id（P1.4: 通过 gRPC 读 TestResult）
            api_id = None
            device_id = None
            if result_id:
                test_result = task_acl_repository.get_test_result_by_id(result_id)
                if test_result:
                    api_id = test_result.api_id
                    device_id = test_result.device_id
                    test_case_id = test_case_id or test_result.test_case_id

            for dim_data, dimension_result_id in group_items:
                dim_id = dim_data['id']
                dim_name = dim_data['name']

                # 解析结果并打分
                raw_value, score = self.parse_dimension_result(resp_data, dim_data)

                # 记录维度评估详细结果到日志
                self._log(
                    level='INFO',
                    category='execution',
                    content=f"维度 {dim_name} 评估完成: "
                           f"用例ID: {test_case_id}, "
                           f"设备ID: {device_id}, "
                           f"API ID: {api_id}, "
                           f"原始值: {raw_value}, "
                           f"维度分值: {score}, "
                           f"响应数据: {json.dumps(resp_data, ensure_ascii=False)}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )

                # 更新维度评估结果，传入session避免重复创建
                self.update_dimension_result_completed(dimension_result_id, raw_value, score, task_id=task_id, test_case_id=test_case_id, api_raw_response=resp_data, api_request_body=api_request_body, session=local_db_session)

            # 循环结束后统一提交
            local_db_session.commit()

            # 预提取 algorithm_results 快照，存入 result_data['algorithm_results']
            self._build_and_store_algorithm_results(
                result_id, task_id, test_case_id, test_type
            )

            # 检查是否所有维度都已完成评估，如果是，更新TaskCase状态
            if result_id and test_case_id:
                if self.check_all_dimensions_completed(result_id, task_id):
                    # Multi-round: aggregate before final status update
                    if self.is_multi_round_result(result_id):
                        self.aggregate_round_results(result_id, task_id, test_case_id)
                    self.update_task_case_status(result_id, True, task_id, test_case_id, test_type)
        finally:
            local_db_session.close()

    def _build_and_store_algorithm_results(self, result_id, task_id, test_case_id, test_type=TestType.API.value):
        """预提取 algorithm_results 扁平列表并存入 result_data['algorithm_results']。

        在评估完成后调用，报告页和详情页可直接读取，无需重复提取。
        """
        if not result_id:
            return
        try:
            test_result = task_acl_repository.get_test_result_by_id(result_id)
            if not test_result:
                return

            # 获取 algorithm_type 和 resource
            algorithm_type = ''
            # algorithm_type 通过 TestResult 获取（若 DTO 不含则从 Task/TestCase 推断）
            algo_result = deserialize_algorithm_result(test_result.algorithm_result)

            task = task_acl_repository.get_task_by_id(task_id) if task_id else None

            # 获取 resource name
            device_id = test_result.device_id
            api_id = test_result.api_id
            # 通过 gRPC 获取设备/API 名称
            resource = f'result_{result_id}'
            try:
                resource = self._resolve_resource_name(result_id, device_id, api_id)
            except Exception:
                pass

            # 加载 algo_res 和 result_data
            from shared.utils.result_data_store import load_full_result_data, write_result_data_file, split_result_data
            result_data = load_full_result_data(test_result.result_data, test_result.result_data_path)
            if not isinstance(result_data, dict):
                result_data = {}

            if not (algo_result or result_data):
                return

            # 查询 dim_result_rows（含 api_raw_response，本地 DB）
            dim_result_rows = self._load_dim_result_rows(result_id)

            # 查询 aux_params_map（通过 gRPC 调 algorithm_service）
            aux_params_map = self._load_aux_params_map(dim_result_rows)

            # 查询 output_fields
            output_fields = self._load_output_fields(algorithm_type)

            # 调用公共方法构建 algorithm_results
            from report_service.application.services.report_data_builder import ReportDataBuilder
            algorithm_results = ReportDataBuilder.build_algorithm_results_for_result(
                test_result, resource, algo_result, result_data,
                aux_params_map, dim_result_rows, output_fields, algorithm_type
            )

            # 存入 result_data['algorithm_results']
            result_data['algorithm_results'] = algorithm_results if algorithm_results else None

            # 写回：大字段存文件，轻量部分存 DB
            lightweight, has_heavy = split_result_data(result_data)
            result_data_path = None
            if has_heavy:
                device_sn = str(api_id or result_id)
                result_data_path = write_result_data_file(task_id, test_case_id, device_sn, result_data)

            task_acl_repository.update_test_result_data(
                result_id, lightweight, result_data_path
            )

        except Exception as e:
            self._log(
                level='WARNING',
                category='execution',
                content=f"预提取 algorithm_results 失败: {e}",
                task_id=task_id, test_case_id=test_case_id
            )

    @staticmethod
    def _resolve_resource_name(result_id, device_id, api_id):
        """通过 gRPC 解析设备/API 名称作为 resource（失败时回退 result_id 形式）"""
        if device_id:
            from shared.clients.grpc_clients import get_device_config_service_stub
            from shared.proto import device_service_pb2 as dev_pb
            from shared.utils.grpc_json import loads as _grpc_loads
            dev_stub = get_device_config_service_stub()
            dev_resp = dev_stub.GetDevice(dev_pb.GetDeviceRequest(device_id=device_id))
            if dev_resp.success:
                dev_data = _grpc_loads(dev_resp.data, {})
                return dev_data.get('name') or f'device_{device_id}'
        elif api_id:
            from shared.clients.grpc_clients import get_api_test_service_stub
            from shared.proto import api_test_service_pb2 as api_pb
            from shared.utils.grpc_json import loads as _grpc_loads
            api_stub = get_api_test_service_stub()
            api_resp = api_stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=api_id))
            if api_resp.success:
                api_data = _grpc_loads(api_resp.data, {})
                return api_data.get('name') or f'api_{api_id}'
        return f'result_{result_id}'

    @staticmethod
    def _load_dim_result_rows(result_id):
        """查询该结果的维度评估记录（含 api_raw_response，本地 DB）"""
        local_db_session = get_db_session()
        try:
            from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
            return local_db_session.query(
                TestResultDimension
            ).filter(TestResultDimension.test_result_id == result_id).all()
        finally:
            local_db_session.close()

    @staticmethod
    def _load_aux_params_map(dim_result_rows):
        """查询 aux 参数映射（通过 gRPC 调 algorithm_service，仅收集可见的 output/aux 参数）"""
        all_dim_ids = set(dr.dimension_id for dr in dim_result_rows if dr.dimension_id)
        aux_params_map = {}
        if not all_dim_ids:
            return aux_params_map
        try:
            from evaluation_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
            _algo_repo = AlgorithmRepository()
            for dim_id in all_dim_ids:
                params = _algo_repo.get_dimension_params(dim_id)
                if not params:
                    continue
                for p in params:
                    if not isinstance(p, dict):
                        continue
                    if p.get('param_direction') != 'output':
                        continue
                    if p.get('output_role') != 'aux':
                        continue
                    if not p.get('visible_in_report'):
                        continue
                    dim_name = p.get('dimension_name') or ''
                    if dim_id not in aux_params_map:
                        aux_params_map[dim_id] = []
                    aux_params_map[dim_id].append({'param': p, 'dimension_name': dim_name})
        except Exception:
            pass
        return aux_params_map

    @staticmethod
    def _load_output_fields(algorithm_type):
        """查询算法输出字段（通过 gRPC 调 algorithm_service）"""
        output_fields = []
        if algorithm_type:
            try:
                from evaluation_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
                _algo_repo = AlgorithmRepository()
                output_fields = _algo_repo.get_output_fields(algorithm_type) or []
            except Exception:
                pass
        return output_fields
