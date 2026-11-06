# -*- coding: utf-8 -*-
"""proto 上传与符号解析应用服务（INT-1952 / A3（INT-1791）硬前置）。

把用户上传的 `.proto` 落到 `api_test_service` 能读到的存储位置（内容寻址），
并回吐符号表（service / method / method_kind / 消息字段）供前端渲染下拉与
类型预览。

复用而非重写：大小 / UTF-8 / import 白名单 / protoc 编译全在
`infrastructure/adapters/transport/grpc_client.compile_proto`，本模块经
`load_compiled_proto` 走 sha 缓存（同内容只编译一次），只补「编译预算 +
并发限流 + 存储落盘 + 符号表」。

存储口径（卡面 §5 第 1/2 条）：
- `category='api-protos'`、`key='<sha256>.proto'`，`object_key` 是
  `storage.save_bytes(...)` 的**原样返回值**（带 `oss://` / `local://` scheme）；
- 幂等 = 同 key 覆盖写（内容寻址天然幂等），**不做 `exists()` 预检**；
- `allow_fallback=False`（D1/INT-1805）：OSS 不可用即抛
  `StorageUnavailableError` → `code=503` 向上报，不落本地降级目录。
"""
import concurrent.futures
import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict

from shared.infrastructure.storage import StorageUnavailableError, storage
from shared.models.proto_limits import (
    PROTO_COMPILE_MAX_CONCURRENCY,
    PROTO_COMPILE_TIMEOUT_SECONDS,
    PROTO_FILENAME_MAX_LEN,
    PROTO_OBJECT_SUFFIX,
    PROTO_STORAGE_CATEGORY,
)

from api_test_service.infrastructure.adapters.transport.grpc_client import (
    GrpcProtoError,
    load_compiled_proto,
)

logger = logging.getLogger(__name__)

CONTENT_TYPE = 'text/plain; charset=utf-8'

#: 业务码：0 成功；400 内容类错误；503 存储不可用；500 意外内部错误
CODE_OK = 0
CODE_CONTENT_ERROR = 400
CODE_INTERNAL_ERROR = 500
CODE_STORAGE_UNAVAILABLE = 503


class ProtoParseError(Exception):
    """可归类的解析失败：`code` 决定网关回给前端的 HTTP 状态。"""

    def __init__(self, message: str, code: int = CODE_CONTENT_ERROR):
        super().__init__(message)
        self.code = code


# protoc 是 CPU 密集的同步调用：单进程内限流 + 编译预算（卡面 §7 第 4/5 条）
_COMPILE_SEMAPHORE = threading.BoundedSemaphore(PROTO_COMPILE_MAX_CONCURRENCY)
_COMPILE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=PROTO_COMPILE_MAX_CONCURRENCY,
    thread_name_prefix='proto-compile',
)


def _compile_within_budget(proto_bytes: bytes, filename: str):
    """在 `PROTO_COMPILE_TIMEOUT_SECONDS` 内完成编译（同 sha 命中缓存立即返回）。"""
    deadline = time.monotonic() + PROTO_COMPILE_TIMEOUT_SECONDS
    if not _COMPILE_SEMAPHORE.acquire(timeout=PROTO_COMPILE_TIMEOUT_SECONDS):
        raise ProtoParseError('proto 编译超时')
    try:
        remaining = max(0.1, deadline - time.monotonic())
        future = _COMPILE_EXECUTOR.submit(load_compiled_proto, proto_bytes, filename)
        try:
            return future.result(timeout=remaining)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise ProtoParseError('proto 编译超时')
    finally:
        _COMPILE_SEMAPHORE.release()


class ApiProtoService:
    """上传 .proto → 编译 → 内容寻址落存储 → 符号表。"""

    @staticmethod
    def compile_filename(sha256: str) -> str:
        """编译用的文件名：sha 派生，与执行期 `api_{sha}.proto` 同口径。

        端点**不把客户端 filename 交给编译**（`compile_proto` 会把 filename
        拼进临时目录，直传可被 `../../x` 写出），客户端 filename 只进报错文案。
        """
        return f'api_{sha256}{PROTO_OBJECT_SUFFIX}'

    @staticmethod
    def parse(filename: str, content: bytes) -> Dict[str, Any]:
        """解析一份 proto 源码，返回 `{object_key, sha256, size, services}`。

        :raises ProtoParseError: 内容类错误（400）/ 存储不可用（503）
        """
        if not content:
            raise ProtoParseError('未收到 proto 文件')

        # sha256 / size 一律由服务端对字节计算，客户端声明不参与
        sha256 = hashlib.sha256(content).hexdigest()
        size = len(content)
        log_name = _filename_for_log(filename)

        try:
            compiled = _compile_within_budget(content, ApiProtoService.compile_filename(sha256))
        except GrpcProtoError as exc:  # 大小 / UTF-8 / import / protoc 全在这里
            raise ProtoParseError(str(exc), CODE_CONTENT_ERROR)

        services = [svc for svc in compiled.enumerate_services() if svc['methods']]
        if not services:
            raise ProtoParseError('proto 中没有可调用的 service', CODE_CONTENT_ERROR)

        try:
            object_key = storage.save_bytes(
                content,
                PROTO_STORAGE_CATEGORY,
                f'{sha256}{PROTO_OBJECT_SUFFIX}',
                content_type=CONTENT_TYPE,
                allow_fallback=False,
            )
        except StorageUnavailableError as exc:
            raise ProtoParseError(f'存储不可用: {exc}', CODE_STORAGE_UNAVAILABLE)

        # 只记元信息与符号名，不落上传内容 / 正文
        logger.info(
            'proto 解析成功 file=%s sha256=%s size=%d services=%s',
            log_name, sha256, size, [svc['name'] for svc in services])
        return {
            'object_key': object_key,
            'sha256': sha256,
            'size': size,
            'services': services,
        }


def _filename_for_log(raw: str) -> str:
    """客户端 filename 只用于日志 / 报错：basename 归一 + 限长。"""
    name = os.path.basename(str(raw or '').replace('\\', '/'))
    return name[:PROTO_FILENAME_MAX_LEN]


api_proto_service = ApiProtoService()
