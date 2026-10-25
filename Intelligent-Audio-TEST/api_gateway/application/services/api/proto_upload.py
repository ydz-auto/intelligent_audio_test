# -*- coding: utf-8 -*-
"""proto 上传的网关侧预检（INT-1952）。

网关没有全局 body 上限（`api_gateway/app.py` 无 `max_upload` 类配置），超大文件
必须**在调 RPC 之前**拒绝（卡面 §6 第 1 条），且不把整份超大文件读进内存：

- 有 `Content-Length` 时先按「上限 + multipart 包体余量」判（Content-Length 是
  整个 multipart 包体，合法上限文件本身也会比纯文件大若干字节）；
- 无该头（chunked）时按块读，读满 `PROTO_MAX_BYTES + 1` 即拒。

客户端 filename 只用于报错文案：basename 归一 + 限长，**绝不参与编译 / 存储**
（编译用 sha 派生文件名，存储 key 用 sha256）。

大小上限与 api_test_service 同口径，常量来自 `shared/models/proto_limits.py`。
"""
import os
from typing import Optional

from shared.models.proto_limits import (
    PROTO_FILENAME_MAX_LEN,
    PROTO_MAX_BYTES,
    PROTO_MULTIPART_OVERHEAD_SLACK_BYTES,
)

_CHUNK_SIZE = 64 * 1024


class ProtoUploadError(Exception):
    """上传内容不合规：网关直接回 400，不调 RPC。"""


def normalize_filename(raw) -> str:
    """客户端 filename 归一：只留 basename，并限长到文案上限。"""
    name = os.path.basename(str(raw or '').replace('\\', '/'))
    return name[:PROTO_FILENAME_MAX_LEN]


def _size_error(actual: int) -> ProtoUploadError:
    return ProtoUploadError(
        f'proto 文件超过 {PROTO_MAX_BYTES} 字节上限（实际 {actual}）')


def check_content_length(content_length: Optional[str]) -> None:
    """有 `Content-Length` 时先判：整个 multipart 包体超「上限 + 余量」即拒。"""
    if content_length in (None, ''):
        return
    try:
        declared = int(content_length)
    except (TypeError, ValueError):
        return
    if declared > PROTO_MAX_BYTES + PROTO_MULTIPART_OVERHEAD_SLACK_BYTES:
        raise _size_error(declared)


def read_upload(file) -> bytes:
    """按块读到 `PROTO_MAX_BYTES + 1` 为止；超出即拒，空文件报「未收到」。"""
    chunks = []
    total = 0
    while True:
        chunk = file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > PROTO_MAX_BYTES:
            raise _size_error(total)
        chunks.append(chunk)
    if not total:
        raise ProtoUploadError('未收到 proto 文件')
    return b''.join(chunks)
