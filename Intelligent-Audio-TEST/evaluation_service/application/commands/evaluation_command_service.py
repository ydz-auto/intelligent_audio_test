# -*- coding: utf-8 -*-
"""EvaluationCommandService — 评估维度写操作应用服务（CQRS Command 侧）。

承担 Category CRUD + Dimension 的
创建/更新/删除/批量操作/评分计算/健康探测，以及内部辅助方法。

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 self.repo 调用 Repository，不直连 DB
- 保留软删除模式（deleted=True + deleted_at）
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.utils.query_utils import now_cst
from evaluation_service.domain.repositories.evaluation_repository_abc import (
    EvaluationRepositoryABC,
)
from evaluation_service.infrastructure.persistence.evaluation_repository import (
    evaluation_repository,
)

logger = logging.getLogger(__name__)

# Dimension 模型可赋值字段
_DIMENSION_MODEL_FIELDS = [
    'name', 'keywords', 'description', 'category_id', 'api_url',
    'api_endpoints', 'type', 'result_type', 'result_min',
    'result_max', 'decimal_places', 'weight', 'estimated_exec_time',
    'rule', 'api_settings', 'status', 'api_status', 'score_unit',
    'dimension_type', 'parent_dimension_id', 'task_type_code',
    'statistic_method',
]

# 评分规则合法条件（已移至 Domain Entity ScoringRule._VALID_RULE_CONDITIONS）


class EvaluationCommandService:
    """评估维度写操作应用服务（CQRS Command）。"""

    def __init__(self, repo: EvaluationRepositoryABC = None):
        self.repo = repo or evaluation_repository

    # ==================== Category 写操作 ====================

    def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建分类。"""
        name = data.get('name')
        if not name:
            return {'success': False, 'message': '分类名称不能为空', 'code': 400}

        try:
            existing = self.repo.get_category_by_name(name)
            if existing:
                return {'success': False, 'message': f'分类名称已存在: {name}', 'code': 400}

            new_cat = self.repo.create_category({
                'name': name,
                'description': data.get('description'),
                'icon': data.get('icon'),
            })
            self.repo.commit()

            return {
                'success': True,
                'message': '分类创建成功',
                'data': {'id': new_cat.id},
                'code': 201,
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建分类失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def update_category(self, cat_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新分类。"""
        try:
            cat = self.repo.get_category_by_id(cat_id)
            if not cat or cat.deleted:
                return {'success': False, 'message': '未找到分类', 'code': 404}

            if data.get('name') is not None:
                name = data['name']
                existing = self.repo.get_category_by_name(name)
                if existing and existing.id != cat.id:
                    return {'success': False, 'message': f'分类名称已存在: {name}', 'code': 400}
                cat.name = name

            if data.get('description') is not None:
                cat.description = data['description']
            if data.get('icon') is not None:
                cat.icon = data['icon']

            cat.updated_at = now_cst()
            self.repo.commit()

            return {'success': True, 'message': '分类更新成功'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新分类失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def delete_category(self, cat_id: int) -> Dict[str, Any]:
        """软删除分类。"""
        try:
            cat = self.repo.get_category_by_id(cat_id)
            if not cat or cat.deleted:
                return {'success': False, 'message': '未找到分类', 'code': 404}

            now = now_cst()
            cat.deleted = True
            cat.deleted_at = now
            cat.updated_at = now
            self.repo.commit()

            return {'success': True, 'message': '分类已删除'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除分类失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== Dimension 写操作 ====================

    def create_dimension(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建评分维度。"""
        if not data or 'name' not in data:
            return {'success': False, 'message': '缺少名称(name)', 'code': 400}

        # 解析 rule / required_inputs / api_settings JSON 字符串
        rule = data.get('rule')
        if rule:
            try:
                if isinstance(rule, str):
                    rule = json.loads(rule)
            except json.JSONDecodeError:
                return {'success': False, 'message': '规则格式错误: 无效的 JSON 字符串', 'code': 400}
            if rule:
                is_valid, msg = self.validate_rule_structure(rule)
                if not is_valid:
                    return {'success': False, 'message': f'规则格式错误: {msg}', 'code': 400}
            data['rule'] = rule

        required_inputs = data.get('required_inputs')
        if required_inputs:
            try:
                if isinstance(required_inputs, str):
                    required_inputs = json.loads(required_inputs)
                data['required_inputs'] = required_inputs
            except json.JSONDecodeError:
                return {'success': False, 'message': '所需输入配置格式错误: 无效的 JSON 字符串', 'code': 400}

        api_settings = data.get('api_settings')
        if api_settings:
            try:
                if isinstance(api_settings, str):
                    api_settings = json.loads(api_settings)
                data['api_settings'] = api_settings
            except json.JSONDecodeError:
                return {'success': False, 'message': 'API配置格式错误: 无效的 JSON 字符串', 'code': 400}

        try:
            # 1. 创建 Dimension 记录
            create_data = {}
            for field in _DIMENSION_MODEL_FIELDS:
                if field in data:
                    value = data[field]
                    if field == 'category_id' and (value == '' or value is None):
                        value = None
                    create_data[field] = value

            new_dim = self.repo.create_dimension(create_data)

            # 2. 保存关联算法（gRPC 同步：先清空再插入）
            raw_associated_algorithms = (
                data.get('associatedAlgorithms')
                or data.get('associated_algorithms')
                or []
            )
            relations = []
            if raw_associated_algorithms:
                for algo in raw_associated_algorithms:
                    if isinstance(algo, dict):
                        algo_type = algo.get('algorithmType') or algo.get('algorithm_type')
                        is_default = algo.get('isDefault', False)
                        weight = algo.get('weight', 1.0)
                    else:
                        algo_type = algo
                        is_default = False
                        weight = 1.0
                    if algo_type:
                        relations.append({
                            'algorithm_type': algo_type,
                            'is_default': is_default,
                            'weight': weight,
                        })
            self.repo.sync_relations(new_dim.id, relations)

            # 3. 保存 required_inputs 到 EvaluationDimensionParam
            raw_required_inputs = data.get('required_inputs')
            if raw_required_inputs:
                if isinstance(raw_required_inputs, str):
                    try:
                        required_inputs_parsed = json.loads(raw_required_inputs)
                    except json.JSONDecodeError:
                        return {'success': False, 'message': '所需输入配置格式错误: 无效的 JSON 字符串', 'code': 400}
                else:
                    required_inputs_parsed = raw_required_inputs

                if isinstance(required_inputs_parsed, list):
                    for idx, inp in enumerate(required_inputs_parsed):
                        param_code = inp.get('param_code', inp.get('key', ''))
                        if not param_code:
                            continue
                        self.repo.add_dimension_param({
                            'dimension_id': new_dim.id,
                            'param_code': param_code,
                            'param_name': inp.get('param_name', inp.get('label', '')),
                            'label': inp.get('label', inp.get('param_name', '')),
                            'field_type': inp.get('field_type', inp.get('type', 'text')),
                            'required': inp.get('required', True),
                            'default_value': json.dumps(inp.get('default_value')) if inp.get('default_value') else None,
                            'help_text': inp.get('help_text', inp.get('description', '')),
                            'ui_order': inp.get('ui_order', idx),
                        })

            # 同步 ParamMapping: input
            _create_algo_type = self._get_default_algorithm_type(raw_associated_algorithms)
            self._sync_param_mappings(
                new_dim.id, data.get('required_inputs'),
                direction='input', algorithm_type=_create_algo_type,
            )

            # 4. 保存 output_fields 到 EvaluationDimensionParam
            raw_output_fields = data.get('output_fields')
            if raw_output_fields:
                if isinstance(raw_output_fields, str):
                    try:
                        output_fields = json.loads(raw_output_fields)
                    except json.JSONDecodeError:
                        return {'success': False, 'message': '输出字段配置格式错误: 无效的 JSON 字符串', 'code': 400}
                else:
                    output_fields = raw_output_fields

                if isinstance(output_fields, list):
                    for idx, outp in enumerate(output_fields):
                        param_code = outp.get('param_code', '')
                        if not param_code:
                            continue
                        self.repo.add_dimension_param({
                            'dimension_id': new_dim.id,
                            'param_code': param_code,
                            'param_name': outp.get('param_name', outp.get('label', '')),
                            'label': outp.get('label', outp.get('param_name', '')),
                            'field_type': outp.get('field_type', 'number'),
                            'param_direction': 'output',
                            'field_path': outp.get('field_path', param_code),
                            'agg_role': outp.get('agg_role'),
                            'output_role': outp.get('output_role', 'main'),
                            'visible_in_report': outp.get('visible_in_report', True),
                            'required': False,
                            'default_value': json.dumps(outp.get('default_value')) if outp.get('default_value') else None,
                            'help_text': outp.get('help_text', ''),
                            'ui_order': outp.get('ui_order', idx),
                        })

            # 同步 ParamMapping: output
            self._sync_param_mappings(
                new_dim.id, data.get('output_fields'),
                direction='output', algorithm_type=_create_algo_type,
            )

            # 5. 同步 body_template
            self._sync_dimension_body_template(new_dim, data)

            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                pass

            return {
                'success': True,
                'message': '评分维度创建成功',
                'data': {'id': new_dim.id},
                'code': 201,
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建评分维度失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def update_dimension(self, dim_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新评分维度。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim or dim.deleted:
                return {'success': False, 'message': '未找到评分维度', 'code': 404}

            # 解析 rule
            if 'rule' in data:
                rule = data['rule']
                try:
                    if isinstance(rule, str):
                        rule = json.loads(rule)
                except json.JSONDecodeError:
                    return {'success': False, 'message': '规则格式错误: 无效的 JSON 字符串', 'code': 400}
                if rule:
                    is_valid, msg = self.validate_rule_structure(rule)
                    if not is_valid:
                        return {'success': False, 'message': f'规则格式错误: {msg}', 'code': 400}
                data['rule'] = rule

            # 解析 required_inputs
            raw_required_inputs = data.get('required_inputs')
            required_inputs = None
            if raw_required_inputs:
                try:
                    if isinstance(raw_required_inputs, str):
                        required_inputs = json.loads(raw_required_inputs)
                    else:
                        required_inputs = raw_required_inputs
                except json.JSONDecodeError:
                    return {'success': False, 'message': '所需输入配置格式错误: 无效的 JSON 字符串', 'code': 400}

            # 解析 api_settings
            api_settings = data.get('api_settings')
            if api_settings:
                try:
                    if isinstance(api_settings, str):
                        api_settings = json.loads(api_settings)
                    data['api_settings'] = api_settings
                except json.JSONDecodeError:
                    return {'success': False, 'message': 'API配置格式错误: 无效的 JSON 字符串', 'code': 400}

            # 2. 更新基本字段 + 关联算法
            for field in _DIMENSION_MODEL_FIELDS:
                if field in data:
                    value = data[field]
                    if field == 'category_id' and (value == '' or value is None):
                        value = None
                    setattr(dim, field, value)

            raw_associated_algorithms = (
                data.get('associatedAlgorithms')
                or data.get('associated_algorithms')
            )
            if raw_associated_algorithms is not None:
                # gRPC 同步：先清空旧关联再插入新关联
                relations = []
                if isinstance(raw_associated_algorithms, list):
                    for algo in raw_associated_algorithms:
                        if isinstance(algo, dict):
                            algo_type = algo.get('algorithmType') or algo.get('algorithm_type')
                            is_default = algo.get('isDefault', False)
                            weight = algo.get('weight', 1.0)
                        else:
                            algo_type = algo
                            is_default = False
                            weight = 1.0
                        if algo_type:
                            relations.append({
                                'algorithm_type': algo_type,
                                'is_default': is_default,
                                'weight': weight,
                            })
                self.repo.sync_relations(dim.id, relations)

            _update_algo_type = self._get_default_algorithm_type(raw_associated_algorithms)

            # 3. 更新 required_inputs
            if required_inputs is not None:
                # 只删除旧的 input 参数，保留 output 参数
                self.repo.delete_input_params_by_dimension(dim.id)

                # 添加新的参数
                if isinstance(required_inputs, list):
                    for idx, inp in enumerate(required_inputs):
                        param_code = inp.get('param_code', inp.get('key', ''))
                        if not param_code:
                            continue
                        self.repo.add_dimension_param({
                            'dimension_id': dim.id,
                            'param_code': param_code,
                            'param_name': inp.get('param_name', inp.get('label', '')),
                            'label': inp.get('label', inp.get('param_name', '')),
                            'field_type': inp.get('field_type', inp.get('type', 'text')),
                            'param_direction': 'input',
                            'required': inp.get('required', True),
                            'default_value': json.dumps(inp.get('default_value')) if inp.get('default_value') else None,
                            'help_text': inp.get('help_text', inp.get('description', '')),
                            'ui_order': inp.get('ui_order', idx),
                        })

            # 同步 ParamMapping: input
            self._sync_param_mappings(
                dim.id, data.get('required_inputs'),
                direction='input', algorithm_type=_update_algo_type,
            )

            # 4. 更新 output_fields
            raw_output_fields = data.get('output_fields')
            if raw_output_fields is not None:
                # 只删除旧的 output 参数
                self.repo.delete_output_params_by_dimension(dim.id)

                try:
                    if isinstance(raw_output_fields, str):
                        output_fields = json.loads(raw_output_fields)
                    else:
                        output_fields = raw_output_fields
                except json.JSONDecodeError:
                    return {'success': False, 'message': '输出字段配置格式错误: 无效的 JSON 字符串', 'code': 400}

                if isinstance(output_fields, list):
                    for idx, outp in enumerate(output_fields):
                        param_code = outp.get('param_code', '')
                        if not param_code:
                            continue
                        self.repo.add_dimension_param({
                            'dimension_id': dim.id,
                            'param_code': param_code,
                            'param_name': outp.get('param_name', outp.get('label', '')),
                            'label': outp.get('label', outp.get('param_name', '')),
                            'field_type': outp.get('field_type', 'number'),
                            'param_direction': 'output',
                            'field_path': outp.get('field_path', param_code),
                            'agg_role': outp.get('agg_role'),
                            'output_role': outp.get('output_role', 'main'),
                            'visible_in_report': outp.get('visible_in_report', True),
                            'required': False,
                            'default_value': json.dumps(outp.get('default_value')) if outp.get('default_value') else None,
                            'help_text': outp.get('help_text', ''),
                            'ui_order': outp.get('ui_order', idx),
                        })

            # 同步 ParamMapping: output
            self._sync_param_mappings(
                dim.id, data.get('output_fields'),
                direction='output', algorithm_type=_update_algo_type,
            )

            # 5. 同步 body_template
            if required_inputs is not None and isinstance(required_inputs, list):
                updated_param_codes = []
                for inp in required_inputs:
                    pc = inp.get('param_code', inp.get('key', ''))
                    if pc:
                        updated_param_codes.append(pc)
                if updated_param_codes:
                    current_api_settings = dim.api_settings or {}
                    dim.api_settings = self._sync_body_template(current_api_settings, updated_param_codes)

            dim.updated_at = now_cst()

            # 6. 更新子维度（主维度继承）
            if dim.dimension_type == 'main':
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

            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                pass

            return {'success': True, 'message': '评分维度更新成功'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新评分维度失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def delete_dimension(self, dim_id: int) -> Dict[str, Any]:
        """软删除评分维度。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim:
                return {'success': False, 'message': '未找到评分维度', 'code': 404}

            self.repo.soft_delete_dimension(dim)
            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                pass

            return {'success': True, 'message': '评分维度已删除'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除评分维度失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def batch_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """批量操作维度。"""
        ids = data.get('ids')
        action = data.get('action')

        if ids is None or not action:
            return {'success': False, 'message': '缺少必要参数: ids, action', 'code': 400}

        try:
            if action == 'delete':
                self.repo.batch_update_dimensions(ids, {'deleted': True})
            elif action == 'enable':
                self.repo.batch_update_dimensions(ids, {'status': True})
            elif action == 'disable':
                self.repo.batch_update_dimensions(ids, {'status': False})
            elif action == 'export':
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
                return {'success': True, 'message': '数据准备就绪', 'data': export_data}
            else:
                return {'success': False, 'message': f'不支持的操作: {action}', 'code': 400}

            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                pass

            return {'success': True, 'message': f'批量操作 {action} 执行成功'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"批量操作失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def calculate_score(self, dim_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """根据维度评分规则计算分值（委托 Domain Entity ScoringRule.calculate）。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim or dim.deleted:
                return {'success': False, 'message': '维度不存在', 'code': 404}

            test_value = data.get('value')
            rule_data = dim.rule

            if not rule_data or 'rules' not in rule_data:
                return {'success': False, 'message': '未配置评分规则', 'code': 400}

            from evaluation_service.domain.entities import ScoringRule
            rule = ScoringRule.from_dict(rule_data)
            try:
                score = rule.calculate(test_value)
                return {
                    'success': True,
                    'message': '分值计算完成',
                    'data': {'score': score},
                }
            except Exception as e:
                return {'success': False, 'message': f'规则计算出错: {str(e)}', 'code': 400}
        except Exception as e:
            logger.error(f"计算分值失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def health_check(self, dim_id: int) -> Dict[str, Any]:
        """对维度配置的 API 端点进行健康探测（委托 Infrastructure 层 EndpointHealthChecker）。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim or dim.deleted:
                return {'success': False, 'message': '维度不存在', 'code': 404}

            if not (dim.api_endpoints and isinstance(dim.api_endpoints, list) and len(dim.api_endpoints) > 0):
                dim.api_status = 'offline'
                self.repo.commit()
                return {'success': False, 'message': '未配置任何 API 端点', 'code': 400}

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

            return {
                'success': True,
                'message': '健康探测完成',
                'data': {
                    'results': probe['results'],
                    'overall_status': dim.api_status,
                },
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"健康探测失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 内部辅助 ====================

    def _sync_body_template(self, api_settings: Dict, param_codes: List[str]) -> Dict:
        """根据 param_codes 同步 api_settings 中的 body_template。"""
        if not param_codes:
            return api_settings

        if api_settings is None:
            api_settings = {}
        if not isinstance(api_settings, dict):
            return api_settings

        body_template = api_settings.get('body_template')

        # 解析 body_template 为 dict
        if body_template is None:
            bt_dict = {}
        elif isinstance(body_template, str):
            try:
                bt_dict = json.loads(body_template) if body_template.strip() else {}
            except json.JSONDecodeError:
                bt_dict = {}
        elif isinstance(body_template, dict):
            bt_dict = dict(body_template)
        else:
            bt_dict = {}

        param_set = set(param_codes)

        # 移除已删除参数对应的占位符（值为 {{xxx}} 且 xxx 不在 param_set 中）
        placeholder_re = re.compile(r'^\{\{(\w+)\}\}$')
        keys_to_remove = []
        for key, value in bt_dict.items():
            if isinstance(value, str):
                match = placeholder_re.match(value)
                if match and match.group(1) not in param_set:
                    keys_to_remove.append(key)
        for key in keys_to_remove:
            del bt_dict[key]

        # 添加新参数的占位符
        for code in param_codes:
            if code not in bt_dict:
                bt_dict[code] = f"{{{{{code}}}}}"

        # 写回 body_template（保持与原始类型一致）
        if isinstance(body_template, str):
            api_settings['body_template'] = json.dumps(bt_dict, ensure_ascii=False)
        else:
            api_settings['body_template'] = bt_dict

        return api_settings

    def _get_default_algorithm_type(self, associated_algorithms) -> str:
        """从关联算法列表取默认（或第一个）算法的 type，回落到 voice_llm。"""
        if not associated_algorithms:
            return 'voice_llm'
        for algo in associated_algorithms:
            if isinstance(algo, dict):
                if algo.get('isDefault'):
                    return algo.get('algorithmType') or algo.get('algorithm_type') or 'voice_llm'
        # 没有标记默认的，取第一个
        for algo in associated_algorithms:
            if isinstance(algo, dict):
                return algo.get('algorithmType') or algo.get('algorithm_type') or 'voice_llm'
            return algo or 'voice_llm'
        return 'voice_llm'

    def _sync_param_mappings(
        self,
        dimension_id: int,
        params,
        direction: str = 'output',
        algorithm_type: str = 'voice_llm',
    ) -> None:
        """同步 ParamMapping：当评估维度的输入/输出字段变更时，
        自动为该维度创建/更新/删除对应的 ParamMapping 记录。

        委托 algorithm_service gRPC（SyncParamMappings），由 algorithm_service
        在其本地事务内完成 ParamMapping 的创建/更新/软删除。
        """
        if params is None:
            return

        # params 可以是 list 或 JSON 字符串，直接传给 gRPC 端处理
        self.repo.sync_param_mappings(dimension_id, params, direction, algorithm_type)

    def _sync_dimension_body_template(self, dim, data: Dict[str, Any]) -> None:
        """同步 body_template：根据 required_inputs 中的 param_code 更新 api_settings。"""
        required_inputs = data.get('required_inputs')
        # 兼容字符串情况
        if isinstance(required_inputs, str):
            try:
                required_inputs = json.loads(required_inputs)
            except json.JSONDecodeError:
                required_inputs = None

        if required_inputs and isinstance(required_inputs, list):
            created_param_codes = []
            for inp in required_inputs:
                pc = inp.get('param_code', inp.get('key', ''))
                if pc:
                    created_param_codes.append(pc)
            if created_param_codes:
                current_api_settings = dim.api_settings or {}
                dim.api_settings = self._sync_body_template(current_api_settings, created_param_codes)

    def validate_rule_structure(self, rule) -> tuple:
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


    def delete_dimension_results_by_result_ids(self, result_ids: list) -> Dict[str, Any]:
        """按 result_id 列表批量删除维度评估记录（供 gRPC servicer 调用）。"""
        try:
            from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
                evaluation_dimension_repository,
            )
            count = evaluation_dimension_repository.delete_scores_by_result_ids(result_ids)
            return {'success': True, 'message': '', 'data': {'deleted': count}}
        except Exception as e:
            logger.error(f"批量删除维度评估记录失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}


# 模块级单例
evaluation_command_service = EvaluationCommandService()
