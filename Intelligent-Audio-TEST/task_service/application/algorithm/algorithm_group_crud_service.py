# -*- coding: utf-8 -*-
# DEPRECATED: 本文件已废弃，算法分组 CRUD 已迁移至 algorithm_service（DDD 四层架构）。
# 后续应通过 algorithm_service 的 gRPC 接口访问，详见 shared/clients/grpc_clients.py
# 中的 get_algorithm_group_service_stub。
# 当前保留仅为兼容 task_service.interfaces.grpc.algorithm_config.AlgorithmConfigServiceServicer，
# 待 algorithm_service 的 proto 接入并完成调用方切换后删除。
"""AlgorithmGroupCrudService - 算法分组配置 CRUD 服务。

职责：
- 算法分组 CRUD（创建/更新/删除）
- 算法分组查询（列表/详情）

持久化访问统一委托给 AlgorithmRepository（Repository 模式），
本服务不再直接出现 `session = get_db_session()` / `session.query()`。

所有方法返回 dict: {success, message, data, code?}
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict

from task_service.infrastructure.acl.algorithm_acl_repository import (
    AlgorithmRepository,
)

logger = logging.getLogger(__name__)


class AlgorithmGroupCrudService:
    """算法分组 CRUD 服务。"""

    def __init__(self):
        # 若子类（AlgorithmParamCrudService）已注入 repo 则不覆盖，
        # 否则自行注入，保证独立实例化亦可用。
        if not getattr(self, 'repo', None):
            self.repo = AlgorithmRepository()

    # ==================== 算法分组 写操作 ====================

    def create_group(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建算法分组"""
        name = data.get('name')
        if not name:
            return {'success': False, 'message': '分组名称不能为空', 'code': 400}

        try:
            existing = self.repo.find_group_by_name(name)
            if existing:
                return {'success': False, 'message': f"分组 '{name}' 已存在"}

            group = self.repo.create_group(data)
            algo_count = self.repo.count_algorithms_in_group_for_group(group)

            self.repo.commit()
            return {
                'success': True,
                'message': '分组创建成功',
                'data': self._group_to_dict(group, algo_count),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建算法分组失败: {e}")
            return {'success': False, 'message': f'创建失败: {e}', 'code': 500}

    def update_group(self, group_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新算法分组"""
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '分组不存在', 'code': 404}

            if data.get('name') is not None and data['name'] != group.name:
                existing = self.repo.find_group_by_name(data['name'])
                if existing:
                    return {'success': False, 'message': f"分组 '{data['name']}' 已存在"}

            self.repo.update_group_attrs(group, data)

            self.repo.commit()

            # Re-fetch to get updated data (gRPC update doesn't modify the local DTO)
            group = self.repo.get_group(group_id)
            algo_count = self.repo.count_algorithms_in_group_for_group(group)
            return {
                'success': True,
                'message': '分组更新成功',
                'data': self._group_to_dict(group, algo_count),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新算法分组失败: {e}")
            return {'success': False, 'message': f'更新失败: {e}', 'code': 500}

    def delete_group(self, group_id: int) -> Dict[str, Any]:
        """删除算法分组（软删除）"""
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '分组不存在', 'code': 404}

            algorithm_count = self.repo.count_algorithms_in_group(group_id)
            if algorithm_count > 0:
                return {
                    'success': False,
                    'message': f'该分组下有 {algorithm_count} 个算法，无法删除',
                    'code': 400,
                }

            self.repo.soft_delete_group(group)
            self.repo.commit()

            return {'success': True, 'message': '分组删除成功'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除算法分组失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}

    # ==================== 算法分组 读操作 ====================

    def list_groups(self) -> Dict[str, Any]:
        """获取算法分组列表"""
        try:
            groups = self.repo.list_groups()

            data_list = [
                self._group_to_dict(
                    g,
                    self.repo.count_algorithms_in_group_for_group(g),
                )
                for g in groups
            ]

            return {
                'success': True,
                'message': '',
                'data': {
                    'data': data_list,
                    'total': len(data_list),
                },
            }
        except Exception as e:
            logger.error(f"查询算法分组列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_group(self, group_id: int) -> Dict[str, Any]:
        """获取算法分组详情"""
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '分组不存在', 'code': 404}

            algo_count = self.repo.count_algorithms_in_group_for_group(group)
            return {
                'success': True,
                'message': '',
                'data': self._group_to_dict(group, algo_count),
            }
        except Exception as e:
            logger.error(f"获取算法分组失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 内部辅助 ====================

    @staticmethod
    def _group_to_dict(group, algorithm_count: int = 0) -> Dict[str, Any]:
        """序列化算法分组"""
        if isinstance(group, dict):
            g = group
        else:
            g = asdict(group)
        created_at = g.get('created_at')
        updated_at = g.get('updated_at')
        return {
            'id': g.get('id'),
            'name': g.get('name'),
            'description': g.get('description'),
            'icon': g.get('icon'),
            'display_order': g.get('display_order'),
            'algorithm_count': algorithm_count,
            'created_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else (created_at if isinstance(created_at, str) else None),
            'updated_at': updated_at.isoformat() if hasattr(updated_at, 'isoformat') else (updated_at if isinstance(updated_at, str) else None),
        }


# 模块级单例
algorithm_group_crud_service = AlgorithmGroupCrudService()
