from typing import Generic, List, Optional, TypeVar
from pydantic import Field

from api_gateway.schemas.base import APIModel

T = TypeVar("T")


class IdData(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')


class StringIdData(APIModel):
    id: str = Field(..., alias='id', validation_alias='id')


class StatusData(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    status: str = Field(..., alias='status', validation_alias='status')


class TaskStatusData(APIModel):
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    status: str = Field(..., alias='status', validation_alias='status')


class DeletedCountData(APIModel):
    deleted_count: int = Field(..., alias='deletedCount', validation_alias='deletedCount')


class PaginatedData(APIModel, Generic[T]):
    items: List[T] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')
    page: int = Field(..., alias='page', validation_alias='page')
    per_page: int = Field(..., alias='perPage', validation_alias='perPage')
    pages: int = Field(..., alias='pages', validation_alias='pages')


class CountData(APIModel):
    count: int = Field(..., alias='count', validation_alias='count')
    new_count: Optional[int] = Field(None, alias='newCount', validation_alias='newCount')

