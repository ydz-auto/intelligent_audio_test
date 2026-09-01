# -*- coding: utf-8 -*-
"""评估维度参数读写 Mixin（从 evaluation_command_service.py 拆分，P4-4）。

提取 create_dimension / update_dimension 中高度重复的
required_inputs / output_fields / 关联算法 / body_template 四段处理逻辑，
按项目既有 Mixin 组合模式复用（消除大段重复代码）。
"""
import json
from typing import Any, Dict

from evaluation_service.application.commands._command_utils import (
    command_error,
    get_default_algorithm_type,
)


class DimensionParamsMixin:
    """维度参数读写：输入参数 / 输出字段 / ParamMapping / body_template 同步"""

    def _extract_param_codes(self, required_inputs) -> list:
        """从 required_inputs 列表提取 param_code 集合（兼容 key 键）"""
        param_codes = []
        for inp in required_inputs or []:
            pc = inp.get('param_code', inp.get('key', ''))
            if pc:
                param_codes.append(pc)
        return param_codes

    def _save_input_params(self, dim_id: int, required_inputs) -> Dict[str, Any]:
        """保存输入参数到 EvaluationDimensionParam（gRPC）。返回错误 dict 或 None。"""
        if not isinstance(required_inputs, list):
            return None
        for idx, inp in enumerate(required_inputs):
            param_code = inp.get('param_code', inp.get('key', ''))
            if not param_code:
                continue
            self.repo.add_dimension_param({
                'dimension_id': dim_id,
                'param_code': param_code,
                'param_name': inp.get('param_name', inp.get('label', '')),
                'label': inp.get('label', inp.get('param_name', '')),
                'field_type': inp.get('field_type', inp.get('type', 'text')),
                'required': inp.get('required', True),
                'default_value': json.dumps(inp.get('default_value')) if inp.get('default_value') else None,
                'help_text': inp.get('help_text', inp.get('description', '')),
                'ui_order': inp.get('ui_order', idx),
            })
        return None

    def _save_output_params(self, dim_id: int, output_fields) -> Dict[str, Any]:
        """保存输出字段到 EvaluationDimensionParam（gRPC）。返回错误 dict 或 None。"""
        if not isinstance(output_fields, list):
            return None
        for idx, outp in enumerate(output_fields):
            param_code = outp.get('param_code', '')
            if not param_code:
                continue
            self.repo.add_dimension_param({
                'dimension_id': dim_id,
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
        return None

    def _parse_required_inputs(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析 required_inputs（JSON 字符串兼容）。返回错误 dict 或 None。"""
        raw = data.get('required_inputs')
        if not raw:
            return None
        ok, parsed = self._parse_json_value(raw, '所需输入配置格式错误: 无效的 JSON 字符串')
        if not ok:
            return parsed
        data['required_inputs'] = parsed
        return None

    def _parse_output_fields(self, raw_output_fields) -> Dict[str, Any]:
        """解析 output_fields（JSON 字符串兼容）。返回 (parsed, 错误dict或None)。"""
        if not raw_output_fields:
            return None, None
        ok, parsed = self._parse_json_value(raw_output_fields, '输出字段配置格式错误: 无效的 JSON 字符串')
        if not ok:
            return None, parsed
        return parsed, None

    def _parse_json_value(self, value, error_message: str):
        """解析可能为 JSON 字符串的值。返回 (ok, parsed)。"""
        if not isinstance(value, str):
            return True, value
        try:
            return True, json.loads(value)
        except json.JSONDecodeError:
            return False, command_error(error_message, code=400)

    def _sync_inputs_and_mappings(self, dim_id: int, data: Dict[str, Any], algo_type: str):
        """同步输入参数 + ParamMapping(input)。返回错误 dict 或 None。"""
        raw_required_inputs = data.get('required_inputs')
        if raw_required_inputs:
            if isinstance(raw_required_inputs, str):
                ok, parsed = self._parse_json_value(raw_required_inputs, '所需输入配置格式错误: 无效的 JSON 字符串')
                if not ok:
                    return parsed
                raw_required_inputs = parsed
            self._save_input_params(dim_id, raw_required_inputs)

        self._sync_param_mappings(
            dim_id, data.get('required_inputs'),
            direction='input', algorithm_type=algo_type,
        )
        return None

    def _sync_outputs_and_mappings(self, dim_id: int, data: Dict[str, Any], algo_type: str):
        """同步输出字段 + ParamMapping(output)。返回错误 dict 或 None。"""
        raw_output_fields = data.get('output_fields')
        if raw_output_fields:
            if isinstance(raw_output_fields, str):
                ok, parsed = self._parse_json_value(raw_output_fields, '输出字段配置格式错误: 无效的 JSON 字符串')
                if not ok:
                    return parsed
                raw_output_fields = parsed
            self._save_output_params(dim_id, raw_output_fields)

        self._sync_param_mappings(
            dim_id, data.get('output_fields'),
            direction='output', algorithm_type=algo_type,
        )
        return None

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

    def _sync_body_template(self, api_settings: Dict, param_codes: list) -> Dict:
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
        placeholder_re = self._placeholder_re
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
            created_param_codes = self._extract_param_codes(required_inputs)
            if created_param_codes:
                current_api_settings = dim.api_settings or {}
                dim.api_settings = self._sync_body_template(current_api_settings, created_param_codes)

    @property
    def _placeholder_re(self):
        """{{param_code}} 占位符匹配正则（延迟编译，避免模块级 import re）"""
        import re
        return re.compile(r'^\{\{(\w+)\}\}$')
