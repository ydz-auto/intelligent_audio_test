# -*- coding: utf-8 -*-
"""api_gateway 应用层 —— 实验室读操作服务（CQRS Query Side，INT-493/INT-537 拆分①）

查询侧只读 ReadModel（laboratories 表经仓储直读 + 资源计数经 gRPC 聚合），
不产生副作用。子资源列表端点（devices/playback_devices/test_cases）为路由骨架：
lab_id 过滤随拆分②③ RPC 就绪后联动，未就绪时经读模型退化为无过滤透传。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.repositories.laboratory_repository import (
    LaboratoryRepositoryImpl,
)
from api_gateway.infrastructure.read_models.laboratory_resource_read_model import (
    LaboratoryResourceReadModel,
)
from api_gateway.schemas.laboratory import (
    LaboratoryItem,
    LaboratoryListData,
    LaboratoryListQuery,
    LaboratoryResourcesQuery,
    LaboratorySummaryData,
)

_laboratory_repo = LaboratoryRepositoryImpl()

_DEFAULT_LIST_PER_PAGE = 20
_DEFAULT_RESOURCE_PER_PAGE = 10


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v
              for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


def _counts_dict(lab_id: int) -> dict:
    return LaboratoryResourceReadModel.counts(lab_id)


def _lab_item(lab, counts: dict) -> LaboratoryItem:
    return LaboratoryItem(
        id=lab.id,
        code=lab.code,
        name=lab.name,
        building=lab.building,
        floor=lab.floor,
        room_number=lab.room_number,
        description=lab.description,
        status=lab.status.value,
        device_count=counts.get('device_count', 0),
        playback_device_count=counts.get('playback_device_count', 0),
        test_case_count=counts.get('test_case_count', 0),
    )


class LaboratoryQueryService:
    """实验室读操作服务（list/get/summary/子资源列表）。"""

    @staticmethod
    def list():
        query = _parse_query_params(LaboratoryListQuery)
        page = query.page
        per_page = query.per_page if query.per_page is not None else _DEFAULT_LIST_PER_PAGE
        status = query.status.value if query.status is not None else None

        items, total = _laboratory_repo.list(status=status, page=page, per_page=per_page)
        data_items = [_lab_item(lab, _counts_dict(lab.id)) for lab in items]
        pages = (total + per_page - 1) // per_page if per_page else 1
        return success_response(
            LaboratoryListData(
                items=data_items,
                total=total,
                page=page,
                per_page=per_page,
                pages=pages,
            )
        )

    @staticmethod
    def get(lab_id: int):
        lab = _laboratory_repo.get(lab_id)
        if lab is None:
            return error_response('实验室不存在', code=ErrorCode.NOT_FOUND, http_code=404)
        return success_response(_lab_item(lab, _counts_dict(lab_id)))

    @staticmethod
    def summary(lab_id: int):
        lab = _laboratory_repo.get(lab_id)
        if lab is None:
            return error_response('实验室不存在', code=ErrorCode.NOT_FOUND, http_code=404)
        return success_response(LaboratorySummaryData(**_counts_dict(lab_id)))

    @staticmethod
    def devices(lab_id: int):
        lab = _laboratory_repo.get(lab_id)
        if lab is None:
            return error_response('实验室不存在', code=ErrorCode.NOT_FOUND, http_code=404)
        query = _parse_query_params(LaboratoryResourcesQuery)
        data = LaboratoryResourceReadModel.list_devices(
            lab_id,
            page=query.page,
            per_page=query.per_page if query.per_page is not None else _DEFAULT_RESOURCE_PER_PAGE,
            keyword=query.keyword or '',
        )
        return success_response(data)

    @staticmethod
    def playback_devices(lab_id: int):
        lab = _laboratory_repo.get(lab_id)
        if lab is None:
            return error_response('实验室不存在', code=ErrorCode.NOT_FOUND, http_code=404)
        query = _parse_query_params(LaboratoryResourcesQuery)
        data = LaboratoryResourceReadModel.list_playback_devices(
            lab_id,
            page=query.page,
            per_page=query.per_page if query.per_page is not None else _DEFAULT_RESOURCE_PER_PAGE,
            keyword=query.keyword or '',
        )
        return success_response(data)

    @staticmethod
    def test_cases(lab_id: int):
        lab = _laboratory_repo.get(lab_id)
        if lab is None:
            return error_response('实验室不存在', code=ErrorCode.NOT_FOUND, http_code=404)
        query = _parse_query_params(LaboratoryResourcesQuery)
        data = LaboratoryResourceReadModel.list_test_cases(
            lab_id,
            page=query.page,
            per_page=query.per_page if query.per_page is not None else _DEFAULT_RESOURCE_PER_PAGE,
            algorithm_type=query.algorithm_type or '',
        )
        return success_response(data)
