# -*- coding: utf-8 -*-
"""设备分组 Query 应用服务（读侧，INT-80）。"""
import logging

from device_service.domain.repositories import DeviceGroupRepositoryInterface

logger = logging.getLogger(__name__)


class DeviceGroupQueryService:
    """设备分组 Query 应用服务"""

    def __init__(self, repo: DeviceGroupRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_group_repository import device_group_repository
            repo = device_group_repository
        self.repo = repo

    def get_all(self, page: int = 1, per_page: int = 100, keyword: str = None,
                group_type: str = None) -> dict:
        try:
            data = self.repo.list_groups(
                page=int(page or 1), per_page=int(per_page or 100),
                keyword=keyword or None, group_type=group_type or None,
            )
            return {'success': True, 'message': '查询成功', 'data': data, 'code': 200}
        except Exception as e:
            logger.exception("查询设备分组列表失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_one(self, group_id: str) -> dict:
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '未找到设备分组', 'data': None, 'code': 404}
            counts = self.repo.count_group_devices([group_id])
            return {
                'success': True,
                'message': '查询成功',
                'data': {**group.to_dict(), 'device_count': counts.get(group_id, 0)},
                'code': 200,
            }
        except Exception as e:
            logger.exception("查询设备分组详情失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


device_group_query_service = DeviceGroupQueryService()
