# -*- coding: utf-8 -*-
"""原始报文外置存储（内容寻址，uri-only）——C1 回填 / C2 读写路径共用的**唯一口径**。

背景：``test_result_dimensions.api_raw_response`` / ``api_request_body`` 曾是 JSON
列，同一份厂商报文按「维度 × 轮」重复落库（主库实测 51,857 行，去重后 6,492 个
响应 + 6,164 个请求体）。C1（INT-1807）给表补了指针列并回填对象，C2（INT-1809）
把写路径切到「组级一次上传 + 只写指针」、读路径切到「按指针读对象」。

口径实现在 ``shared/utils/raw_payload.py``（INT-1924 归一，纯函数、不依赖 DB /
存储 / 网络）：规范化字节 / sha256 / 对象 key / gzip 级别一律从那里导入，本模块
**只做存储、指针与进程内缓存**，不再自带一份实现——两份实现一旦漂移，同一份报文
会算出不同 sha，回填写入的对象与在线写入的对象互读不出来（A→B→A 往返膨胀）。

对象口径（改口径先改卡，三处必须一致：shared/utils/raw_payload.py、C1 回填脚本、
离线搬运）：
    key      ``raw/resp/{sha[:2]}/{sha}.json.gz`` / ``raw/req/{sha[:2]}/{sha}.json.gz``
    category ``case_result``（多桶模式用 case-result 桶；单桶模式自动加
             ``{OSS_KEY_PREFIX}/case_result/`` 前缀）
    字节     规范化 JSON：``json.dumps(v, sort_keys=True, separators=(',', ':'),
             ensure_ascii=False).encode('utf-8')``；sha256 对这串**未压缩**字节算；
             gzip（mtime=0，压缩确定）后上传，content_type=``application/json+gzip``，
             ``bytes`` 记压缩后大小。
    写入     一律 ``storage.save_bytes(..., allow_fallback=False)``（D1 / INT-1805）：
             OSS 不可用即抛 ``StorageUnavailableError``，**不落本地盘、不写 local://**；
             调用方据此不写 uri（宁可该组失败，也不留假指针）。
    读取     一律 ``storage.load_bytes(..., allow_fallback=False)``；解压后校验
             sha256，不符即抛 ``RawPayloadCorruptError``（绝不当空上下文用）。

请求体 / 响应体是独立取值空间（实测 6,164 / 6,492 个不同值），不打包成一份对象。
``None`` 视为「无报文」：不建对象、不写指针（C1 回填同口径）。
"""
import gzip
import hashlib
import json
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, NamedTuple, Optional, Tuple

from shared.utils.raw_payload import (
    RAW_CATEGORY as CATEGORY,
    RAW_CONTENT_TYPE as CONTENT_TYPE,
    RAW_KIND_REQUEST,
    RAW_KIND_RESPONSE,
    canonical_bytes,
    compress,
    object_key,
    sha256_hex,
)

#: 响应体 / 请求体两个独立取值空间（也是对象 key 的第二段）
KIND_RESPONSE = RAW_KIND_RESPONSE
KIND_REQUEST = RAW_KIND_REQUEST
KINDS = (KIND_RESPONSE, KIND_REQUEST)

#: kind → 指针列前缀（列由 C1 迁移脚本建）
COLUMN_PREFIX = {
    KIND_RESPONSE: 'api_raw_response',
    KIND_REQUEST: 'api_request_body',
}

#: 指针列后缀（顺序与迁移脚本 / ORM 一致）
POINTER_COLUMN_SUFFIXES = ('uri', 'sha256', 'bytes', 'content_type', 'created_at')

_LOCAL_SCHEME = 'local://'
_MISSING = object()


class RawPayloadError(RuntimeError):
    """原始报文外置存储的读写错误基类。"""


class RawPayloadUnavailableError(RawPayloadError):
    """对象不可达（存储不可用 / 对象不存在 / 禁止本地降级而只有 local://）。"""


class RawPayloadCorruptError(RawPayloadError):
    """对象在，但内容与 sha256 不符 / 解压或 JSON 解析失败。"""


class RawPayloadPointer(NamedTuple):
    """一行原始报文对应的对象指针（五列）。"""

    uri: str
    sha256: str
    size_bytes: int
    content_type: str
    created_at: datetime


# ------------------------------------------------------------------ 指针列

def column_names(kind: str) -> Tuple[str, ...]:
    """该 kind 的五列列名（uri / sha256 / bytes / content_type / created_at）。"""
    prefix = COLUMN_PREFIX[kind]
    return tuple(f'{prefix}_{suffix}' for suffix in POINTER_COLUMN_SUFFIXES)


def apply_pointer(target, kind: str, pointer: Optional[RawPayloadPointer]) -> None:
    """把指针写到目标行（ORM 对象）的五列；无报文时五列一并置空。

    M1（INT-1813）起 ``api_raw_response`` / ``api_request_body`` 两列已在库与 ORM 里
    删除（报文只存在于对象里），因此这里不再置空 JSON 列——不变量变成「行上要么有
    完整指针、要么五列全空」。
    """
    values = (None, None, None, None, None) if pointer is None else (
        pointer.uri, pointer.sha256, pointer.size_bytes,
        pointer.content_type, pointer.created_at)
    for column, value in zip(column_names(kind), values):
        setattr(target, column, value)


# ------------------------------------------------------------------ 存储

class RawPayloadStore:
    """原始报文对象读写（进程级单例；读侧带按 sha 的进程内缓存）。"""

    #: 读缓存预算：内容寻址 → 同一 sha 的内容恒定，缓存安全；命中率随报文重复度上升
    DEFAULT_CACHE_MAX_ENTRIES = 512
    DEFAULT_CACHE_MAX_BYTES = 64 * 1024 * 1024

    def __init__(self, cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
                 cache_max_bytes: int = DEFAULT_CACHE_MAX_BYTES,
                 uploader=None, downloader=None):
        self._cache: 'OrderedDict[str, Any]' = OrderedDict()
        self._cache_sizes: Dict[str, int] = {}
        self._cache_bytes = 0
        self._cache_max_entries = cache_max_entries
        self._cache_max_bytes = cache_max_bytes
        self._lock = threading.Lock()
        #: 仅用于测试注入（签名同 _upload / _download），生产路径留空走 storage
        self._uploader = uploader
        self._downloader = downloader
        #: 读取次数计数（测试与性能取证用：内容一致的对象只读一次）
        self.read_count = 0
        self.write_count = 0

    def new_group_cache(self, uploader=None) -> 'RawPayloadGroupCache':
        """新建组级缓存（同组内同值只上传一次）。"""
        return RawPayloadGroupCache(store=self, uploader=uploader)

    # ---- 写 ----

    def store(self, kind: str, value, uploader=None) -> RawPayloadPointer:
        """单值上传，返回指针。OSS 不可用 / 拿到 local:// 一律抛 StorageUnavailableError。

        ``uploader`` 仅用于测试注入（签名 ``(data, key) -> uri``）。
        """
        sha = sha256_hex(value)
        data = compress(canonical_bytes(value))
        key = object_key(kind, sha)
        uploader = uploader or self._uploader or self._upload
        uri = uploader(data, key)
        if not uri:
            raise self._storage_error(f'{kind} 对象上传未返回 uri: {key}')
        if uri.startswith(_LOCAL_SCHEME):
            raise self._storage_error(
                f'禁止本地降级却拿到 local:// 路径: {uri}（key={key}）')
        self.write_count += 1
        return RawPayloadPointer(
            uri=uri, sha256=sha, size_bytes=len(data),
            content_type=CONTENT_TYPE, created_at=datetime.now(timezone.utc))

    @staticmethod
    def _upload(data: bytes, key: str) -> str:
        from shared.infrastructure.storage import storage
        return storage.save_bytes(
            data, CATEGORY, key, content_type=CONTENT_TYPE, allow_fallback=False)

    @staticmethod
    def _storage_error(message: str) -> Exception:
        from shared.infrastructure.storage import StorageUnavailableError
        return StorageUnavailableError(message)

    # ---- 读 ----

    def load(self, kind: str, uri: str, sha256: str) -> Any:
        """按指针读对象：下载 → 解压 → 校验 sha256 → 解析 JSON。

        sha256 是内容地址，因此按 sha 做进程内缓存（同一份报文只下一次 OSS）。
        """
        if not uri:
            raise RawPayloadUnavailableError(f'{kind} 对象 uri 为空，无法读取')
        if not sha256:
            raise RawPayloadCorruptError(f'{kind} 对象缺少 sha256，无法校验: {uri}')

        cached = self._cache_get(sha256)
        if cached is not _MISSING:
            return cached

        from shared.infrastructure.storage import StorageUnavailableError
        try:
            data = self._do_download(uri)
        except StorageUnavailableError as exc:
            raise RawPayloadUnavailableError(
                f'{kind} 对象读取失败 {uri}: {exc}') from exc

        try:
            raw = gzip.decompress(data)
        except OSError as exc:
            raise RawPayloadCorruptError(
                f'{kind} 对象解压失败 {uri}: {exc}') from exc
        actual = hashlib.sha256(raw).hexdigest()
        if actual != sha256:
            raise RawPayloadCorruptError(
                f'{kind} 对象 sha256 校验失败 {uri}: 期望 {sha256} 实际 {actual}')
        try:
            value = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RawPayloadCorruptError(
                f'{kind} 对象 JSON 解析失败 {uri}: {exc}') from exc

        self.read_count += 1
        self._cache_put(sha256, value, len(raw))
        return value

    @staticmethod
    def _download(uri: str) -> bytes:
        from shared.infrastructure.storage import storage
        return storage.load_bytes(uri, allow_fallback=False)

    def _do_download(self, uri: str) -> bytes:
        downloader = self._downloader or self._download
        return downloader(uri)

    # ---- 读缓存（按内容地址） ----

    def _cache_get(self, sha256: str):
        with self._lock:
            if sha256 not in self._cache:
                return _MISSING
            self._cache.move_to_end(sha256)
            return self._cache[sha256]

    def _cache_put(self, sha256: str, value, size: int) -> None:
        if size > self._cache_max_bytes:
            return  # 单个对象就超过预算 → 不缓存，避免把进程内存顶爆
        with self._lock:
            if sha256 in self._cache:
                self._cache.move_to_end(sha256)
                return
            self._cache[sha256] = value
            self._cache_sizes[sha256] = size
            self._cache_bytes += size
            while (len(self._cache) > self._cache_max_entries
                   or self._cache_bytes > self._cache_max_bytes):
                old_sha, _old = self._cache.popitem(last=False)
                self._cache_bytes -= self._cache_sizes.pop(old_sha, 0)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_sizes.clear()
            self._cache_bytes = 0


class RawPayloadGroupCache:
    """组级原始报文缓存：**同值只上传一次**，行上只写指针。

    为什么必须在组级上传：一组 6~7 行的 resp/req 往往完全相同，逐行上传会把
    线上每天约 8 千次写放大成 5 万次 OSS 操作（6.44 倍失败面）。逐轮值
    （``per_round``）每行不同，因此按**值**去重而不是按行假设相同。

    失败方向：``pointer_for`` 上传失败即抛 ``StorageUnavailableError``（调用方据此
    不写 uri、按失败语义收口）；``mark_unavailable()`` 用于「已经确定存储不可用」的
    场景（失败记录落库路径），此后 ``pointer_for`` 一律返回 None（行上指针保持 NULL）。
    """

    def __init__(self, store: Optional[RawPayloadStore] = None, uploader=None):
        self._store = store or raw_payload_store
        self._uploader = uploader
        self._pointers: Dict[Tuple[str, str], RawPayloadPointer] = {}
        self._values: Dict[str, Any] = {}
        self._unavailable = False
        #: 计数供日志 / 测试取证（上传次数 = 不同值数，不是行数）
        self.uploaded = 0
        self.reused = 0

    def warm(self, kind: str, value) -> Optional[RawPayloadPointer]:
        """组级预上传（None 视作无报文）。失败抛 StorageUnavailableError。"""
        if value is None:
            return None
        return self.pointer_for(kind, value)

    def pointer_for(self, kind: str, value) -> Optional[RawPayloadPointer]:
        """取值对应的指针：值缓存命中直接复用，否则上传一次。"""
        if value is None:
            return None
        if self._unavailable:
            return None
        sha = sha256_hex(value)
        hit = self._pointers.get((kind, sha))
        if hit is not None:
            self.reused += 1
            return hit
        pointer = self._store.store(kind, value, uploader=self._uploader)
        self._pointers[(kind, sha)] = pointer
        self._values.setdefault(sha, value)
        self.uploaded += 1
        return pointer

    def value_for_sha(self, sha: str):
        """内存中的 payload（本组刚上传过的值）；未命中返回 None（≠ 报文为 null）。"""
        if not sha:
            return None
        return self._values.get(sha)

    def mark_unavailable(self) -> None:
        """标记存储不可用：后续取值不再尝试上传（行上指针保持 NULL）。"""
        self._unavailable = True

    @property
    def unavailable(self) -> bool:
        return self._unavailable


#: 进程级单例（读缓存挂在这里）
raw_payload_store = RawPayloadStore()
