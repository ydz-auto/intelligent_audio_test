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


class GroupCreateRequest(APIModel):
    id: Optional[str] = Field(None)
    name: str = Field(..., validation_alias=AliasChoices('groupName', 'group_name'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('groupDescription', 'group_description'))
    algorithm_type: Optional[str] = Field(None)


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
    test_type: Optional[str] = Field(None, validation_alias=AliasChoices('type', 'test_type', 'testType'))


class GroupDeleteQuery(APIModel):
    cascade: bool = Field(False)
