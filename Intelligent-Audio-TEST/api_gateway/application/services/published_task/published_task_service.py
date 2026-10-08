import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.grpc_proxies import published_task_config_service
from api_gateway.schemas.common import IdData, StatusData
from api_gateway.schemas.published_task import (
    PublishedTaskCreateRequest,
    PublishedTaskVersionCreateRequest,
    PublishedTaskUpdateRequest,
    PublishedTaskListData,
    PublishedTaskItem,
    PublishedTaskDetailData,
    PublishedTaskExecutionItem,
    PublishedTaskExecuteData,
)

logger = logging.getLogger(__name__)

_pt_acl = published_task_config_service


def _parse_query_params():
    """查询参数解析（Flask 兼容 request.args → 扁平 dict）"""
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return params


class PublishedTaskService:
    """已发布任务网关服务（CQRS）。

    按 DDD 原则，网关不直接操作 DB，通过 gRPC 调用 task_service
    PublishedTaskConfigService（由 grpc_proxies 代理转发）。
    """

    # ---------- 发布 ----------

    @staticmethod
    def publish():
        try:
            req = PublishedTaskCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS, http_code=400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)
        result = _pt_acl.publish(data_dict)

        if not result.get('success'):
            return error_response(
                result.get('message', '发布失败'),
                code=result.get('code', ErrorCode.OPERATION_FAILED),
                http_code=400,
            )

        data = result.get('data') or {}
        return success_response(IdData(id=data.get('id')), result.get('message', '已发布任务创建成功'), http_code=201)

    # ---------- 查询 ----------

    @staticmethod
    def get_all():
        params = _parse_query_params()
        page = max(int(params.get('page', 1)), 1)
        per_page = min(max(int(params.get('perPage', params.get('per_page', 10))), 1), 100)
        status = params.get('status', '')
        keyword = params.get('keyword', '').strip()
        task_type = params.get('type', '')
        start_date = params.get('start_date')
        end_date = params.get('end_date')

        result = _pt_acl.get_list(
            page=page, per_page=per_page, status=status, keyword=keyword,
            task_type=task_type, start_date=start_date or '', end_date=end_date or '',
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询已发布任务失败'), code=result.get('code', 500))

        raw = result.get('data') or {}
        items = [
            PublishedTaskItem(
                id=item.get('id'),
                source_task_id=item.get('source_task_id'),
                name=item.get('name'),
                description=item.get('description'),
                type=item.get('type'),
                status=item.get('status'),
                version=item.get('version'),
                is_current=item.get('is_current'),
                version_count=item.get('version_count'),
                published_by=item.get('published_by'),
                published_at=item.get('published_at'),
                archived_at=item.get('archived_at'),
                created_at=item.get('created_at'),
            )
            for item in raw.get('items', [])
        ]
        return success_response(
            PublishedTaskListData(
                items=items,
                total=raw.get('total', 0),
                page=raw.get('page', page),
                per_page=raw.get('per_page', per_page),
                pages=raw.get('pages', 0),
            )
        )

    @staticmethod
    def get_one(published_task_id):
        result = _pt_acl.get_detail(published_task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 201:
                return error_response(result.get('message', '已发布任务不存在'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询已发布任务失败'), code=code)

        d = result.get('data') or {}
        versions = [
            PublishedTaskItem(
                id=v.get('id'),
                source_task_id=v.get('source_task_id'),
                name=v.get('name'),
                description=v.get('description'),
                type=v.get('type'),
                status=v.get('status'),
                version=v.get('version'),
                is_current=v.get('is_current'),
                version_count=v.get('version_count'),
                published_by=v.get('published_by'),
                published_at=v.get('published_at'),
                archived_at=v.get('archived_at'),
                created_at=v.get('created_at'),
            )
            for v in d.get('versions', [])
        ]
        execution_history = [
            PublishedTaskExecutionItem(
                task_id=e.get('task_id'),
                task_name=e.get('task_name'),
                version=e.get('version'),
                status=e.get('status'),
                total_cases=e.get('total_cases', 0),
                completed_cases=e.get('completed_cases', 0),
                created_at=e.get('created_at'),
                completed_at=e.get('completed_at'),
            )
            for e in d.get('execution_history', [])
        ]
        return success_response(
            PublishedTaskDetailData(
                id=d.get('id'),
                task_group_id=d.get('task_group_id'),
                source_task_id=d.get('source_task_id'),
                name=d.get('name'),
                description=d.get('description'),
                type=d.get('type'),
                status=d.get('status'),
                version=d.get('version'),
                is_current=d.get('is_current'),
                snapshot_config=d.get('snapshot_config') or {},
                publish_reason=d.get('publish_reason'),
                published_by=d.get('published_by'),
                published_at=d.get('published_at'),
                archived_by=d.get('archived_by'),
                archived_at=d.get('archived_at'),
                source_task_name=d.get('source_task_name'),
                source_task_status=d.get('source_task_status'),
                source_task_total_cases=d.get('source_task_total_cases'),
                source_task_completed_cases=d.get('source_task_completed_cases'),
                report_snapshot=d.get('report_snapshot'),
                has_report_snapshot=d.get('has_report_snapshot', False),
                versions=versions,
                execution_history=execution_history,
            )
        )

    # ---------- 执行 ----------

    @staticmethod
    def execute(published_task_id):
        result = _pt_acl.execute(published_task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 201:
                return error_response(result.get('message', '已发布任务不存在'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '创建日常任务失败'), code=code, http_code=400 if code == 203 else 500)

        data = result.get('data') or {}
        return success_response(
            PublishedTaskExecuteData(
                task_id=data.get('task_id'),
                task_name=data.get('task_name'),
                published_task_id=data.get('published_task_id'),
                published_task_version=data.get('published_task_version'),
            ),
            result.get('message', '日常任务创建成功，可前往任务列表执行'),
        )

    # ---------- 新版本 ----------

    @staticmethod
    def create_version(published_task_id):
        try:
            req = PublishedTaskVersionCreateRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS, http_code=400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)
        result = _pt_acl.create_version(published_task_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 201:
                return error_response(result.get('message', '已发布任务不存在'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '创建新版本失败'), code=code, http_code=400 if code in (100, 203) else 500)

        data = result.get('data') or {}
        return success_response(IdData(id=data.get('id')), result.get('message', '新版本创建成功'), http_code=201)

    # ---------- 归档 ----------

    @staticmethod
    def archive(published_task_id):
        result = _pt_acl.archive(published_task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 201:
                return error_response(result.get('message', '已发布任务不存在'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '归档失败'), code=code)

        data = result.get('data') or {}
        return success_response(
            StatusData(id=data.get('id'), status=data.get('status')),
            result.get('message', '任务已归档'),
        )

    # ---------- 重命名 ----------

    @staticmethod
    def update_name(published_task_id):
        try:
            req = PublishedTaskUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS, http_code=400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)
        result = _pt_acl.rename(published_task_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 201:
                return error_response(result.get('message', '已发布任务不存在'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '重命名失败'), code=code, http_code=400 if code == 101 else 500)

        data = result.get('data') or {}
        return success_response(
            IdData(id=data.get('id')), result.get('message', '任务名称已更新')
        )
