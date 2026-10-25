# -*- coding: utf-8 -*-
"""api_test_service.APITestService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from report_service.config.config import Config
from report_service.domain.dto import ApiConfigDTO
from report_service.domain.repositories.acl.apitest_acl_repository import (
    ApiTestAclRepository,
)
from report_service.infrastructure.acl.lookup_cache import TTLCache
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)

# API 配置按 id 缓存（INT-1572 返工，与设备同因）：报告聚合按「每条测试结果」
# 取 API 元数据，同一批 API 被重复取几十上百次。只缓存取到的配置。
_api_cache = TTLCache(
    Config.REPORT_RESOURCE_ACL_CACHE_TTL_SECONDS,
    Config.REPORT_RESOURCE_ACL_CACHE_MAX_ENTRIES,
)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
    return dto


class ApiTestAclRepositoryImpl(ApiTestAclRepository):
    """api_test_service.APITestService 跨域只读查询 gRPC 实现。"""

    def get_api(self, api_id) -> Optional[ApiConfigDTO]:
        cached = _api_cache.get(api_id)
        if cached is not None:
            return cached
        from shared.clients.grpc_clients import get_api_test_service_stub
        from shared.proto import api_test_service_pb2 as api_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_api_test_service_stub()
            resp = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=int(api_id)))
            if not resp.success:
                return None
            data = _loads(resp.data, None)
            dto = _attach(dict_to_dto(data, ApiConfigDTO), data)
            _api_cache.set(api_id, dto)
            return dto
        except Exception as e:
            logger.warning("get_api gRPC failed: %s", e)
            return None

    def get_apis_by_ids(self, api_ids) -> Dict[int, ApiConfigDTO]:
        if not api_ids:
            return {}
        result: Dict[int, ApiConfigDTO] = {}
        for aid in api_ids:
            a = self.get_api(aid)
            if a is not None and a.id is not None:
                try:
                    result[int(a.id)] = a
                except Exception:
                    logger.debug("ApiConfig id 转换失败: %r", a.id, exc_info=True)
        return result
