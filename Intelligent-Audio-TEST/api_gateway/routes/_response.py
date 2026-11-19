"""统一的 JSON 响应工具

解决 FastAPI JSONResponse 不支持 datetime/Decimal 等类型的问题。
替代 Flask jsonify 的自动序列化能力。
"""
import json
import os
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from urllib.parse import quote

from fastapi.responses import JSONResponse, StreamingResponse

# 流式下载分块大小（1MB：不把文件对象直接交给 Starlette，它会按行迭代）
DOWNLOAD_STREAM_CHUNK_BYTES = 1024 * 1024


def _default_encoder(obj):
    """处理 Flask jsonify 自动处理但 FastAPI 不处理的类型"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except Exception:
            return str(obj)
    if hasattr(obj, '__dict__') and hasattr(obj, 'to_dict') and callable(obj.to_dict):
        return obj.to_dict()
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')


class CustomJSONResponse(JSONResponse):
    """支持 datetime/Decimal 等类型的 JSONResponse"""

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(',', ':'),
            default=_default_encoder,
        ).encode('utf-8')


def to_response(result):
    """
    将 controller 返回的 (dict, int) tuple 转为 CustomJSONResponse。
    如果 result 已经是 Response 对象，直接返回。
    """
    if isinstance(result, tuple) and len(result) == 2:
        return CustomJSONResponse(content=result[0], status_code=result[1])
    return result


def content_disposition(filename, fallback='export'):
    """构造下载响应头 Content-Disposition 的值（RFC 6266 / RFC 5987）。

    中文等非 ASCII 文件名直接写进响应头时，Starlette 按 latin-1 编码会抛
    UnicodeEncodeError（HTTP 500），因此同时给出两段：
    - filename="<ASCII 名>"：本身是 ASCII 时保持原名，否则退化为「兜底名 + 扩展名」；
    - filename*=UTF-8''<百分号编码>：保留原始文件名，现代浏览器优先采用。
    """
    name = filename or fallback
    ext = os.path.splitext(name)[1]
    ascii_ext = ''.join(ch for ch in ext if ch.isascii() and (ch.isalnum() or ch == '.'))
    ascii_name = name.replace('\\', '_').replace('"', '_') if name.isascii() \
        else f'{fallback}{ascii_ext}'
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


def stream_download_response(stream, filename, media_type='application/octet-stream'):
    """把存储流按固定块流式回传（结束关闭句柄）。

    用于导出产物、日志 ZIP 等大文件：网关从桶内网读、按块转发给浏览器，
    不整包驻留内存，也不下发预签名直链（FILE_DOWNLOAD_VIA_GATEWAY）。
    """
    def _iter():
        try:
            while True:
                chunk = stream.read(DOWNLOAD_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        _iter(),
        media_type=media_type,
        headers={'Content-Disposition': content_disposition(filename)},
    )
