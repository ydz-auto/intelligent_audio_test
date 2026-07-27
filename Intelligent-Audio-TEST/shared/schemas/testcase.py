from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field, AliasChoices

from shared.schemas.base import APIModel


class ReportAudioItem(APIModel):
    id: Optional[int] = Field(None, alias='id', validation_alias='id')
    filename: Optional[str] = Field(None, alias='filename', validation_alias='filename')
    duration: Optional[float] = Field(None, alias='duration', validation_alias='duration')
    url: Optional[str] = Field(None, alias='url', validation_alias='url')
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    play_order: Optional[int] = Field(None, alias='play_order', validation_alias=AliasChoices('play_order', 'playOrder'))
    playback_device_id: Optional[int] = Field(None, alias='playback_device_id', validation_alias=AliasChoices('playback_device_id', 'playbackDeviceId'))
    playback_device_name: Optional[str] = Field(None, alias='playback_device_name', validation_alias=AliasChoices('playback_device_name', 'playbackDeviceName'))
    label: Optional[str] = Field(None, alias='label', validation_alias='label')
    timeline_start: Optional[float] = Field(None, alias='timeline_start', validation_alias=AliasChoices('timeline_start', 'timelineStart'))
    timeline_end: Optional[float] = Field(None, alias='timeline_end', validation_alias=AliasChoices('timeline_end', 'timelineEnd'))


class ReportTestCaseItem(APIModel):
    id: Optional[str] = Field(None, alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    category: Optional[str] = Field(None, alias='category', validation_alias='category')
    tags: List[Any] = Field(default_factory=list, alias='tags', validation_alias='tags')
    audios: List[ReportAudioItem] = Field(default_factory=list, alias='audios', validation_alias='audios')
    metrics: List[Any] = Field(default_factory=list, alias='metrics', validation_alias='metrics')
    asr: Optional[Dict[str, Any]] = Field(None, alias='asr', validation_alias='asr')
    translation: Optional[Dict[str, Any]] = Field(None, alias='translation', validation_alias='translation')
    results: List[Any] = Field(default_factory=list, alias='results', validation_alias='results')
    logs: Optional[str] = Field(None, alias='logs', validation_alias='logs')
