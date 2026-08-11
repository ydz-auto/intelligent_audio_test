# -*- coding: utf-8 -*-
"""device_service 仓储接口包。

按 DDD 分层：
- 自有数据 ABC → domain/repositories/
- 跨域 ACL ABC → domain/repositories/acl/
- 实现 → infrastructure/persistence/ 和 infrastructure/acl/
"""
from device_service.domain.repositories.device_repository_abc import (
    DeviceRepositoryInterface,
    PlaybackRepositoryInterface,
    SPLRepositoryInterface,
)

__all__ = [
    'DeviceRepositoryInterface',
    'PlaybackRepositoryInterface',
    'SPLRepositoryInterface',
]
