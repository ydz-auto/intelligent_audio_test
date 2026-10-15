# -*- coding: utf-8 -*-
"""挑选合并 ACL 仓储实现（INT-339）——委托 cherry_pick gRPC 代理。"""
from __future__ import annotations

from api_gateway.domain.dto import CommandResultDTO
from api_gateway.domain.repositories.acl.cherry_pick_acl_repository import (
    CherryPickAclRepository,
)


def _wrap(result) -> CommandResultDTO:
    """将 gRPC 返回的信封 dict 封装为 CommandResultDTO。"""
    if isinstance(result, dict):
        return CommandResultDTO(
            success=result.get('success', False),
            message=result.get('message'),
            data=result.get('data'),
            code=result.get('code'),
        )
    return CommandResultDTO(success=False, data=result)


class CherryPickAclRepositoryImpl(CherryPickAclRepository):
    """task_service.CherryPickService 挑选合并 ACL 实现。"""

    # ---- 购物车 ----

    def get_cart(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.get_cart())

    def add_cart_items(self, result_ids) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.add_cart_items(result_ids))

    def remove_cart_items(self, item_ids) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.remove_cart_items(item_ids))

    def clear_cart(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.clear_cart())

    # ---- 挑选集 ----

    def save_set(self, name, description=None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.save_set(name, description))

    def list_sets(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.list_sets())

    def get_set(self, set_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.get_set(set_id))

    def delete_set(self, set_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.delete_set(set_id))

    def restore_set_to_cart(self, set_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.restore_set_to_cart(set_id))

    # ---- 挑选候选查询 ----

    def list_candidates(self, query) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.list_candidates(query))

    # ---- 下单 ----

    def preview(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.preview())

    def checkout(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.checkout(data))

    # ---- 溯源 ----

    def get_source(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import cherry_pick_service
        return _wrap(cherry_pick_service.get_source(task_id))
