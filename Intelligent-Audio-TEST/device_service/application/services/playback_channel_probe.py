# -*- coding: utf-8 -*-
"""播放设备物理通道探测（INT-1579）

restart / reset-config / diagnosis 三个端点都要回答同一个问题：
「库里的播放设备行，在当前 audio_service 枚举结果里对应哪个物理通道？」
把匹配与通道容量判定收敛到本模块，避免 command / query 两侧各写一套口径。
"""
from __future__ import annotations

import re
from typing import List, Optional


def normalize_unique_id(unique_id: str) -> str:
    """归一化设备名中的声卡序号（与 check_status 同口径）"""
    if not unique_id:
        return unique_id
    return re.sub(r'\((\d+)-\s+', '(', unique_id)


def match_physical_channel(devices: List[dict], device_unique_id: str,
                           channel_index: Optional[int] = None) -> Optional[dict]:
    """在物理设备枚举结果里匹配播放设备行对应的通道

    匹配顺序：唯一标识精确命中 → 归一化标识命中；同标识多通道时按 channel_index 区分。
    返回匹配到的物理通道 dict（{unique_id, device_index, channel_index, sample_rate, ...}）或 None。
    """
    if not devices or not device_unique_id:
        return None

    candidates = [d for d in devices if d.get('unique_id') == device_unique_id]
    if not candidates:
        normalized = normalize_unique_id(device_unique_id)
        candidates = [d for d in devices if d.get('unique_id') == normalized]
    if not candidates:
        return None

    if channel_index is not None:
        for dev in candidates:
            if dev.get('channel_index') == channel_index:
                return dev
    return candidates[0]


def channel_capacity(devices: List[dict], device_index: Optional[int]) -> set:
    """某物理声卡（按 device_index 归组）可用的通道索引集合

    枚举结果每个元素就是一个通道（unique_id 内含 [Ch n]），因此通道容量 =
    同一 device_index 下出现过的 channel_index 集合。
    """
    if not devices or device_index is None:
        return set()
    return {
        d.get('channel_index') for d in devices
        if d.get('device_index') == device_index and d.get('channel_index') is not None
    }
