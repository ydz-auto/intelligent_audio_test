from typing import Any, Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class ApiEndpointItem(APIModel):
    id: Optional[str] = Field(None, alias='id', validation_alias='id')
    endpoint: str = Field(..., alias='endpoint', validation_alias='endpoint')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    max_process: Optional[int] = Field(None, alias='maxProcess', validation_alias='maxProcess')
    max_timeout: Optional[int] = Field(None, alias='maxTimeout', validation_alias='maxTimeout')
    max_audio_duration: Optional[int] = Field(None, alias='maxAudioDuration', validation_alias='maxAudioDuration')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    health_score: Optional[int] = Field(None, alias='healthScore', validation_alias='healthScore')
    priority: Optional[int] = Field(None, alias='priority', validation_alias='priority')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')


class ApiItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    vendor: Optional[str] = Field(None, alias='vendor', validation_alias='vendor')
    api_url: str = Field(..., alias='apiUrl', validation_alias='apiUrl')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    meta: Dict[str, Any] = Field(default_factory=dict, alias='meta', validation_alias='meta')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    default_max_process: Optional[int] = Field(None, alias='defaultMaxProcess', validation_alias='defaultMaxProcess')
    default_max_timeout: Optional[int] = Field(None, alias='defaultMaxTimeout', validation_alias='defaultMaxTimeout')
    default_max_audio_duration: Optional[int] = Field(None, alias='defaultMaxAudioDuration', validation_alias='defaultMaxAudioDuration')
    health_score: Optional[int] = Field(None, alias='healthScore', validation_alias='healthScore')
    endpoints: List[ApiEndpointItem] = Field(default_factory=list, alias='endpoints', validation_alias='endpoints')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class ApiListData(PaginatedData[ApiItem]):
    pass


class ApiHealthCheckData(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    status: str = Field(..., alias='status', validation_alias='status')
    health_score: Optional[int] = Field(None, alias='healthScore', validation_alias='healthScore')
    api_url_status: Optional[str] = Field(None, alias='apiUrlStatus', validation_alias='apiUrlStatus')
    endpoints_status: Optional[str] = Field(None, alias='endpointsStatus', validation_alias='endpointsStatus')
    status_code: Optional[int] = Field(None, alias='statusCode', validation_alias='statusCode')
    response_time: Optional[str] = Field(None, alias='responseTime', validation_alias='responseTime')
    error: Optional[str] = Field(None, alias='error', validation_alias='error')
    warning: Optional[str] = Field(None, alias='warning', validation_alias='warning')


class ApiEndpointInput(APIModel):
    endpoint: Optional[str] = Field(None, alias='endpoint', validation_alias='endpoint')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    max_process: Optional[int] = Field(None, alias='maxProcess', validation_alias='maxProcess')
    max_timeout: Optional[int] = Field(None, alias='maxTimeout', validation_alias='maxTimeout')
    max_audio_duration: Optional[int] = Field(None, alias='maxAudioDuration', validation_alias='maxAudioDuration')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    priority: Optional[int] = Field(None, alias='priority', validation_alias='priority')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')


class ApiCreateInput(APIModel):
    name: str = Field(..., alias='name', validation_alias='name')
    vendor: Optional[str] = Field(None, alias='vendor', validation_alias='vendor')
    api_url: Optional[str] = Field(None, alias='apiUrl', validation_alias='apiUrl')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    meta: Dict[str, Any] = Field(default_factory=dict, alias='meta', validation_alias='meta')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    default_max_process: Optional[int] = Field(None, alias='defaultMaxProcess', validation_alias='defaultMaxProcess')
    default_max_timeout: Optional[int] = Field(None, alias='defaultMaxTimeout', validation_alias='defaultMaxTimeout')
    default_max_audio_duration: Optional[int] = Field(None, alias='defaultMaxAudioDuration', validation_alias='defaultMaxAudioDuration')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    endpoints: List[ApiEndpointInput] = Field(default_factory=list, alias='endpoints', validation_alias='endpoints')


class ApiUpdateInput(APIModel):
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    vendor: Optional[str] = Field(None, alias='vendor', validation_alias='vendor')
    api_url: Optional[str] = Field(None, alias='apiUrl', validation_alias='apiUrl')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    meta: Optional[Dict[str, Any]] = Field(None, alias='meta', validation_alias='meta')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    default_max_process: Optional[int] = Field(None, alias='defaultMaxProcess', validation_alias='defaultMaxProcess')
    default_max_timeout: Optional[int] = Field(None, alias='defaultMaxTimeout', validation_alias='defaultMaxTimeout')
    default_max_audio_duration: Optional[int] = Field(None, alias='defaultMaxAudioDuration', validation_alias='defaultMaxAudioDuration')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    endpoints: Optional[List[ApiEndpointInput]] = Field(None, alias='endpoints', validation_alias='endpoints')

