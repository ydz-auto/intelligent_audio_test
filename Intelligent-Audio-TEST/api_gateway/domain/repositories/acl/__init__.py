# -*- coding: utf-8 -*-
"""api_gateway 跨域 ACL 仓储接口包。

按 DDD 约定：跨域只读查询与运行时调用的 ABC 定义在 domain/repositories/acl/，
实现放在 infrastructure/acl/。
"""
from api_gateway.domain.repositories.acl.audio_acl_repository import (
    AudioAclRepository,
)
from api_gateway.domain.repositories.acl.config_acl_repository import (
    AlgorithmConfigAclRepository,
    ApiConfigAclRepository,
    EvaluationConfigAclRepository,
    SplConfigAclRepository,
    TagConfigAclRepository,
    TaskConfigAclRepository,
    TestCaseConfigAclRepository,
)
from api_gateway.domain.repositories.acl.device_acl_repository import (
    DeviceAclRepository,
    PlaybackConfigAclRepository,
)
from api_gateway.domain.repositories.acl.execution_acl_repository import (
    ExecutionAclRepository,
)
from api_gateway.domain.repositories.acl.playback_acl_repository import (
    PlaybackAclRepository,
)
from api_gateway.domain.repositories.acl.reevaluation_acl_repository import (
    ReevaluationAclRepository,
)

__all__ = [
    'AlgorithmConfigAclRepository',
    'ApiConfigAclRepository',
    'AudioAclRepository',
    'DeviceAclRepository',
    'EvaluationConfigAclRepository',
    'ExecutionAclRepository',
    'PlaybackAclRepository',
    'PlaybackConfigAclRepository',
    'ReevaluationAclRepository',
    'SplConfigAclRepository',
    'TagConfigAclRepository',
    'TaskConfigAclRepository',
    'TestCaseConfigAclRepository',
]
