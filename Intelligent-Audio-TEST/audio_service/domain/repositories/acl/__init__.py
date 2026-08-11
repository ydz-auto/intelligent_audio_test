# -*- coding: utf-8 -*-
"""audio_service 跨域 ACL 仓储接口包。

按 DDD 约定：跨域只读查询的 ABC 定义在 domain/repositories/acl/，
实现放在 infrastructure/acl/。
"""
from audio_service.domain.repositories.acl.task_acl_repository import (
    TaskACLRepository,
)
from audio_service.domain.repositories.acl.device_acl_repository import (
    DeviceACLRepository,
)

__all__ = ['TaskACLRepository', 'DeviceACLRepository']
