# -*- coding: utf-8 -*-
"""执行器本地冷存回源客户端（2026-11-28 裁定）。

背景：执行产物（case_result / ref_params）双写「执行机本地冷存 + 对象存储
热存」。对象存储只保留最近 30 天，过期后服务端（容器 / 另一台机器）无法
直接访问执行机磁盘，需要经执行器 `ArtifactService` 读取本地冷副本。

约定：
- 只在 `ARTIFACT_COLD_READ_ENABLED=true` 时启用；
- 执行器地址复用 `DEVICE_SERVICE_HOST/DEVICE_SERVICE_GRPC_PORT`（执行机常驻）；
- 任何失败都返回空结果，由调用方继续按「不存在」处理，不阻塞主链路；
- 本进程就是 device_service 时不走自调用（本地文件优先，远端也是同一节点）。
"""
import logging
import os
import threading
from datetime import datetime, timezone
from typing import List, Optional

import grpc

from shared.infrastructure.config import BaseConfig

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
_stub_lock = threading.Lock()
_stub_cache = None


def _enabled() -> bool:
    if not getattr(BaseConfig, 'ARTIFACT_COLD_READ_ENABLED', False):
        return False
    # 本机就是执行器：本地文件已优先尝试，无需自调用
    if (os.environ.get('SERVICE_NAME') or '').strip() == 'device_service':
        return False
    # 开发态各服务同机（host 缺省 localhost）时本地冷存已可命中；
    # 只有显式配置了远端执行机地址才启用回源，避免无谓的 3s 连接等待。
    host = (BaseConfig.DEVICE_SERVICE_HOST or '').strip().lower()
    if host in ('', 'localhost', '127.0.0.1', '::1') and not os.environ.get('DEVICE_SERVICE_HOST'):
        return False
    return True


def _get_stub():
    """惰性构建执行器 ArtifactService stub（进程内复用）。"""
    global _stub_cache
    if _stub_cache is not None:
        return _stub_cache
    with _stub_lock:
        if _stub_cache is not None:
            return _stub_cache
        from shared.proto import artifact_service_pb2_grpc as artifact_grpc
        host = BaseConfig.DEVICE_SERVICE_HOST
        port = BaseConfig.DEVICE_SERVICE_GRPC_PORT
        channel = grpc.insecure_channel(f'{host}:{port}')
        _stub_cache = artifact_grpc.ArtifactServiceStub(channel)
        return _stub_cache


def _timeout() -> float:
    try:
        return max(1.0, float(BaseConfig.ARTIFACT_COLD_READ_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return 30.0


def _list_timeout() -> float:
    try:
        return max(1.0, float(BaseConfig.ARTIFACT_COLD_LIST_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return 3.0


def list_artifacts(category: str, prefix: str = '') -> List[dict]:
    """列出执行器本地冷存条目；不可用/失败返回空列表。"""
    if not _enabled():
        return []
    try:
        from shared.proto import artifact_service_pb2 as artifact_pb
        stub = _get_stub()
        resp = stub.ListArtifacts(
            artifact_pb.ListArtifactsRequest(category=category, prefix=prefix),
            timeout=_list_timeout(),
        )
        items = []
        for item in resp.items:
            last_modified = None
            if item.last_modified_ms:
                last_modified = datetime.fromtimestamp(
                    item.last_modified_ms / 1000, tz=timezone.utc)
            items.append({
                'key': item.key,
                'sizeBytes': int(item.size_bytes),
                'lastModified': last_modified,
            })
        return items
    except Exception as e:
        logger.debug('artifact list failed (%s/%s): %s', category, prefix, e)
        return []


def stat_artifact(category: str, key: str) -> Optional[dict]:
    """查询执行器本地冷存单条元数据；不存在/失败返回 None。"""
    if not _enabled():
        return None
    try:
        from shared.proto import artifact_service_pb2 as artifact_pb
        stub = _get_stub()
        resp = stub.StatArtifact(
            artifact_pb.StatArtifactRequest(category=category, key=key),
            timeout=_list_timeout(),
        )
        if not resp.found:
            return None
        last_modified = None
        if resp.last_modified_ms:
            last_modified = datetime.fromtimestamp(
                resp.last_modified_ms / 1000, tz=timezone.utc)
        return {'sizeBytes': int(resp.size_bytes), 'lastModified': last_modified}
    except Exception as e:
        logger.debug('artifact stat failed (%s/%s): %s', category, key, e)
        return None


def read_artifact_bytes(category: str, key: str) -> Optional[bytes]:
    """流式读取执行器本地冷存文件；不存在/失败返回 None。"""
    if not _enabled():
        return None
    try:
        from shared.proto import artifact_service_pb2 as artifact_pb
        stub = _get_stub()
        chunks = []
        for chunk in stub.ReadArtifact(
                artifact_pb.ReadArtifactRequest(category=category, key=key),
                timeout=_timeout()):
            if chunk.data:
                chunks.append(chunk.data)
        if not chunks:
            return None
        return b''.join(chunks)
    except Exception as e:
        logger.debug('artifact read failed (%s/%s): %s', category, key, e)
        return None
