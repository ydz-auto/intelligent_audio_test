# -*- coding: utf-8 -*-
"""api_gateway 基础设施层 — ACL 仓储实现包。

跨服务 gRPC 调用的具体实现，对应 domain/repositories/acl/ 下的 ABC 接口。
委托现有 grpc_proxies 单例完成 gRPC 调用，对返回的 raw dict / 信封 data /
(success, message) tuple 负载经 shared.utils.dto_utils.dict_to_dto /
dict_list_to_dto 转换为 dataclass DTO。
"""
from api_gateway.infrastructure.acl.audio_acl_repository import (
    AudioAclRepositoryImpl,
)
from api_gateway.infrastructure.acl.config_acl_repository import (
    AlgorithmConfigAclRepositoryImpl,
    ApiConfigAclRepositoryImpl,
    EvaluationConfigAclRepositoryImpl,
    SplConfigAclRepositoryImpl,
    TagConfigAclRepositoryImpl,
    TaskConfigAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
)
from api_gateway.infrastructure.acl.device_acl_repository import (
    DeviceAclRepositoryImpl,
    PlaybackConfigAclRepositoryImpl,
)
from api_gateway.infrastructure.acl.execution_acl_repository import (
    ExecutionAclRepositoryImpl,
)
from api_gateway.infrastructure.acl.playback_acl_repository import (
    PlaybackAclRepositoryImpl,
)
from api_gateway.infrastructure.acl.reevaluation_acl_repository import (
    ReevaluationAclRepositoryImpl,
)

__all__ = [
    'AlgorithmConfigAclRepositoryImpl',
    'ApiConfigAclRepositoryImpl',
    'AudioAclRepositoryImpl',
    'DeviceAclRepositoryImpl',
    'EvaluationConfigAclRepositoryImpl',
    'ExecutionAclRepositoryImpl',
    'PlaybackAclRepositoryImpl',
    'PlaybackConfigAclRepositoryImpl',
    'ReevaluationAclRepositoryImpl',
    'SplConfigAclRepositoryImpl',
    'TagConfigAclRepositoryImpl',
    'TaskConfigAclRepositoryImpl',
    'TestCaseConfigAclRepositoryImpl',
]
