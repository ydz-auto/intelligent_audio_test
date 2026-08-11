# -*- coding: utf-8 -*-
"""api_gateway 跨域 ACL 仓储接口包。

按 DDD 约定：跨域只读查询的 ABC 定义在 domain/repositories/acl/，
实现放在 infrastructure/acl/。
"""
from api_gateway.domain.repositories.acl.audio_acl_repository import (
    AudioAclRepository,
)
from api_gateway.domain.repositories.acl.config_acl_repository import (
    AlgorithmConfigAclRepository,
    ApiConfigAclRepository,
    EvaluationConfigAclRepository,
    TagConfigAclRepository,
    TaskConfigAclRepository,
    TestCaseConfigAclRepository,
)
from api_gateway.domain.repositories.acl.device_acl_repository import (
    DeviceAclRepository,
    PlaybackConfigAclRepository,
)

__all__ = [
    'AlgorithmConfigAclRepository',
    'ApiConfigAclRepository',
    'AudioAclRepository',
    'DeviceAclRepository',
    'EvaluationConfigAclRepository',
    'PlaybackConfigAclRepository',
    'TagConfigAclRepository',
    'TaskConfigAclRepository',
    'TestCaseConfigAclRepository',
]
