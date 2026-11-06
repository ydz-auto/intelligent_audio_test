# -*- coding: utf-8 -*-
"""task_service.TagConfigService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import logging
from typing import Optional

from report_service.domain.dto import TagCategoryDTO
from report_service.domain.repositories.acl.tag_acl_repository import (
    TagConfigAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
    return dto


class TagConfigAclRepositoryImpl(TagConfigAclRepository):
    """task_service.TagConfigService 跨域只读查询 gRPC 实现。"""

    def get_tag_category(self, category_id) -> Optional[TagCategoryDTO]:
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_tag_config_service_stub()
            resp = stub.GetTagCategory(task_pb.GetTagCategoryRequest(category_id=int(category_id)))
            if not resp.success:
                return None
            data = _loads(resp.data, None)
            return _attach(dict_to_dto(data, TagCategoryDTO), data)
        except Exception as e:
            logger.warning("get_tag_category gRPC failed: %s", e)
            return None

    def get_tags_by_category(self) -> Optional[TagCategoryDTO]:
        """查询按分类分组的标签全量（GetTagsByCategory）。

        INT-2100 路线 A：报告生成侧经单次调用取全量标签（真实库 ~115 活跃标签，
        载荷小），建 name → {id, category_id, category_name} 映射，供字符串 tag
        按名解析分类。失败返回 None，调用方按「无分类」兜底（不丢标签）。
        """
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_tag_config_service_stub()
            resp = stub.GetTagsByCategory(task_pb.GetTagsByCategoryRequest())
            if not resp.success:
                return None
            data = _loads(resp.data, None)
            if not isinstance(data, dict):
                return None
            return _attach(dict_to_dto(data, TagCategoryDTO), data)
        except Exception as e:
            logger.warning("get_tags_by_category gRPC failed: %s", e)
            return None
