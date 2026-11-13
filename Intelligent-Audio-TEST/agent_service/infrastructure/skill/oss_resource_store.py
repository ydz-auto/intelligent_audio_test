# -*- coding: utf-8 -*-
"""Skill 资源的 OSS 实现（INT-2549 §4.4）。

复用仓库唯一的对象存储客户端 ``shared.clients.oss_client``：Skill 资源
（``references/`` / ``scripts/`` / ``assets/``）只存对象存储，表内只存 key。
写 ``archives`` 类目（长期保留，历史 run 回放要能取回旧版本资源）。
"""
import logging

from agent_service.domain.ports.skill_repository import SkillResourceStore

logger = logging.getLogger(__name__)

_CATEGORY = 'archives'


class OssSkillResourceStore(SkillResourceStore):
    def __init__(self, client=None):
        self._client = client

    def _oss(self):
        if self._client is None:
            from shared.clients.oss_client import oss
            self._client = oss
        return self._client

    def put(self, key: str, data: bytes,
            content_type: str = 'application/octet-stream') -> str:
        self._oss().upload_bytes(data, _CATEGORY, key,
                                 content_type=content_type)
        return key

    def get(self, key: str) -> bytes:
        return self._oss().download_bytes(_CATEGORY, key)

    def delete(self, key: str) -> None:  # pragma: no cover - 保留期策略不在本卡
        self._oss().delete_object(_CATEGORY, key)


__all__ = ['OssSkillResourceStore']
