# -*- coding: utf-8 -*-
"""原始报文外置对象（raw payload）口径的**唯一实现**（INT-1807 / INT-1811）

`test_result_dimensions` 的原始报文按内容寻址外置到对象存储，行上只留指针：

    key      raw/{resp|req}/{sha[:2]}/{sha}.json.gz
    category case_result（复用结果文件类别，多桶 / 单桶模式都免新增配置）
    字节     规范化 JSON：``json.dumps(value, sort_keys=True,
             separators=(',', ':'), ensure_ascii=False).encode('utf-8')``
             sha256 对这串**未压缩**字节算；gzip 压缩后上传，
             content_type 固定 ``application/json+gzip``，bytes 记压缩后大小。

调用方（禁止各自复制一份算法，否则规范化口径漂移会让同一报文算出不同 sha，
A→B→A 往返膨胀）：

- 迁移回填：``scripts/migrations/202610/backfill_raw_payload_pointers_int1807.py``
- 离线搬运 1.0 旧包现场物化：``task_service/infrastructure/transfer/raw_payload_store.py``

本模块是纯函数，不依赖 DB / 存储 / 网络。
"""
import gzip
import hashlib
import json
from dataclasses import dataclass
from typing import Optional

# 两类报文是独立取值空间（实测 response / request 各 6,492 / 6,164 个不同值），
# 打包成一份会丢掉跨值去重。
RAW_KIND_RESPONSE = 'resp'
RAW_KIND_REQUEST = 'req'

RAW_CATEGORY = 'case_result'
RAW_CONTENT_TYPE = 'application/json+gzip'
RAW_GZIP_COMPRESS_LEVEL = 9

RAW_KEY_SUFFIX = '.json.gz'


@dataclass(frozen=True)
class RawPayloadSpec:
    """一类报文的列映射（行上指针五列 + 内联 JSON 源列）"""
    kind: str
    json_column: str
    uri_column: str
    sha256_column: str
    bytes_column: str
    content_type_column: str
    created_at_column: str


RAW_PAYLOAD_SPECS = (
    RawPayloadSpec(
        kind=RAW_KIND_RESPONSE,
        json_column='api_raw_response',
        uri_column='api_raw_response_uri',
        sha256_column='api_raw_response_sha256',
        bytes_column='api_raw_response_bytes',
        content_type_column='api_raw_response_content_type',
        created_at_column='api_raw_response_created_at',
    ),
    RawPayloadSpec(
        kind=RAW_KIND_REQUEST,
        json_column='api_request_body',
        uri_column='api_request_body_uri',
        sha256_column='api_request_body_sha256',
        bytes_column='api_request_body_bytes',
        content_type_column='api_request_body_content_type',
        created_at_column='api_request_body_created_at',
    ),
)


def canonical_bytes(value) -> bytes:
    """规范化 JSON 字节：键序 / 分隔符固定，否则键序不同会产出重复对象。"""
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def sha256_of_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_hex(value) -> str:
    """对规范化字节算 sha256（内容寻址 key 的取值依据）"""
    return sha256_of_bytes(canonical_bytes(value))


def object_key(kind: str, sha: str) -> str:
    """内容寻址 key：raw/resp/{sha[:2]}/{sha}.json.gz（req 同理）"""
    if kind not in (RAW_KIND_RESPONSE, RAW_KIND_REQUEST):
        raise ValueError(f'非法原始报文类别: {kind!r}')
    sha = str(sha or '').strip().lower()
    if len(sha) != 64:
        raise ValueError(f'非法 sha256: {sha!r}')
    return f'raw/{kind}/{sha[:2]}/{sha}{RAW_KEY_SUFFIX}'


def compress(raw: bytes) -> bytes:
    """gzip 压缩；mtime 固定为 0（sha 对未压缩字节算，压缩差异不影响 key）。"""
    return gzip.compress(raw, compresslevel=RAW_GZIP_COMPRESS_LEVEL, mtime=0)


def decompress(data: bytes) -> bytes:
    return gzip.decompress(data)


def parse_object_key(key: str) -> Optional[tuple]:
    """解析内容寻址 key → (kind, sha)；不是 raw 对象 key 时返回 None。"""
    segments = str(key or '').split('/')
    if len(segments) != 4 or segments[0] != 'raw':
        return None
    kind, fanout, filename = segments[1], segments[2], segments[3]
    if kind not in (RAW_KIND_RESPONSE, RAW_KIND_REQUEST):
        return None
    if not filename.endswith(RAW_KEY_SUFFIX):
        return None
    sha = filename[:-len(RAW_KEY_SUFFIX)]
    if len(sha) != 64 or fanout != sha[:2]:
        return None
    return kind, sha


def sha_from_uri(uri: str) -> Optional[str]:
    """从存储路径（oss://case_result/raw/resp/ab/<sha>.json.gz）反推 sha256。"""
    from shared.utils.data_transfer import parse_storage_path
    _category, key = parse_storage_path(uri)
    parsed = parse_object_key(key)
    return parsed[1] if parsed else None
