# -*- coding: utf-8 -*-
"""参数策略处理器（CQRS：读/写两侧共用）。

薄编排层：只做输入归一 + 调仓储，不直接触碰 ORM。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from algorithm_service.infrastructure.persistence._param_profile_repositories import (
    param_profile_command_repository,
    param_profile_repository,
)


class ParamProfileHandler:
    """策略读操作。"""

    @staticmethod
    def list_profiles(algorithm_type: Optional[str] = None,
                      scope: Optional[str] = None) -> List[Dict[str, Any]]:
        return param_profile_command_repository.list(algorithm_type, scope)

    @staticmethod
    def get_profile(profile_id: int) -> Optional[Dict[str, Any]]:
        return param_profile_command_repository.get(int(profile_id))

    @staticmethod
    def list_bindings(profile_ids: List[int]) -> List[Dict[str, Any]]:
        """按策略 id 批量读取 API 绑定（api_id / profile_id）。"""
        return param_profile_repository.list_bindings(profile_ids or [])

    @staticmethod
    def list_device_bindings(profile_ids: List[int]) -> List[Dict[str, Any]]:
        """按策略 id 批量读取设备绑定（device_id / profile_id）。"""
        return param_profile_repository.list_device_bindings(profile_ids or [])


class ParamProfileCommandHandler:
    """策略写操作（保存 / 克隆 / 删除 / 绑定 / 实例覆盖）。"""

    @staticmethod
    def save_profile(data: Dict[str, Any]) -> Dict[str, Any]:
        return param_profile_command_repository.save(data or {})

    @staticmethod
    def clone_profile(source_profile_id: int, name: str,
                      description: Optional[str] = None) -> Dict[str, Any]:
        return param_profile_command_repository.clone(
            int(source_profile_id), name, description)

    @staticmethod
    def delete_profile(profile_id: int) -> bool:
        return param_profile_command_repository.delete(int(profile_id))

    @staticmethod
    def bind_api(api_id: int, profile_id: Optional[int]) -> Dict[str, Any]:
        return param_profile_command_repository.bind_api(int(api_id), profile_id)

    @staticmethod
    def bind_device(device_id: int, profile_id: Optional[int]) -> Dict[str, Any]:
        return param_profile_command_repository.bind_device(int(device_id), profile_id)

    @staticmethod
    def save_api_overrides(api_id: int, algorithm_type: str,
                           api_params: List[Dict[str, Any]],
                           mappings: List[Dict[str, Any]]) -> Dict[str, int]:
        if not algorithm_type:
            raise ValueError('algorithm_type 必填')
        return param_profile_command_repository.save_api_overrides(
            int(api_id), algorithm_type, api_params or [], mappings or [])
