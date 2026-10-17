# -*- coding: utf-8 -*-
"""EvaluationStrategyCrudService — 评估策略 CRUD 应用服务（命令侧，INT-590）。

策略实体归 task_service（用例域）：引用/删保护/列表计数全部本地化。
所有方法返回 dict: {success, message, data, code?}，网关侧负责 Pydantic 校验。
"""
from __future__ import annotations

import logging
import uuid

from task_service.domain.repositories.evaluation_strategy_repository import (
    EvaluationStrategyRepositoryABC,
)
from task_service.infrastructure.persistence.evaluation_strategy_repository import (
    evaluation_strategy_repository,
)

logger = logging.getLogger(__name__)


class EvaluationStrategyCrudService:
    """评估策略 CRUD 应用服务（命令侧）。"""

    def __init__(self, repo: EvaluationStrategyRepositoryABC = None):
        self.repo = repo or evaluation_strategy_repository

    # ==================== 写操作 ====================

    def create(self, data: dict) -> dict:
        """创建评估策略。

        Args:
            data: {name, description?, algorithm_type?, enabled?, config}
                  config: {dimensions: [...], background_noise: {...}}
                  与用例 config.dimensions / config.background_noise 同构
        Returns:
            {success, message, data, code?}（错误时 data 含 code 供网关提取）
        """
        try:
            name = (data.get('name') or '').strip()
            if not name:
                return {'success': False, 'message': '缺少必要字段: name', 'data': {'code': 400}, 'code': 400}

            config = data.get('config')
            if not isinstance(config, dict):
                return {'success': False, 'message': '缺少必要字段: config', 'data': {'code': 400}, 'code': 400}

            if self.repo.get_strategy_by_name(name):
                return {'success': False, 'message': f'策略名称已存在: {name}', 'data': {'code': 409}, 'code': 409}

            strategy_id = str(uuid.uuid4())
            new_strategy = self.repo.create_strategy({
                'id': strategy_id,
                'name': name,
                'description': data.get('description'),
                'algorithm_type': data.get('algorithm_type'),
                'enabled': data.get('enabled', True),
                'config': config,
            })

            self.repo.commit()

            return {
                'success': True,
                'message': '评估策略创建成功',
                'data': self._serialize(new_strategy, referenced_case_count=0),
                'code': 201,
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建评估策略失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': {'code': 500}, 'code': 500}

    def update(self, strategy_id: str, data: dict) -> dict:
        """更新评估策略。

        P1：编辑不回灌已引用用例（用例/任务均快照语义）；「批量同步策略变更」
        另开增强卡。
        """
        try:
            strategy = self.repo.get_strategy(strategy_id)
            if not strategy:
                return {'success': False, 'message': '未找到评估策略', 'data': {'code': 404}, 'code': 404}

            new_name = (data.get('name') or '').strip() if data.get('name') else None
            if new_name:
                existing = self.repo.get_strategy_by_name(new_name)
                if existing and existing.id != strategy_id:
                    return {'success': False, 'message': f'策略名称已存在: {new_name}', 'data': {'code': 409}, 'code': 409}

            config = data.get('config')
            if config is not None and not isinstance(config, dict):
                return {'success': False, 'message': 'config 必须是对象', 'data': {'code': 400}, 'code': 400}

            self.repo.update_strategy_attrs(strategy, data)
            self.repo.commit()

            return {
                'success': True,
                'message': '评估策略更新成功',
                'data': self._serialize(strategy,
                                        referenced_case_count=self.repo.count_referenced_cases(strategy_id)),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新评估策略失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': {'code': 500}, 'code': 500}

    def delete(self, strategy_id: str) -> dict:
        """删除评估策略（软删除）。

        被用例引用的策略不可直接删除：返回 409 + referenced_case_count，
        前端提示引用数/强制解除需二次确认。
        """
        try:
            strategy = self.repo.get_strategy(strategy_id)
            if not strategy:
                return {'success': False, 'message': '未找到评估策略', 'data': {'code': 404}, 'code': 404}

            referenced_count = self.repo.count_referenced_cases(strategy_id)
            if referenced_count > 0:
                return {
                    'success': False,
                    'message': f'策略被 {referenced_count} 个用例引用，无法删除；请先解除引用或二次确认强制解除',
                    'data': {
                        'strategy_id': strategy_id,
                        'referenced_case_count': referenced_count,
                        'code': 409,
                    },
                    'code': 409,
                }

            if not self.repo.soft_delete_strategy(strategy_id):
                return {'success': False, 'message': '未找到评估策略', 'data': {'code': 404}, 'code': 404}

            self.repo.commit()
            return {'success': True, 'message': '评估策略已删除', 'data': None}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除评估策略失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': {'code': 500}, 'code': 500}

    # ==================== 序列化 ====================

    @staticmethod
    def _serialize(strategy, referenced_case_count: int = 0) -> dict:
        """评估策略 PO → API DTO（snake_case，网关 schema 层再转 camelCase）。"""
        return {
            'id': strategy.id,
            'name': strategy.name,
            'description': strategy.description,
            'algorithm_type': strategy.algorithm_type,
            'enabled': bool(strategy.enabled),
            'config': strategy.config or {},
            'created_by_user_id': strategy.created_by_user_id,
            'updated_by_user_id': strategy.updated_by_user_id,
            'created_at': strategy.created_at.isoformat() if strategy.created_at else None,
            'updated_at': strategy.updated_at.isoformat() if strategy.updated_at else None,
            'referenced_case_count': referenced_case_count,
        }


# 模块级单例
evaluation_strategy_crud_service = EvaluationStrategyCrudService()
