# -*- coding: utf-8 -*-
"""EvaluationCommandService — 评估维度写操作应用服务（聚合模块，P4-4 大文件拆分）。

原单文件 791 行，已按职责拆分为 4 个内部模块，本文件保持
`from evaluation_service.application.commands.evaluation_command_service import ...`
的全部导入路径不变：

- _command_utils.py：响应构造 / JSON 字段解析 / 事件发布 / 关联算法载荷解析 / 常量
- _category_commands_mixin.py：CategoryCommandsMixin — 分类写操作
- _dimension_params_mixin.py：DimensionParamsMixin — 输入参数 / 输出字段 /
  ParamMapping / body_template 的公共同步逻辑
- _dimension_ops_mixin.py：DimensionOpsMixin — Dimension 辅助写操作
  （删除/批量/评分/健康探测/规则校验/子维度继承/公共子步骤）

本文件仅保留 create_dimension / update_dimension 主流程编排（<50 行/方法）。

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 self.repo 调用 Repository，不直连 DB
- 保留软删除模式（deleted=True + deleted_at）
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from shared.utils.query_utils import now_cst

from evaluation_service.domain.repositories.evaluation_repository_abc import (
    EvaluationRepositoryABC,
)
from evaluation_service.infrastructure.persistence.evaluation_repository import (
    evaluation_repository,
)
from evaluation_service.application.commands._command_utils import (
    DIMENSION_MODEL_FIELDS,
    command_ok,
    command_error,
    extract_associated_relations,
    get_default_algorithm_type,
    publish_dimension_config_changed,
)
from evaluation_service.application.commands._category_commands_mixin import (
    CategoryCommandsMixin,
)
from evaluation_service.application.commands._dimension_ops_mixin import (
    DIMENSION_TYPE_MAIN,
    DimensionOpsMixin,
)

logger = logging.getLogger(__name__)


def _refresh_stats_cache(op_name: str):
    """写操作后刷新统计缓存（api_gateway 提供的旁路优化，失败降级忽略）"""
    try:
        from api_gateway.application.services.stats_cache import refresh_stats_cache
        refresh_stats_cache()
    except Exception:
        logger.warning(f"{op_name}后刷新统计缓存失败", exc_info=True)


class EvaluationCommandService(CategoryCommandsMixin, DimensionOpsMixin):
    """评估维度写操作应用服务（CQRS Command）。

    Category 写操作复用 CategoryCommandsMixin；
    Dimension 参数同步/辅助写操作复用 DimensionOpsMixin（内含 DimensionParamsMixin）。
    """

    # 供 DimensionOpsMixin 使用的可赋值字段清单（向后兼容旧类属性名）
    _DIMENSION_MODEL_FIELDS = DIMENSION_MODEL_FIELDS

    def __init__(self, repo: EvaluationRepositoryABC = None):
        self.repo = repo or evaluation_repository

    def _refresh_stats_cache(self, op_name: str):
        """实例级包装：供 Mixin 内复用统计缓存刷新"""
        _refresh_stats_cache(op_name)

    # ==================== Dimension 写操作主流程 ====================

    def create_dimension(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建评分维度。"""
        if not data or 'name' not in data:
            return command_error('缺少名称(name)', code=400)

        err = self._parse_dimension_payload(data, strict_rule=False)
        if err:
            return err

        try:
            new_dim = self.repo.create_dimension(self._extract_model_fields(data))

            # 关联算法（gRPC 同步：先清空再插入）
            raw_associated = data.get('associatedAlgorithms') or data.get('associated_algorithms') or []
            self.repo.sync_relations(new_dim.id, extract_associated_relations(raw_associated))

            # 参数与 ParamMapping 同步（input + output）
            err = self._sync_dimension_params(
                new_dim.id, data, get_default_algorithm_type(raw_associated), update_mode=False)
            if err:
                return err

            self._sync_dimension_body_template(new_dim, data)

            self.repo.commit()
            self._refresh_stats_cache("创建评分维度")
            publish_dimension_config_changed('create', dim_id=new_dim.id)

            return command_ok('评分维度创建成功', data={'id': new_dim.id}, code=201)
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建评分维度失败: {e}")
            return command_error(str(e))

    def update_dimension(self, dim_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新评分维度。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim or dim.deleted:
                return command_error('未找到评分维度', code=404)

            err = self._parse_dimension_payload(data)
            if err:
                return err

            self._apply_dimension_fields(dim, data)

            # 关联算法（payload 未携带时不处理）
            raw_associated = data.get('associatedAlgorithms') or data.get('associated_algorithms')
            if raw_associated is not None:
                self.repo.sync_relations(dim.id, extract_associated_relations(raw_associated))
            algo_type = get_default_algorithm_type(raw_associated)

            err = self._sync_dimension_params(dim.id, data, algo_type, update_mode=True)
            if err:
                return err

            self._sync_update_body_template(dim, data)

            dim.updated_at = now_cst()

            # 主维度继承 API 配置给子维度
            if dim.dimension_type == DIMENSION_TYPE_MAIN:
                self._inherit_fields_to_sub_dimensions(dim)

            self.repo.commit()
            self._refresh_stats_cache("更新评分维度")
            publish_dimension_config_changed('update', dim_id=dim_id)

            return command_ok('评分维度更新成功')
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新评分维度失败: {e}")
            return command_error(str(e))

    def _sync_update_body_template(self, dim, data: Dict[str, Any]) -> None:
        """更新场景的 body_template 同步：以已解析的 required_inputs 为准。"""
        required_inputs = data.get('required_inputs')
        if required_inputs is not None and isinstance(required_inputs, list):
            updated_param_codes = self._extract_param_codes(required_inputs)
            if updated_param_codes:
                current_api_settings = dim.api_settings or {}
                dim.api_settings = self._sync_body_template(current_api_settings, updated_param_codes)


# 保持向后兼容的模块级别名（原文件导出）
_publish_dimension_config_changed = publish_dimension_config_changed
_DIMENSION_MODEL_FIELDS = DIMENSION_MODEL_FIELDS

# 模块级单例
evaluation_command_service = EvaluationCommandService()
