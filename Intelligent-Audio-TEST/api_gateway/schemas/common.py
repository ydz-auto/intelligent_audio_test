from typing import Generic, List, Optional, TypeVar
from pydantic import Field

from api_gateway.schemas.base import APIModel

T = TypeVar("T")


class IdData(APIModel):
    id: int = Field(...)


class StringIdData(APIModel):
    id: str = Field(...)


class StatusData(APIModel):
    id: int = Field(...)
    status: str = Field(...)


class TaskStatusData(APIModel):
    task_id: str = Field(...)
    status: str = Field(...)


class DeletedCountData(APIModel):
    deleted_count: int = Field(...)


class PaginatedData(APIModel, Generic[T]):
    items: List[T] = Field(...)
    total: int = Field(...)
    page: int = Field(...)
    per_page: int = Field(...)
    pages: int = Field(...)


class CountData(APIModel):
    count: int = Field(...)
    new_count: Optional[int] = Field(None)
