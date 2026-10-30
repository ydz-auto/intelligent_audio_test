from typing import Any, List, Optional
from pydantic import Field, AliasChoices

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class PlaybackDeviceItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    model: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None)
    sample_rate: Optional[int] = Field(None)
    channel_index: Optional[int] = Field(None)
    device_unique_id: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    current_spl_mapping_id: Optional[int] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)
    # 实验室扩展：所属实验室（未绑定为 null，前端渲染「未绑定」；lab_name 由网关装饰）
    lab_id: Optional[int] = Field(None, description='所属实验室ID')
    lab_name: Optional[str] = Field(None, description='所属实验室名称（网关装饰）')


class PlaybackDeviceListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    keyword: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None, validation_alias=AliasChoices('type', 'device_type', 'deviceType'))
    lab_id: Optional[int] = Field(None)


class PlaybackDeviceListData(PaginatedData[PlaybackDeviceItem]):
    pass


class PlaybackScanItem(APIModel):
    name: Optional[str] = Field(None)
    model: Optional[str] = Field(None)
    device_unique_id: Optional[str] = Field(None)
    channel_index: Optional[int] = Field(None)
    sample_rate: Optional[int] = Field(None)
    type: Optional[str] = Field(None)
    status: Optional[str] = Field(None)


class PlaybackTestData(APIModel):
    device: Any = Field(...)
    audio: Any = Field(...)
    status: str = Field(...)
    device_index: Optional[int] = Field(None)
    channel_index: Optional[int] = Field(None)
    gain: Optional[float] = Field(None)


class PlaybackStatusItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    unique_id: str = Field(...)
    status: str = Field(...)
    device_index: Optional[int] = Field(None)


class PlaybackCreateSchema(APIModel):
    name: str = Field(...)
    model: str = Field(...)
    device_type: str = Field(...)
    sample_rate: int = Field(...)
    device_unique_id: str = Field(...)
    channel_index: Optional[int] = Field(0)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field('online')


class PlaybackUpdateSchema(APIModel):
    name: Optional[str] = Field(None)
    model: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None)
    sample_rate: Optional[int] = Field(None)
    channel_index: Optional[int] = Field(None)
    device_unique_id: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    current_spl_mapping_id: Optional[int] = Field(None)


class PlaybackTestSchema(APIModel):
    audio_id: Optional[int] = Field(None)
    spl: Optional[float] = Field(None)


class PlaybackAssociateSplSchema(APIModel):
    spl_mapping_id: int = Field(...)


class PlaybackRepairSchema(APIModel):
    """修复动作请求体（INT-1579 契约 §2.5）。

    动作白名单由 device_service 校验（单一事实源），网关只做形态校验，
    未知动作 → device_service 返回 400 并列出合法值。
    """
    actions: List[str] = Field(default_factory=list)


class PlaybackSpeakerGroupItem(APIModel):
    """逻辑音箱在某实验室对应的实体播放设备"""
    id: Optional[int] = Field(None)
    group_id: Optional[int] = Field(None)
    lab_id: int = Field(...)
    playback_device_id: int = Field(...)


class PlaybackSpeakerGroupItemSchema(APIModel):
    """设置逻辑音箱在指定实验室对应的播放设备"""
    lab_id: int = Field(...)
    playback_device_id: int = Field(...)


class PlaybackSpeakerGroupSchema(APIModel):
    """逻辑音箱组（N 个实验室里位置相同的音箱互相对应）"""
    name: str = Field(...)
    description: Optional[str] = Field(None)


class PlaybackSpeakerGroupData(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    items: List[PlaybackSpeakerGroupItem] = Field(default_factory=list)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class PlaybackSpeakerGroupListQuery(APIModel):
    keyword: Optional[str] = Field(None)
