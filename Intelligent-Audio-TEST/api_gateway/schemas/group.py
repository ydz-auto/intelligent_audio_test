from typing import Optional
from pydantic import Field, AliasChoices

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class GroupItem(APIModel):
    id: str = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    created_at: str = Field(...)
    updated_at: str = Field(...)
    test_case_count: int = Field(...)
    # INT-423/466：资源可见性与归属人（前端徽标 + 路由层 owner 校验）
    visibility: Optional[str] = Field(None)
    created_by_user_id: Optional[int] = Field(None)


class GroupSummaryItem(APIModel):
    """分组列表精简投影（INT-1470：分组 facet / 组头行只需这三项）。

    `GET /groups?fields=summary` 返回此形状。完整 GroupItem 的
    description / algorithm_type 被编辑弹窗复用（回显后原值保存），
    故不能作为默认投影，只能由纯 facet 消费方显式选择。
    """
    id: str = Field(...)
    name: str = Field(...)
    test_case_count: int = Field(...)


class GroupCreateRequest(APIModel):
    id: Optional[str] = Field(None)
    name: str = Field(..., validation_alias=AliasChoices('groupName', 'group_name'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('groupDescription', 'group_description'))
    algorithm_type: Optional[str] = Field(None)
    # INT-566：新建分组可见性（shared/private；None 服务端默认 shared）
    visibility: Optional[str] = Field(None)


class GroupUpdateRequest(APIModel):
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)


class GroupMoveCasesRequest(APIModel):
    case_ids: list[str] = Field(...)
    target_group_id: str = Field(...)


class GroupListData(PaginatedData[GroupItem]):
    pass


class GroupSummaryListData(PaginatedData[GroupSummaryItem]):
    pass


class GroupListQuery(APIModel):
    page: int = Field(1)
    per_page: Optional[int] = Field(None, validation_alias=AliasChoices('per_page', 'perPage', 'page_size', 'pageSize'))
    # INT-1470：列表投影选择。空/full = 完整 GroupItem（默认，兼容编辑弹窗回显）；
    # summary = 仅 id/name/test_case_count（纯 facet 消费方，响应体积最小）
    fields: Optional[str] = Field(None, validation_alias=AliasChoices('fields', 'view'))
    algorithm_type: Optional[str] = Field(None)
    # 分组下用例计数筛选（V9.7.10 对齐）：keyword 模糊匹配用例 id/name/description；
    # dimension_id 按评估维度 config 匹配
    keyword: Optional[str] = Field(None)
    dimension_id: Optional[int] = Field(None, validation_alias=AliasChoices('dimension_id', 'dimensionId'))
    # INT-528：收藏 / 回收站口径（与 TestCaseListQuery 一致，双视图贯通）——
    # favorite=true 仅当前用户收藏；only_deleted=true 仅回收站软删除项
    favorite: Optional[bool] = Field(False)
    only_deleted: Optional[bool] = Field(False)


class GroupDeleteQuery(APIModel):
    cascade: bool = Field(False)
