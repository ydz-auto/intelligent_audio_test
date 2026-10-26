# -*- coding: utf-8 -*-
"""音频导入标签来源枚举（INT-1978）——tag_source 单一取值来源。

前端在音频导入（分片上传合并 / 秒传）时用 tag_source 控制「路径目录段是否解析成标签」：

- json：只用手填 + 前端解析出的 JSON tags，跳过 relative_path 目录段解析
- path：手填 + 路径目录段标签（JSON tags 由前端决定不并进请求 tags）
- both：手填 + JSON tags + 路径目录段标签（= 历史行为，默认）

取值集合冻结在本文件：网关 schema 用 AudioTagSource 做类型校验（非法值拒绝），
audio_service 侧用 resolve_tag_source 归一（缺失 / 未知 / 空值一律降级 both）。
"""
from enum import Enum


class AudioTagSource(str, Enum):
    """音频导入标签来源（值即请求字段原值，禁止改动）"""

    JSON = 'json'
    PATH = 'path'
    BOTH = 'both'


AUDIO_TAG_SOURCE_VALUES = tuple(item.value for item in AudioTagSource)


def resolve_tag_source(value) -> AudioTagSource:
    """归一 tag_source 取值：缺失 / 空 / 未知一律降级 both（旧客户端兼容，不抛异常）。

    网关层已用 AudioTagSource 校验并拒绝非法值；audio_service 侧拿到的 gRPC data
    JSON 不经网关校验（直连 / 旧客户端），故此处必须防御降级而不是抛错。
    """
    if isinstance(value, AudioTagSource):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in AUDIO_TAG_SOURCE_VALUES:
            return AudioTagSource(normalized)
    return AudioTagSource.BOTH


def should_resolve_path_tags(value) -> bool:
    """是否解析 relative_path 目录段为标签（json 模式跳过，path / both 照常）。"""
    return resolve_tag_source(value) is not AudioTagSource.JSON
