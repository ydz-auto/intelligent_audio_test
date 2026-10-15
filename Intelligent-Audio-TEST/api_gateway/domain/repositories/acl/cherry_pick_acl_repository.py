# -*- coding: utf-8 -*-
"""挑选合并 ACL 仓储接口（INT-339）：task_service.CherryPickService 抽象契约。"""
from abc import ABC, abstractmethod

from api_gateway.domain.dto import CommandResultDTO


class CherryPickAclRepository(ABC):
    """task_service.CherryPickService 挑选合并 ACL 接口。"""

    # ---- 购物车（per-user）----
    @abstractmethod
    def get_cart(self) -> CommandResultDTO: ...

    @abstractmethod
    def add_cart_items(self, result_ids) -> CommandResultDTO: ...

    @abstractmethod
    def remove_cart_items(self, item_ids) -> CommandResultDTO: ...

    @abstractmethod
    def clear_cart(self) -> CommandResultDTO: ...

    # ---- 挑选集 ----
    @abstractmethod
    def save_set(self, name, description=None) -> CommandResultDTO: ...

    @abstractmethod
    def list_sets(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_set(self, set_id) -> CommandResultDTO: ...

    @abstractmethod
    def delete_set(self, set_id) -> CommandResultDTO: ...

    @abstractmethod
    def restore_set_to_cart(self, set_id) -> CommandResultDTO: ...

    # ---- 挑选候选查询（S2）----
    @abstractmethod
    def list_candidates(self, query) -> CommandResultDTO: ...

    # ---- 下单（三出口 + 预览）----
    @abstractmethod
    def preview(self) -> CommandResultDTO: ...

    @abstractmethod
    def checkout(self, data) -> CommandResultDTO: ...

    # ---- 溯源 ----
    @abstractmethod
    def get_source(self, task_id) -> CommandResultDTO: ...
