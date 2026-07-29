from typing import Optional
from pydantic import Field, AliasChoices

from shared.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class GroupItem(APIModel):
    id: str = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias=AliasChoices('algorithmType', 'algorithm_type'))
    created_at: str = Field(..., alias='createdAt', validation_alias='createdAt')
    updated_at: str = Field(..., alias='updatedAt', validation_alias='updatedAt')
    test_case_count: int = Field(..., alias='testCaseCount', validation_alias='testCaseCount')


class GroupCreateRequest(APIModel):
    id: Optional[str] = Field(None, validation_alias=AliasChoices('id', 'id'))
    name: str = Field(..., validation_alias=AliasChoices('name', 'groupName', 'group_name'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('description', 'groupDescription', 'group_description'))
    algorithm_type: Optional[str] = Field(None, validation_alias=AliasChoices('algorithmType', 'algorithm_type'))


class GroupUpdateRequest(APIModel):
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias=AliasChoices('algorithmType', 'algorithm_type'))


class GroupMoveCasesRequest(APIModel):
    case_ids: list[str] = Field(..., alias='caseIds', validation_alias='caseIds')
    target_group_id: str = Field(..., alias='targetGroupId', validation_alias='targetGroupId')


class GroupListData(PaginatedData[GroupItem]):
    pass

