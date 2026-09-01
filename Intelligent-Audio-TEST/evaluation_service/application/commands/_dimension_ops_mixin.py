# -*- coding: utf-8 -*-
"""评分维度（Dimension）辅助写操作 Mixin（从 evaluation_command_service.py 拆分，P4-4）。

提取 create/update_dimension 之外的 Dimension 辅助流程：软删除、批量操作、
评分计算、健康探测、删除评估记录、规则结构校验、子维度继承。

update_dimension 的 payload 预处理 / 字段落库 / 参数同步也被分解为
单一职责小方法（_parse_dimension_payload / _apply_dimension_fields /
_sync_dimension_params），供 create/update 共用（消除重复）。
"""
import logging
from typing import Any, Dict, Optional, Tuple

from shared.utils.query_utils import now_cst

from evaluation_service.application.commands._command_utils import (
    command_ok,
    command_error,
    parse_json_field,
    publish_dimension_config_changed,
)
from evaluation_service.application.commands._dimension_params_mixin import (
    DimensionParamsMixin,
)

logger = logging.getLogger(__name__)

# 维度维度类型：主维度（子维度继承其 API 配置）
DIMENSION_TYPE_MAIN = 'main'


class DimensionOpsMixin(DimensionParamsMixin):
    """Dimension 辅助写操作（依赖 self.repo）"""

    # ==================== 规则校验 ====================

    def validate_rule_structure(self, rule) -> Tuple[bool, str]:
        """验证评分规则结构（委托 Domain Entity ScoringRule.validate）。"""
        from evaluation_service.domain.entities import ScoringRule
        if not isinstance(rule, dict):
            return False, '规则必须是一个 JSON 对象'
        if 'rules' not in rule:
            return False, "规则对象必须包含 'rules' 字段"
        if not isinstance(rule['rules'], list):
            return False, "'rules' 字段必须是一个列表"
        scoring_rule = ScoringRule.from_dict(rule)
        return scoring_rule.validate()

    # ==================== create/update 公共子步骤 ====================

    def _parse_dimension_payload(self, data: Dict[str, Any],
                                 strict_rule: bool = True) -> Optional[Dict[str, Any]]:
        """解析 rule / required_inputs / api_settings JSON 字段。

        就地回写 data['rule'] / data['required_inputs'] / data['api_settings']。
        strict_rule=False（create 场景）时 rule 为空值则跳过解析；
        strict_rule=True（update 场景）时只要携带 rule 键就解析（与历史行为一致）。
        返回错误响应 dict 或 None。
        """
        if 'rule' in data and (strict_rule or data.get('rule')):
            rule = data['rule']
            ok, rule = parse_json_field(rule, '规则格式错误: 无效的 JSON 字符串')
            if not ok:
                return rule
            if rule:
                is_valid, msg = self.validate_rule_structure(rule)
                if not is_valid:
                    return command_error(f'规则格式错误: {msg}', code=400)
            data['rule'] = rule

        err = self._parse_required_inputs(data)
        if err:
            return err

        if data.get('api_settings'):
            ok, parsed = parse_json_field(data['api_settings'], 'API配置格式错误: 无效的 JSON 字符串')
            if not ok:
                return parsed
            data['api_settings'] = parsed
        return None

    def _extract_model_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """提取 Dimension 可赋值字段（category_id 空值归一化为 None）。"""
        fields = {}
        for field in self._DIMENSION_MODEL_FIELDS:
            if field in data:
                value = data[field]
                if field == 'category_id' and (value == '' or value is None):
                    value = None
                fields[field] = value
        return fields

    def _apply_dimension_fields(self, dim, data: Dict[str, Any]) -> None:
        """将 payload 中可赋值字段写入已有 Dimension PO（category_id 空值归一化）。"""
        for field, value in self._extract_model_fields(data).items():
            setattr(dim, field, value)

    def _sync_dimension_params(self, dim_id: int, data: Dict[str, Any],
                               algo_type: str, update_mode: bool) -> Optional[Dict[str, Any]]:
        """同步 input/output 参数与 ParamMapping。

        create 模式走 _sync_inputs_and_mappings / _sync_outputs_and_mappings；
        update 模式先删除旧参数再重建（保留对侧方向的参数）。
        返回错误响应 dict 或 None。
        """
        if update_mode:
            raw_required_inputs = data.get('required_inputs')
            required_inputs = None
            if raw_required_inputs:
                ok, required_inputs = parse_json_field(
                    raw_required_inputs, '所需输入配置格式错误: 无效的 JSON 字符串')
                if not ok:
                    return required_inputs

            if required_inputs is not None:
                self.repo.delete_input_params_by_dimension(dim_id)
                self._save_input_params(dim_id, required_inputs)
            self._sync_param_mappings(
                dim_id, data.get('required_inputs'),
                direction='input', algorithm_type=algo_type)

            raw_output_fields = data.get('output_fields')
            if raw_output_fields is not None:
                self.repo.delete_output_params_by_dimension(dim_id)
                output_fields, err = self._parse_output_fields(raw_output_fields)
                if err:
                    return err
                self._save_output_params(dim_id, output_fields)
            self._sync_param_mappings(
                dim_id, data.get('output_fields'),
                direction='output', algorithm_type=algo_type)
            return None

        err = self._sync_inputs_and_mappings(dim_id, data, algo_type)
        if err:
            return err
        return self._sync_outputs_and_mappings(dim_id, data, algo_type)

    # ==================== 子维度继承 ====================

    def _inherit_fields_to_sub_dimensions(self, dim) -> None:
        """主维度将 API 配置字段继承给子维度"""
        sub_dimensions = self.repo.list_sub_dimensions(dim.id)
        for sub_dim in sub_dimensions:
            if not sub_dim.api_url:
                sub_dim.api_url = dim.api_url
            if not sub_dim.api_endpoints:
                sub_dim.api_endpoints = dim.api_endpoints
            if not sub_dim.api_settings:
                sub_dim.api_settings = dim.api_settings
            if not sub_dim.task_type_code:
                sub_dim.task_type_code = dim.task_type_code
            sub_dim.updated_at = now_cst()

    # ==================== 删除 / 批量 ====================

    def delete_dimension(self, dim_id: int) -> Dict[str, Any]:
        """软删除评分维度。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim:
                return command_error('未找到评分维度', code=404)

            self.repo.soft_delete_dimension(dim)
            self.repo.commit()
            self._refresh_stats_cache("删除评分维度")

            # 发布维度配置变更事件，触发 EndpointWorker 热加载
            publish_dimension_config_changed('delete', dim_id=dim_id)

            return command_ok('评分维度已删除')
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除评分维度失败: {e}")
            return command_error(str(e))

    def batch_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """批量操作维度。"""
        ids = data.get('ids')
        action = data.get('action')

        if ids is None or not action:
            return command_error('缺少必要参数: ids, action', code=400)

        try:
            if action == 'delete':
                self.repo.batch_update_dimensions(ids, {'deleted': True})
            elif action == 'enable':
                self.repo.batch_update_dimensions(ids, {'status': True})
            elif action == 'disable':
                self.repo.batch_update_dimensions(ids, {'status': False})
            elif action == 'export':
                return self._export_dimensions(ids)
            else:
                return command_error(f'不支持的操作: {action}', code=400)

            self.repo.commit()
            self._refresh_stats_cache("批量操作")

            # 批量操作变更维度配置，发布事件触发 EndpointWorker 热加载
            publish_dimension_config_changed(f'batch_{action}')

            return command_ok(f'批量操作 {action} 执行成功')
        except Exception as e:
            self.repo.rollback()
            logger.error(f"批量操作失败: {e}")
            return command_error(str(e))

    def _export_dimensions(self, ids) -> Dict[str, Any]:
        """导出维度数据（batch_action 的 export 分支）"""
        dims = self.repo.list_dimensions_by_ids(ids)
        export_data = []
        for d in dims:
            export_data.append({
                'name': d.name,
                'description': d.description,
                'category_id': d.category_id,
                'type': d.type,
                'rule': d.rule,
                'api_url': d.api_url,
                'api_settings': d.api_settings,
                'result_type': d.result_type,
                'score_unit': d.score_unit,
                'status': d.status,
            })
        return command_ok('数据准备就绪', data=export_data)

    # ==================== 评分 / 健康探测 ====================

    def calculate_score(self, dim_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """根据维度评分规则计算分值（委托 Domain Entity ScoringRule.calculate）。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim or dim.deleted:
                return command_error('维度不存在', code=404)

            test_value = data.get('value')
            rule_data = dim.rule

            if not rule_data or 'rules' not in rule_data:
                return command_error('未配置评分规则', code=400)

            from evaluation_service.domain.entities import ScoringRule
            rule = ScoringRule.from_dict(rule_data)
            try:
                score = rule.calculate(test_value)
                return command_ok('分值计算完成', data={'score': score})
            except Exception as e:
                return command_error(f'规则计算出错: {str(e)}', code=400)
        except Exception as e:
            logger.error(f"计算分值失败: {e}")
            return command_error(str(e))

    def health_check(self, dim_id: int) -> Dict[str, Any]:
        """对维度配置的 API 端点进行健康探测（委托 Infrastructure 层 EndpointHealthChecker）。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim or dim.deleted:
                return command_error('维度不存在', code=404)

            if not (dim.api_endpoints and isinstance(dim.api_endpoints, list) and len(dim.api_endpoints) > 0):
                dim.api_status = 'offline'
                self.repo.commit()
                return command_error('未配置任何 API 端点', code=400)

            # P1-2: HTTP 探测委托 Infrastructure 层，Application 不直接 import requests
            from evaluation_service.infrastructure.evaluation_api.health_checker import (
                endpoint_health_checker,
            )
            probe = endpoint_health_checker.check_endpoints(
                endpoints=dim.api_endpoints,
                api_settings=dim.api_settings,
            )

            dim.api_status = 'online' if probe['all_online'] else 'offline'
            self.repo.commit()

            return command_ok('健康探测完成', data={
                'results': probe['results'],
                'overall_status': dim.api_status,
            })
        except Exception as e:
            self.repo.rollback()
            logger.error(f"健康探测失败: {e}")
            return command_error(str(e))

    # ==================== 跨服务数据删除 ====================

    def delete_dimension_results_by_result_ids(self, result_ids: list) -> Dict[str, Any]:
        """按 result_id 列表批量删除维度评估记录（供 gRPC servicer 调用）。"""
        try:
            from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
                evaluation_dimension_repository,
            )
            count = evaluation_dimension_repository.delete_scores_by_result_ids(result_ids)
            return command_ok('', data={'deleted': count})
        except Exception as e:
            logger.error(f"批量删除维度评估记录失败: {e}")
            return command_error(str(e))
