# -*- coding: utf-8 -*-
"""执行器本地冷存只读服务（2026-11-28）。

对象存储只保留最近 30 天，执行产物（case_result / ref_params）在产生节点
本地冷存保留 365 天。服务端（容器 / 另一台机器）不共享该磁盘，只读经本
gRPC 服务回源。

安全边界：
- category 只允许 `RESULT_DUAL_WRITE_CATEGORIES` 白名单；
- key 拒绝绝对路径与 `..`，解析后必须落在冷存根内。
"""
import logging
import os

from shared.infrastructure.config import BaseConfig
from shared.proto import artifact_service_pb2 as pb
from shared.proto import artifact_service_pb2_grpc as pb_grpc

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
# 单次列举上限，避免一次扫描过多文件拖垮响应
_MAX_LIST_ITEMS = 10000


def _cold_root() -> str:
    explicit = (os.environ.get('RESULT_LOCAL_ROOT') or '').strip()
    return explicit or BaseConfig.STORAGE_LOCAL_ROOT


def _allowed_categories() -> set:
    raw = getattr(BaseConfig, 'RESULT_DUAL_WRITE_CATEGORIES', '') or ''
    return {part.strip().lower() for part in raw.split(',') if part.strip()}


def _resolve_path(category: str, key: str) -> str:
    """解析并校验冷存路径；非法时抛 ValueError。"""
    if (category or '').strip().lower() not in _allowed_categories():
        raise ValueError(f'category 不在冷存白名单: {category}')
    normalized = (key or '').replace('\\', '/')
    if not normalized or normalized.startswith('/'):
        raise ValueError('非法 key')
    root = os.path.abspath(os.path.join(_cold_root(), category))
    target = os.path.abspath(os.path.join(root, normalized))
    if os.path.commonpath([root, target]) != root:
        raise ValueError('key 越界')
    return target


class ArtifactServiceServicer(pb_grpc.ArtifactServiceServicer):
    """本地冷存列举 / 元数据 / 流式读取。"""

    def ListArtifacts(self, request, context=None):
        try:
            root = os.path.abspath(os.path.join(_cold_root(), request.category))
            prefix = (request.prefix or '').replace('\\', '/').lstrip('/')
            start = os.path.abspath(os.path.join(root, prefix)) if prefix else root
            if os.path.commonpath([root, start]) != root:
                raise ValueError('prefix 越界')
        except ValueError as e:
            if context is not None:
                context.abort(3, str(e))
            return pb.ListArtifactsResponse()

        items = []
        if os.path.isdir(start):
            for cur, _dirs, files in os.walk(start):
                for name in files:
                    full = os.path.join(cur, name)
                    rel = os.path.relpath(full, root).replace(os.sep, '/')
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    items.append(pb.ArtifactItem(
                        key=rel,
                        size_bytes=st.st_size,
                        last_modified_ms=int(st.st_mtime * 1000),
                    ))
                    if len(items) >= _MAX_LIST_ITEMS:
                        break
                if len(items) >= _MAX_LIST_ITEMS:
                    break
        return pb.ListArtifactsResponse(items=items)

    def StatArtifact(self, request, context=None):
        try:
            path = _resolve_path(request.category, request.key)
        except ValueError as e:
            if context is not None:
                context.abort(3, str(e))
            return pb.StatArtifactResponse(found=False)
        if not os.path.isfile(path):
            return pb.StatArtifactResponse(found=False)
        st = os.stat(path)
        return pb.StatArtifactResponse(
            found=True,
            size_bytes=st.st_size,
            last_modified_ms=int(st.st_mtime * 1000),
        )

    def ReadArtifact(self, request, context=None):
        try:
            path = _resolve_path(request.category, request.key)
        except ValueError as e:
            if context is not None:
                context.abort(3, str(e))
            return
        if not os.path.isfile(path):
            if context is not None:
                context.abort(5, '冷存文件不存在')
            return
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield pb.ArtifactChunk(data=chunk)
