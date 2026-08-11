# -*- coding: utf-8 -*-
"""SPL 映射查询应用服务（读侧）

CQRS 拆分后的读操作服务，包含原 SPLCrudService 的读操作方法：
- get_all / get_one / get_history / get_calibration_data / get_stats / get_by_device
"""
import logging

from device_service.domain.repositories import SPLRepositoryInterface

logger = logging.getLogger(__name__)


class SPLQueryService:
    """SPL 映射查询应用服务（读侧）"""

    def __init__(self, repo: SPLRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import spl_repository
            repo = spl_repository
        self.repo = repo

    # ========== 读操作 ==========

    def get_all(self, page: int = 1, per_page: int = 10, keyword: str = None,
                calibration_status: str = None, device_id: int = None) -> dict:
        """分页查询"""
        try:
            result = self.repo.list_spl_mappings(
                page=page, per_page=per_page, keyword=keyword,
                calibration_status=calibration_status, device_id=device_id,
            )
            return {'success': True, 'message': 'Success', 'data': result, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_one(self, mapping_id: int) -> dict:
        """查询详情"""
        data = self.repo.get_spl_mapping_dict(mapping_id)
        if data is None:
            return {'success': False, 'message': '未找到 SPL 映射记录', 'data': None, 'code': 404}
        return {'success': True, 'message': 'Success', 'data': data, 'code': 200}

    def get_history(self, mapping_id: int) -> dict:
        """获取校准历史"""
        try:
            data = self.repo.get_calibration_history(mapping_id)
            return {
                'success': True,
                'message': 'Success',
                'data': {'items': data, 'total': len(data)},
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_calibration_data(self, mapping_id: int) -> dict:
        """获取校准数据"""
        mapping = self.repo.get_spl_mapping(mapping_id)
        if not mapping or mapping.deleted:
            return {'success': False, 'message': '未找到映射记录', 'data': None, 'code': 404}
        return {'success': True, 'message': 'Success', 'data': mapping.calibration_data, 'code': 200}

    def get_stats(self) -> dict:
        """统计信息"""
        try:
            data = self.repo.get_spl_stats()
            return {'success': True, 'message': 'Success', 'data': data, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_by_device(self, device_id: int) -> dict:
        """按设备查询"""
        try:
            data = self.repo.get_spl_by_device(device_id)
            return {
                'success': True,
                'message': 'Success',
                'data': {'items': data, 'total': len(data)},
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


# 模块级实例
spl_query_service = SPLQueryService()
