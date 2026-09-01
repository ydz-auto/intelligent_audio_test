# -*- coding: utf-8 -*-
"""维度评估结果解析混入

负责单个维度的评估结果解析（响应提取优先级、打分），
以及结果维度完成状态检查。
"""
from evaluation_service.domain.services.evaluation_utils import extract_by_path, calculate_score


class ParseDimensionMixin:
    """维度评估结果解析方法"""

    def parse_dimension_result(self, resp_data, dim_data):
        """
        解析单个维度的评估结果。

        结果提取优先级：
        1. EvaluationDimensionParam 表中 output_role=main 的 field_path
        2. output 参数中第一个有 field_path 的字段
        3. api_settings.response_mapping
        4. 维度名兜底
        """
        dim_name = dim_data['name']
        dim_settings = dim_data['api_settings'] or {}
        mapping = dim_settings.get('response_mapping')

        # 1. 提取原始值 - 适配WER/SER API响应格式
        raw_value = None

        # 首先检查是否是新的API响应格式（包含code、msg、data字段）
        if isinstance(resp_data, dict):
            # 检查是否是完整的API响应格式
            if 'code' in resp_data and 'data' in resp_data:
                # 提取data字段作为实际的结果数据
                resp_data = resp_data.get('data', {})

            # 检查是否包含result字段（WER/SER API的标准格式）
            if 'result' in resp_data:
                resp_data = resp_data.get('result', {})

        # 优先从 output 参数中 output_role=main 的 field_path 提取
        output_params = dim_data.get('output_params') or []
        main_field_path = self._pick_main_field_path(output_params)

        # 兼容旧字段 output_field_path
        if not main_field_path:
            main_field_path = dim_data.get('output_field_path')

        if main_field_path:
            raw_value = extract_by_path(resp_data, main_field_path)

        # 其次用 api_settings.response_mapping
        if raw_value is None and mapping:
            raw_value = extract_by_path(resp_data, mapping)

        # 兜底逻辑：用维度名匹配
        if raw_value is None:
            raw_value = self._fallback_extract(resp_data, dim_name)

        # 2. 计算得分
        score = calculate_score(raw_value, dim_data['rule'])

        return raw_value, score

    @staticmethod
    def _pick_main_field_path(output_params):
        """从 output 参数中选取主字段路径（优先 output_role=main，兜底第一个有 field_path 的）"""
        main_field_path = None
        for p in output_params:
            if p.get('output_role') == 'main' and p.get('field_path'):
                main_field_path = p['field_path']
                break

        # 兜底：取第一个有 field_path 的 output 参数
        if not main_field_path:
            for p in output_params:
                if p.get('field_path'):
                    main_field_path = p['field_path']
                    break
        return main_field_path

    @staticmethod
    def _fallback_extract(resp_data, dim_name):
        """维度名兜底提取原始值"""
        if isinstance(resp_data, dict) and dim_name in resp_data:
            return resp_data.get(dim_name)
        if isinstance(resp_data, dict) and 'results' in resp_data:
            return resp_data['results'].get(dim_name, {}).get('value')
        # 尝试直接使用响应值
        return list(resp_data.values())[0] if resp_data and isinstance(resp_data, dict) else None

    def check_all_dimensions_completed(self, result_id, task_id=None):
        """
        检查一个测试结果的所有维度是否都已完成评估
        """
        if not result_id:
            return True

        try:
            # 使用本地会话
            from shared.models.database import get_db_session
            from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
            from shared.utils.status_constants import ACTIVE_EVALUATION_STATUSES
            local_db_session = get_db_session()
            try:
                # 查询该结果的所有维度评估记录
                dimensions = local_db_session.query(TestResultDimension).filter_by(test_result_id=result_id).all()

                if not dimensions:
                    return True

                # 检查是否所有维度都已经不是进行中状态
                all_completed = True
                for dim in dimensions:
                    if dim.evaluation_status in ACTIVE_EVALUATION_STATUSES:
                        all_completed = False
                        break

                return all_completed
            finally:
                local_db_session.close()
        except Exception as e:
            self._log(level='ERROR', content=f"检查维度完成状态失败: {str(e)}", task_id=task_id)
            return False
