# -*- coding: utf-8 -*-
"""API 聚合根实体 — 描述被测 API 配置的聚合根、枚举与快照，纯逻辑，无 IO 依赖。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from shared.models.common_enums import OutputType


class HTTPMethod(str, Enum):
    """HTTP 请求方法枚举"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class APIStatus(str, Enum):
    """API 状态枚举"""

    active = "active"
    inactive = "inactive"
    deleted = "deleted"


def normalize_output_types(raw) -> List[str]:
    """output_types 归一化（OutputType 枚举消费，INT-74）

    去重 + 剔除非法值，按 OutputType 枚举定义序输出，保证落库与读侧口径一致。
    """
    if not isinstance(raw, (list, tuple, set)):
        return []
    present = {str(v) for v in raw}
    return [item.value for item in OutputType if item.value in present]


_AUDIO_CONFIG_KEYS = ('sample_rate', 'bit_depth', 'channels', 'container', 'format', 'chunk_duration_ms')


def normalize_audio_config(raw) -> Optional[Dict]:
    """audio_config 归一化：仅保留已知键的 JSON 对象（None 原样通过）

    CRUD 写路径与聚合共用此过滤，防止未知键原样入库。
    非 dict 输入抛 ValueError。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("audio_config 必须是 JSON 对象")
    return {k: raw[k] for k in _AUDIO_CONFIG_KEYS if k in raw}


def derive_api_keys_summary(raw) -> Optional[Dict]:
    """从 api_keys 原始值派生密钥池非敏感摘要 {count, tails[]}（INT-1177）。

    完整密钥不进入摘要（仅尾号，零明文）；非法形态返回 None。聚合根承载
    摘要而非完整密钥，读侧序列化（_api_to_dict）只输出摘要、端点 dict 中
    完整 api_keys 一律不输出（PO/聚合根双兼容防御）。
    """
    if not isinstance(raw, list):
        return None
    cleaned = [str(k).strip() for k in raw if k is not None and str(k).strip()]
    if not cleaned:
        return None
    return {'count': len(cleaned), 'tails': [k[-4:] for k in cleaned]}


def derive_endpoint_keys_summary(ep) -> Optional[Dict]:
    """从单个端点 dict 派生 api_keys_summary（INT-1230 审计 D6'，endpoint 级）。

    与 derive_api_keys_summary 同语义，作用于 api_endpoints[] 条目的
    api_keys 字段；无 api_keys / 空数组 / 非法形态返回 None。
    """
    if not isinstance(ep, dict):
        return None
    return derive_api_keys_summary(ep.get('api_keys'))


def redact_endpoint_keys(ep) -> Optional[Dict]:
    """端点 dict 读侧防御：完整 api_keys 剥离、内嵌 api_keys_summary 派生。

    返回新 dict（不修改入参）；已含 api_keys_summary 的端点（聚合根派生态）
    沿用摘要；PO 原始态（含完整 api_keys）经派生后剥离。聚合根不承载完整
    密钥（零响应），读侧序列化只读本结果。
    """
    if not isinstance(ep, dict):
        return None
    out = dict(ep)
    summary = out.get('api_keys_summary') or derive_api_keys_summary(out.get('api_keys'))
    out.pop('api_keys', None)
    if summary is not None:
        out['api_keys_summary'] = summary
    return out


@dataclass(frozen=True)
class APISnapshot:
    """API 快照值对象 — 不可变，记录某一时刻 API 的核心信息。"""

    id: int
    name: str
    url: str
    method: HTTPMethod = HTTPMethod.GET


@dataclass
class APIAggregate:
    """API 聚合根 — 被测 API 配置的聚合根实体。

    聚合 API 的标识、请求定义（URL/方法/请求头/请求体）、
    超时与重试策略以及状态。所有对 API 的变更通过聚合根进行。
    """

    id: int
    name: str
    url: str
    method: HTTPMethod = HTTPMethod.GET
    headers: Dict[str, str] = field(default_factory=dict)
    body_template: Optional[str] = None
    timeout_seconds: int = 30
    retry_count: int = 0
    status: str = "active"
    deleted: bool = False
    # API 输出类型列表（OutputType 枚举值子集，多模态输出采集口径，INT-74）
    output_types: List[str] = field(default_factory=list)
    # 被测设备类型（DeviceType 枚举值，决定执行路由，UC-0901）
    device_type: str = "http_api"
    # 指定适配器类名（未指定时按 protocol+vendor 自动匹配，UC-0901）
    adapter_class: Optional[str] = None
    # 目标音频格式声明 {"sample_rate","bit_depth","channels","container"}，未配置回退默认（UC-0901）
    audio_config: Optional[Dict] = None
    # 当前默认 RMS→SPL 映射 ID（apis.rms_spl_mapping_id 指针，UC-0902 步骤6；
    # 读侧透出供前端「默认」星标/清除默认，执行侧 get_default_mapping 同源）
    rms_spl_mapping_id: Optional[int] = None
    # 网络代理（INT-839）：proxy_type=http/https/socks5/socks5h，proxy_url=
    # `user:pass@host:port`（不含 scheme）；两者皆空 = 不用代理
    proxy_type: Optional[str] = None
    proxy_url: Optional[str] = None
    # 密钥池非敏感摘要（INT-1177）：{count, tails[]}，尾号 = 每 key 末 4 位；
    # 聚合根不承载完整密钥（零响应），`_api_po_to_entity` 从 po.api_endpoints
    # 派生逐端点摘要；读侧序列化只读本字段
    api_keys_summary: Optional[Dict] = None
    # ===== 读侧回显字段（INT-1338：GET /apis、GET /apis/{id}、PUT 响应逐字段回显）=====
    # 供应商名称（volc_ast / ali / tencent 等）
    vendor: Optional[str] = None
    # 元数据（INT-1177：聚合根不承载完整 api_keys——映射时剥离，零明文；
    # 完整密钥池以 api_keys_summary 摘要承载，写侧经 get_api_meta 读原始 PO）
    meta: Optional[Dict] = None
    # 详细描述
    description: Optional[str] = None
    # 关联算法类型（translation / asr / speaker_recognition / tts 等）
    algorithm_type: Optional[str] = None
    # 默认最大并发数 / 超时时间 / 音频时长（未配置时 PO 有 DB 默认 5/30/60）
    default_max_process: Optional[int] = None
    default_max_timeout: Optional[int] = None
    default_max_audio_duration: Optional[int] = None
    # 健康度评分（0-100）
    health_score: Optional[float] = None
    # API 接入点配置列表（JSON）
    api_endpoints: List[Dict] = field(default_factory=list)
    # 创建 / 更新时间（读侧透出，datetime 或字符串）
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    # 端点级密钥池摘要（INT-1230 审计 D6'，endpoint 级返工）：逐端点内嵌
    # `api_keys_summary` 的端点 dict 列表（完整 api_keys 已剥离，聚合根零明文）；
    # `_api_po_to_entity` 从 po.api_endpoints 派生，读侧序列化逐端点输出
    endpoint_keys_summary: List[Dict] = field(default_factory=list)

    def set_output_types(self, raw) -> List[str]:
        """设置输出类型列表（经 OutputType 枚举归一化），返回归一化结果"""
        self.output_types = normalize_output_types(raw)
        return self.output_types

    def set_audio_config(self, raw) -> Optional[Dict]:
        """设置目标音频格式（经 normalize_audio_config 仅保留已知键），返回规整后的 dict"""
        self.audio_config = normalize_audio_config(raw)
        return self.audio_config

    def activate(self) -> None:
        """激活 API"""
        self.status = APIStatus.active.value
        self.deleted = False

    def deactivate(self) -> None:
        """停用 API"""
        self.status = APIStatus.inactive.value

    def is_active(self) -> bool:
        """判断 API 是否处于激活态"""
        return self.status == APIStatus.active.value and not self.deleted

    def update_url(self, new_url: str) -> None:
        """更新 API 的 URL"""
        self.url = new_url

    def update_headers(self, new_headers: Dict[str, str]) -> None:
        """更新 API 的请求头"""
        self.headers = dict(new_headers)
