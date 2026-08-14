from typing import Any, Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class ApiEndpointItem(APIModel):
    id: Optional[str] = Field(None)
    endpoint: str = Field(...)
    name: Optional[str] = Field(None)
    max_process: Optional[int] = Field(None)
    max_timeout: Optional[int] = Field(None)
    max_audio_duration: Optional[int] = Field(None)
    status: Optional[str] = Field(None)
    health_score: Optional[int] = Field(None)
    priority: Optional[int] = Field(None)
    description: Optional[str] = Field(None)


class ApiItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    vendor: Optional[str] = Field(None)
    api_url: str = Field(...)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    meta: Dict[str, Any] = Field(default_factory=dict)
    algorithm_type: Optional[str] = Field(None)
    default_max_process: Optional[int] = Field(None)
    default_max_timeout: Optional[int] = Field(None)
    default_max_audio_duration: Optional[int] = Field(None)
    health_score: Optional[int] = Field(None)
    endpoints: List[ApiEndpointItem] = Field(default_factory=list)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class ApiListData(PaginatedData[ApiItem]):
    pass


class ApiHealthCheckData(APIModel):
    id: int = Field(...)
    status: str = Field(...)
    health_score: Optional[int] = Field(None)
    api_url_status: Optional[str] = Field(None)
    endpoints_status: Optional[str] = Field(None)
    status_code: Optional[int] = Field(None)
    response_time: Optional[str] = Field(None)
    error: Optional[str] = Field(None)
    warning: Optional[str] = Field(None)


class ApiEndpointInput(APIModel):
    endpoint: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    max_process: Optional[int] = Field(None)
    max_timeout: Optional[int] = Field(None)
    max_audio_duration: Optional[int] = Field(None)
    status: Optional[str] = Field(None)
    priority: Optional[int] = Field(None)
    description: Optional[str] = Field(None)


class ApiCreateInput(APIModel):
    name: str = Field(...)
    vendor: Optional[str] = Field(None)
    api_url: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    meta: Dict[str, Any] = Field(default_factory=dict)
    algorithm_type: Optional[str] = Field(None)
    default_max_process: Optional[int] = Field(None)
    default_max_timeout: Optional[int] = Field(None)
    default_max_audio_duration: Optional[int] = Field(None)
    status: Optional[str] = Field(None)
    endpoints: List[ApiEndpointInput] = Field(default_factory=list)


class ApiUpdateInput(APIModel):
    name: Optional[str] = Field(None)
    vendor: Optional[str] = Field(None)
    api_url: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    meta: Optional[Dict[str, Any]] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    default_max_process: Optional[int] = Field(None)
    default_max_timeout: Optional[int] = Field(None)
    default_max_audio_duration: Optional[int] = Field(None)
    status: Optional[str] = Field(None)
    endpoints: Optional[List[ApiEndpointInput]] = Field(None)
