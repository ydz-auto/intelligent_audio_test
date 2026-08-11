# -*- coding: utf-8 -*-
"""audio_service 跨域 ACL 仓储实现包。

按 DDD 约定：跨域只读查询的实现在 infrastructure/acl/，
接口 ABC 在 domain/repositories/acl/。
"""
from audio_service.infrastructure.acl.task_acl_repository import (
    TaskACLRepositoryImpl,
)
from audio_service.infrastructure.acl.device_acl_repository import (
    DeviceACLRepositoryImpl,
)

__all__ = ['TaskACLRepositoryImpl', 'DeviceACLRepositoryImpl']
