# -*- coding: utf-8 -*-
"""实验室 Query 应用服务（读侧，INT-655 实验室管理）。

get_all/get_one/get_summary：
- get_all：分页列表（device_count/playback_device_count/test_case_count 由仓储统计）
- get_one：实验室详情 + 资源统计
- get_summary：仅资源统计（实验室扩展功能设计.md §5.1 GET /{id}/summary）
"""
import logging

from device_service.domain.repositories import LaboratoryRepositoryInterface

logger = logging.getLogger(__name__)


class LaboratoryQueryService:
    """实验室 Query 应用服务"""

    def __init__(self, repo: LaboratoryRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.laboratory_repository import laboratory_repository
            repo = laboratory_repository
        self.repo = repo

    def get_all(self, page: int = 1, per_page: int = 10, keyword: str = None,
                status: str = None) -> dict:
        try:
            data = self.repo.list_laboratories(
                page=int(page or 1), per_page=int(per_page or 10),
                keyword=keyword or None, status=status or None,
            )
            return {'success': True, 'message': '查询成功', 'data': data, 'code': 200}
        except Exception as e:
            logger.error("list laboratories failed: %s", e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_one(self, lab_id: int) -> dict:
        try:
            lab = self.repo.get_laboratory(lab_id)
            if not lab:
                return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
            counts = self._counts_for([lab_id])
            return {
                'success': True,
                'message': '查询成功',
                'data': {**lab.to_dict(), **counts.get(lab_id, {})},
                'code': 200,
            }
        except Exception as e:
            logger.error("get laboratory failed: %s", e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_summary(self, lab_id: int) -> dict:
        """实验室资源统计（GET /{id}/summary）"""
        try:
            if not self.repo.get_laboratory(lab_id):
                return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
            counts = self._counts_for([lab_id])
            return {
                'success': True,
                'message': '查询成功',
                'data': counts.get(lab_id, {}),
                'code': 200,
            }
        except Exception as e:
            logger.error("get laboratory summary failed: %s", e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def _counts_for(self, lab_ids) -> dict:
        """按 lab_id 汇总资源统计 dict（{lab_id: {device_count, ...}}）"""
        device_counts = self.repo.count_devices(lab_ids)
        playback_counts = self.repo.count_playback_devices(lab_ids)
        testcase_counts = self.repo.count_test_cases(lab_ids)
        result = {}
        for lab_id in lab_ids:
            result[lab_id] = {
                'device_count': device_counts.get(lab_id, 0),
                'playback_device_count': playback_counts.get(lab_id, 0),
                'test_case_count': testcase_counts.get(lab_id, 0),
            }
        return result


# 模块级实例
laboratory_query_service = LaboratoryQueryService()
