# -*- coding: utf-8 -*-
"""adb track-devices 原始帧解析（L0 设备事件源）。

``adb track-devices -l`` 的 stdout 是 adb host 服务的裸帧：
4 字节 ASCII 十六进制长度 + 等长 UTF-8 设备表文本；每次设备表变化下发一整帧
（等价 ``adb devices -l`` 去表头后的全量快照，不是增量）。

本模块只做协议解析，不启动进程、不碰数据库，便于单测复用。
"""
from __future__ import annotations

import re
from typing import BinaryIO, Dict, Optional

# 帧头长度（adb host 协议固定 4 位十六进制）
ADB_TRACK_HEADER_SIZE = 4
# adb devices 中唯一“可执行”状态；offline / unauthorized / no permissions 均视为不可用
ADB_DEVICE_STATE_ONLINE = 'device'
_FRAME_HEADER_PATTERN = re.compile(rb'^[0-9a-fA-F]+$')
# 帧间可能出现的换行/回车（部分 adb 版本追加），读帧头时跳过
_FRAME_HEADER_IGNORED = b'\r\n'


def read_device_frame(stream: BinaryIO) -> Optional[bytes]:
    """从 adb track-devices 输出流读取一帧设备表文本。

    Returns:
        帧载荷（可能为空 bytes）；流结束或协议损坏返回 None。
    """
    header = _read_frame_header(stream)
    if header is None:
        return None
    return _read_exact(stream, int(header, 16))


def _read_frame_header(stream: BinaryIO) -> Optional[bytes]:
    digits = b''
    while len(digits) < ADB_TRACK_HEADER_SIZE:
        char = stream.read(1)
        if not char:
            return None
        if char in _FRAME_HEADER_IGNORED:
            continue
        digits += char
    return digits if _FRAME_HEADER_PATTERN.match(digits) else None


def _read_exact(stream: BinaryIO, size: int) -> Optional[bytes]:
    if size <= 0:
        return b''
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def parse_device_snapshot(payload: bytes) -> Dict[str, str]:
    """设备表文本 → ``{serial: state}``；空行/字段不足的行忽略。"""
    snapshot: Dict[str, str] = {}
    for line in payload.decode('utf-8', errors='replace').splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        snapshot[fields[0]] = fields[1]
    return snapshot


def is_device_online(state: str) -> bool:
    """状态归一：仅 adb state=``device`` 视为在线。"""
    return state == ADB_DEVICE_STATE_ONLINE
