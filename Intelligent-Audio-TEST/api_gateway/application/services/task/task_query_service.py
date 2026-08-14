import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, convert_keys_to_camel
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl
from shared.utils.grpc_json import loads as _loads
from api_gateway.schemas.task import (
    TaskListData,
    TaskListItem,
    TaskDetailData,
    TaskProgressData,
    TaskProgressCurrentCase,
    TaskStatsData,
    TaskCaseBrief,
    TaskDeviceBrief,
    TaskApiBrief,
    TaskReportItem,
    TaskReportsData,
)

logger = logging.getLogger(__name__)

_task_acl = TaskConfigAclRepositoryImpl()


class TaskQueryService:
    """任务查询读侧 Service（CQRS Query Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    """

    # 获取所有任务，支持分页和过滤
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status')
        type_ = request.args.get('type')
        algorithm_type = request.args.get('algorithm_type')
        search = request.args.get('search')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        result = _task_acl.list_tasks(
            page=page,
            per_page=per_page,
            status=status,
            task_type=type_,
            algorithm_type=algorithm_type,
            search=search,
            start_date=start_date,
            end_date=end_date,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        raw = result.get('data') or {}
        items = []
        for item in raw.get('items', []):
            report_info = item.get('reports', {})
            devices = [
                TaskDeviceBrief(**d) for d in item.get('devices', [])
            ]
            apis = [
                TaskApiBrief(**a) for a in item.get('apis', [])
            ]
            items.append(
                TaskListItem(
                    id=item.get('id'),
                    name=item.get('name'),
                    description=item.get('description'),
                    status=item.get('status'),
                    type=item.get('type'),
                    config=convert_keys_to_camel(item.get('config')) if item.get('config') else {},
                    algorithm_type=item.get('algorithm_type'),
                    algorithm_params=convert_keys_to_camel(item.get('algorithm_params')) if item.get('algorithm_params') else None,
                    started_at=item.get('started_at'),
                    completed_at=item.get('completed_at'),
                    total_cases=item.get('total_cases'),
                    case_count=item.get('total_cases'),
                    device_count=item.get('device_count', len(devices)),
                    completed_cases=item.get('completed_cases'),
                    failed_cases=item.get('failed_cases'),
                    tags=item.get('tags', []),
                    created_at=item.get('created_at'),
                    updated_at=item.get('updated_at'),
                    reports=TaskReportsData(
                        count=report_info.get('count', 0),
                        reports=[
                            TaskReportItem(
                                id=r.get('id'),
                                name=r.get('name'),
                                status=r.get('status'),
                                type=r.get('type'),
                                created_at=r.get('created_at'),
                            )
                            for r in report_info.get('reports', [])
                        ],
                    ) if report_info else TaskReportsData(count=0, reports=[]),
                    devices=devices,
                    apis=apis,
                )
            )

        return success_response(
            TaskListData(
                items=items,
                total=raw.get('total', 0),
                page=raw.get('page', page),
                per_page=raw.get('per_page', per_page),
                pages=raw.get('pages', 0),
            )
        )

    # 获取单个任务详情
    @staticmethod
    def get_one(task_id):
        result = _task_acl.get_task_detail(task_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询失败'))

        item = result.get('data') or {}
        cases = [
            TaskCaseBrief(
                case_id=c.get('case_id'),
                name=c.get('name'),
                status=c.get('status'),
                execution_status=c.get('execution_status'),
                evaluation_status=c.get('evaluation_status'),
                started_at=c.get('started_at'),
                completed_at=c.get('completed_at'),
                duration=c.get('duration'),
                error_message=c.get('error_message'),
            )
            for c in item.get('cases', [])
        ]
        devices = [
            TaskDeviceBrief(**d) for d in item.get('devices', [])
        ]
        apis = [
            TaskApiBrief(**a) for a in item.get('apis', [])
        ]

        return success_response(
            TaskDetailData(
                id=item.get('id'),
                name=item.get('name'),
                description=item.get('description'),
                status=item.get('status'),
                type=item.get('type'),
                config=convert_keys_to_camel(item.get('config')) if item.get('config') else {},
                algorithm_type=item.get('algorithm_type'),
                algorithm_params=convert_keys_to_camel(item.get('algorithm_params')) if item.get('algorithm_params') else None,
                started_at=item.get('started_at'),
                completed_at=item.get('completed_at'),
                expected_total_time=item.get('expected_total_time'),
                expected_complete_time=item.get('expected_complete_time'),
                used_time=item.get('used_time'),
                total_cases=item.get('total_cases'),
                case_count=item.get('total_cases'),
                device_count=len(devices),
                completed_cases=item.get('completed_cases'),
                failed_cases=item.get('failed_cases'),
                tags=item.get('tags', []),
                cases=cases,
                devices=devices,
                apis=apis,
                created_at=item.get('created_at'),
                updated_at=item.get('updated_at'),
            )
        )

    # 获取单个用例的执行详情
    @staticmethod
    def get_case_detail(task_id, case_id):
        result = _task_acl.get_case_detail(task_id, case_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到该任务关联的用例", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询失败'))

        data = result.get('data') or {}

        # 网关侧补充构建 reference_params + audios_list（通过 gRPC 调用 report_service）
        reference_params = data.get('reference_params', {})
        audios_list = data.get('audio_list', [])
        try:
            from api_gateway.infrastructure.grpc_proxies import report_config_service
            from shared.proto import report_service_pb2 as report_pb
            from api_gateway.infrastructure.acl import TestCaseConfigAclRepositoryImpl
            from shared.utils.grpc_json import dumps as _dumps

            _testcase_acl = TestCaseConfigAclRepositoryImpl()
            tc_res = _testcase_acl.get_testcase_detail(case_id)
            if tc_res.get('success'):
                case_info_dict = tc_res.get('data') or {}
                if case_info_dict:
                    test_type = data.get('algorithm_type') or 'api'
                    stub = report_config_service.stub
                    resp = stub.BuildReferenceParams(report_pb.BuildReferenceParamsRequest(
                        data=_dumps({
                            'case_info': case_info_dict,
                            'case_results': data.get('_raw_results', []),
                            'test_type': test_type,
                        })
                    ))
                    if resp.success:
                        payload = _loads(resp.data, {}) or {}
                        if payload.get('reference_params'):
                            reference_params = payload['reference_params']
                        if payload.get('audios_list'):
                            audios_list = payload['audios_list']
        except Exception as e:
            logger.warning(f"构建 reference_params/audios_list 失败: {e}")

        response_data = {
            "task_id": data.get('task_id', task_id),
            "case_id": data.get('case_id', case_id),
            "case_name": data.get('case_name', '未知用例'),
            "status": data.get('status'),
            "execution_status": data.get('execution_status'),
            "evaluation_status": data.get('evaluation_status'),
            "started_at": data.get('started_at'),
            "completed_at": data.get('completed_at'),
            "duration": data.get('duration'),
            "error_message": data.get('error_message'),
            "audio_list": audios_list,
            "reference_params": reference_params,
            "algorithm_results": data.get('algorithm_results', []),
            "algorithm_type": data.get('algorithm_type', ''),
            "devices": data.get('devices', []),
            "metric_configs": data.get('metric_configs', []),
            "field_mapping": data.get('field_mapping', {'result': [], 'reference': []}),
            "result_audios": data.get('result_audios', {}),
        }

        return success_response(response_data)

    # 获取单个用例的执行结果
    @staticmethod
    def get_case_results(task_id, case_id):
        result = _task_acl.get_case_results(task_id, case_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到该任务关联的用例", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    # 获取任务实时进度
    @staticmethod
    def get_progress(task_id):
        result = _task_acl.get_task_progress(task_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询失败'))

        item = result.get('data') or {}
        current_case_data = None
        cc = item.get('current_case')
        if cc:
            current_case_data = TaskProgressCurrentCase(
                case_id=cc.get('case_id'),
                name=cc.get('name'),
                step=cc.get('step', 'running'),
                started_at=cc.get('started_at'),
            )

        return success_response(
            TaskProgressData(
                task_id=str(item.get('task_id', task_id)),
                status=item.get('status'),
                total_cases=item.get('total_cases'),
                completed_cases=item.get('completed_cases'),
                failed_cases=item.get('failed_cases'),
                progress=item.get('progress', 0),
                current_case=current_case_data,
                updated_at=item.get('updated_at'),
            )
        )

    # 获取任务统计信息
    @staticmethod
    def stats(task_id):
        result = _task_acl.get_task_stats(task_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询失败'))

        return success_response(TaskStatsData(**(result.get('data') or {})))
