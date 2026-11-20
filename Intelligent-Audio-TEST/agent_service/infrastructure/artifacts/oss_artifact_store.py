# -*- coding: utf-8 -*-
"""OSS 实现的大工具结果存储（§8.2 L1_TRIM）。

复用仓库唯一的对象存储客户端 ``shared.clients.oss_client``，不新起存储栈。
key 口径：``agent-context/<run_id>/<tool_call_id>.json``，写 ``archives`` 类目
（长期保留，避免 temp 类目的 TTL 清掉可回放产物）。
"""
import logging

from agent_service.domain.ports.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

_CATEGORY = 'archives'
_PREFIX = 'agent-context'


class OssArtifactStore(ArtifactStore):
    """把工具结果写进 OSS；OSS 不可用时抛错，由调用方降级为截断。"""

    def __init__(self, client=None):
        self._client = client

    def _oss(self):
        if self._client is None:
            from shared.clients.oss_client import oss
            self._client = oss
        return self._client

    def put(self, content: str, *, run_id: str, name: str,
            content_type: str = 'application/json') -> str:
        key = f'{_PREFIX}/{run_id}/{name}'
        self._oss().upload_bytes(
            content.encode('utf-8'), _CATEGORY, key,
            content_type=content_type)
        return f'oss://{_CATEGORY}/{key}'


__all__ = ['OssArtifactStore']
