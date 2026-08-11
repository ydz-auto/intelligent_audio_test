# -*- coding: utf-8 -*-
"""e2e_test_service 领域层 — ACL 仓储接口（ABC）

跨服务数据访问的抽象接口，infrastructure/acl/ 下提供基于 gRPC 的实现。
应用层通过依赖注入使用这些接口，不直接 import gRPC stub。
"""
from e2e_test_service.domain.repositories.audio_acl_repository import (
    AudioAclRepository,
)
from e2e_test_service.domain.repositories.device_acl_repository import (
    DeviceAclRepository,
)
from e2e_test_service.domain.repositories.device_result_acl_repository import (
    DeviceResultAclRepository,
)
from e2e_test_service.domain.repositories.playback_acl_repository import (
    PlaybackAclRepository,
)
from e2e_test_service.domain.repositories.task_data_acl_repository import (
    TaskDataAclRepository,
)
from e2e_test_service.domain.repositories.e2e_repository_abc import (
    E2ETestRepositoryABC,
)

__all__ = [
    'AudioAclRepository',
    'DeviceAclRepository',
    'DeviceResultAclRepository',
    'PlaybackAclRepository',
    'TaskDataAclRepository',
    'E2ETestRepositoryABC',
]
