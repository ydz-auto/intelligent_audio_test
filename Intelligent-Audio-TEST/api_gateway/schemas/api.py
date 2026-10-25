from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

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
    # INT-1177 endpoint 级密钥池非敏感摘要 {count, tails[]}（INT-1230 审计 D6'，
    # 逐端点内嵌；完整密钥零响应）。网关读侧返回原始 dict（无 response_model
    # 过滤），本字段仅作文档一致性，非必需。
    api_keys_summary: Optional[Dict[str, Any]] = Field(None)


class ApiListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    keyword: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    # INT-1799：协议 / 流式性两维等值筛选（前端列表按新列筛选）
    protocol: Optional[str] = Field(None)
    streaming: Optional[bool] = Field(None)

    @field_validator('protocol', mode='before')
    @classmethod
    def _blank_protocol_means_no_filter(cls, value):
        """query 形态：协议筛选器未选中时前端传空串，按「不过滤」处理。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator('streaming', mode='before')
    @classmethod
    def _streaming_query_tristate(cls, value):
        """query 形态三态：空串 / none / all = 不过滤；true|false|1|0 归一为 bool。

        直接交给 pydantic 会因 '' 不是合法 bool 抛验证错（整页列表 500）。
        """
        if isinstance(value, str):
            key = value.strip().lower()
            if key in ('', 'none', 'null', 'all'):
                return None
            if key in ('true', '1', 'yes'):
                return True
            if key in ('false', '0', 'no'):
                return False
        return value


class ApiItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    vendor: Optional[str] = Field(None)
    proxy_type: Optional[str] = Field(None)
    proxy_url: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    meta: Dict[str, Any] = Field(default_factory=dict)
    # INT-1177 密钥池非敏感摘要 {count, tails[]}（读侧顶层直出；完整密钥零响应）。
    # 网关读侧返回原始 dict（无 response_model 过滤），顶层字段直接透出，
    # 本字段仅作文档一致性，非必需。
    api_keys_summary: Optional[Dict[str, Any]] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    default_max_process: Optional[int] = Field(None)
    default_max_timeout: Optional[int] = Field(None)
    default_max_audio_duration: Optional[int] = Field(None)
    health_score: Optional[int] = Field(None)
    endpoints: List[ApiEndpointItem] = Field(default_factory=list)
    output_types: List[str] = Field(default_factory=list)
    # INT-1799：协议 / 流式性正交两维（device_type 已废弃，读侧不再返回）
    protocol: Optional[str] = Field(None)
    streaming: Optional[bool] = Field(None)
    # 【已废弃，P3 删列】仅为契约过渡保留字段声明；响应体不再出现该键
    device_type: Optional[str] = Field(None)
    adapter_class: Optional[str] = Field(None)
    audio_config: Optional[Dict[str, Any]] = Field(None)
    rms_spl_mapping_id: Optional[int] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class ApiListData(PaginatedData[ApiItem]):
    pass


class ApiHealthCheckData(APIModel):
    id: int = Field(...)
    status: str = Field(...)
    health_score: Optional[int] = Field(None)
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
    # INT-1177 endpoint 级密钥池（INT-1230 审计 D1'）：每端点 api_keys 纯字符串
    # 数组，作为该端点轮换池。必补本字段——APIModel extra="ignore" 会丢
    # endpoints[].api_keys 入参。写侧校验在 api_crud_service._validate_endpoint_obj。
    api_keys: Optional[List[str]] = Field(None)


class ApiCreateInput(APIModel):
    name: str = Field(...)
    vendor: Optional[str] = Field(None)
    proxy_type: Optional[str] = Field(None)
    proxy_url: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    meta: Dict[str, Any] = Field(default_factory=dict)
    algorithm_type: Optional[str] = Field(None)
    default_max_process: Optional[int] = Field(None)
    default_max_timeout: Optional[int] = Field(None)
    default_max_audio_duration: Optional[int] = Field(None)
    status: Optional[str] = Field(None)
    endpoints: List[ApiEndpointInput] = Field(default_factory=list)
    output_types: Optional[List[str]] = Field(None)
    # INT-1799：协议 / 流式性（缺省 http / false）。device_type 保留字段仅用于
    # 「显式拒绝」——收到非空值后端 400（B0 裁定：不做兼容窗口、不做双写）。
    protocol: Optional[str] = Field(None)
    streaming: Optional[bool] = Field(None)
    device_type: Optional[str] = Field(None)
    adapter_class: Optional[str] = Field(None)
    audio_config: Optional[Dict[str, Any]] = Field(None)


class ApiUpdateInput(APIModel):
    name: Optional[str] = Field(None)
    vendor: Optional[str] = Field(None)
    proxy_type: Optional[str] = Field(None)
    proxy_url: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    meta: Optional[Dict[str, Any]] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    default_max_process: Optional[int] = Field(None)
    default_max_timeout: Optional[int] = Field(None)
    default_max_audio_duration: Optional[int] = Field(None)
    status: Optional[str] = Field(None)
    endpoints: Optional[List[ApiEndpointInput]] = Field(None)
    output_types: Optional[List[str]] = Field(None)
    # INT-1799：只提交需要改的维度；device_type 保留字段仅用于显式拒绝（400）
    protocol: Optional[str] = Field(None)
    streaming: Optional[bool] = Field(None)
    device_type: Optional[str] = Field(None)
    adapter_class: Optional[str] = Field(None)
    audio_config: Optional[Dict[str, Any]] = Field(None)
    rms_spl_mapping_id: Optional[int] = Field(None)
