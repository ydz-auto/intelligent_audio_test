from typing import Any, Generic, List, Optional, TypeVar
from pydantic import Field, field_validator

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


class ResourceExportQuery(APIModel):
    """三资源（test-devices / playback-devices / apis）导出查询参数（INT-816）。"""

    ids: Optional[List[int]] = Field(None)
    format: Optional[str] = Field('json')

    @field_validator('ids', mode='before')
    @classmethod
    def _split_comma_ids(cls, value):
        """query 形态兼容：ids=1,2（URLSearchParams CSV 序列化）拆分为列表"""
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(',') if p.strip()]
            return [int(p) for p in parts] if parts else None
        return value


class ResourceImportResult(APIModel):
    """三资源导入计数报告（成功/更新/跳过，对齐设备管理页面设计 §4.5）。"""

    imported_count: int = Field(...)
    updated_count: int = Field(...)
    skipped_count: int = Field(...)
    errors: List[Any] = Field(default_factory=list)
