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


class GroupListQuery(APIModel):
    page: int = Field(1)
    per_page: Optional[int] = Field(None, validation_alias=AliasChoices('per_page', 'perPage', 'page_size', 'pageSize'))
    algorithm_type: Optional[str] = Field(None)
    # 分组下用例计数筛选（V9.7.10 对齐）：keyword 模糊匹配用例 id/name/description；
    # type 为用例执行口径（api/e2e，按配置形态派生）；dimension_id 按评估维度 config 匹配
    keyword: Optional[str] = Field(None)
    type: Optional[str] = Field(None, validation_alias=AliasChoices('type', 'test_type', 'testType'))
    dimension_id: Optional[int] = Field(None, validation_alias=AliasChoices('dimension_id', 'dimensionId'))
    # INT-528：收藏 / 回收站口径（与 TestCaseListQuery 一致，双视图贯通）——
    # favorite=true 仅当前用户收藏；only_deleted=true 仅回收站软删除项
    favorite: Optional[bool] = Field(False)
    only_deleted: Optional[bool] = Field(False)


class GroupDeleteQuery(APIModel):
    cascade: bool = Field(False)
