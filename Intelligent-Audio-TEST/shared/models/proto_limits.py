# -*- coding: utf-8 -*-
"""被测 API gRPC 的 proto 安全边界与存储口径（单一来源）。

INT-1952 起 `PROTO_MAX_BYTES` 由 `shared/` 持有：网关的上传预检与
api_test_service 的编译 / 执行期读取必须同口径，两处各写一份必然漂移
（卡面 §5 第 4 条；网关禁止反向 import `api_test_service`）。

执行期传输件 `api_test_service/.../transport/grpc_client.py` 从本模块
import 后**保留原名字 re-export**，既有 import 点（`grpc_adapter.py:37`
等）不改。
"""

#: 单个 .proto 源码字节上限（执行期读取与网关上传预检同口径）
PROTO_MAX_BYTES = 256 * 1024

#: 内容寻址存储的 category / key 后缀（key = `<sha256>.proto`）
PROTO_STORAGE_CATEGORY = 'api-protos'
PROTO_OBJECT_SUFFIX = '.proto'

#: protoc 编译预算（秒）：上传端点是同步请求，超时按内容类错误报出
PROTO_COMPILE_TIMEOUT_SECONDS = 10.0

#: 单进程内同时进行的 protoc 编译数上限（防上传风暴打满 CPU）
PROTO_COMPILE_MAX_CONCURRENCY = 2

#: 客户端 filename 归一后的文案长度上限（只用于校验 / 报错，不进存储与编译）
PROTO_FILENAME_MAX_LEN = 200

#: 网关 Content-Length 预检的 multipart 包体余量：Content-Length 是**整个
#: multipart 包体**（含 boundary 与分段头），合法上限文件也会比纯文件大若干
#: 字节，故只有超出「上限 + 余量」才在网关直接拒绝；真实文件字节数由分块读取
#: 的 `PROTO_MAX_BYTES + 1` 兜底。
PROTO_MULTIPART_OVERHEAD_SLACK_BYTES = 64 * 1024
