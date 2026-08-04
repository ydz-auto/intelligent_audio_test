"""维度数据加载混入：从数据库加载维度并格式化为 dim_dict"""
from shared.models.models import Dimension
from shared.models.database import db


class DimensionLoaderMixin:
    """从数据库加载维度数据并构建 dim_dict 列表"""

    def _load_dimension_data(self, unique_dimension_ids, task_id, test_case_id, test_case):
        """从数据库加载维度数据并构建 dim_dict 列表"""
        local_db_session = db.session()
        try:
            dimensions, output_param_map, input_param_map = self._query_dimensions(
                unique_dimension_ids, local_db_session
            )
            if not dimensions:
                self._log(level='WARNING', content=f"用例 {test_case.name} 关联的维度都不可用，跳过评估", task_id=task_id, test_case_id=test_case_id)
                return []

            dimension_data_list = self._format_dimension_data(
                dimensions, output_param_map, input_param_map
            )

            self._log(
                level='DEBUG',
                content=f"[维度数据] 用例 {test_case.name} 加载的维度列表: {[{ 'id': d['id'], 'name': d['name'], 'task_type_code': d.get('task_type_code'), 'api_url': d.get('api_url'), 'api_settings_keys': list(d.get('api_settings', {}).keys()) if d.get('api_settings') else [] } for d in dimension_data_list]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            return dimension_data_list
        finally:
            local_db_session.close()

    def _query_dimensions(self, unique_dimension_ids, local_db_session):
        """查询维度数据并预加载 output/input 参数

        Returns:
            tuple: (dimensions, output_param_map, input_param_map)
        """
        dimensions = local_db_session.query(Dimension).filter(
            Dimension.id.in_(unique_dimension_ids),
            Dimension.status == True
        ).all()
        if not dimensions:
            return [], {}, {}

        # 预加载所有维度的 output 和 input 参数，避免 N+1 查询
        dim_ids = [dim.id for dim in dimensions]
        output_param_map = {}
        input_param_map = {}
        if dim_ids:
            from shared.models.algorithm_models import EvaluationDimensionParam
            all_params = EvaluationDimensionParam.query.filter(
                EvaluationDimensionParam.dimension_id.in_(dim_ids),
                EvaluationDimensionParam.deleted == False
            ).all()
            for p in all_params:
                if p.param_direction == 'output':
                    output_param_map.setdefault(p.dimension_id, []).append({
                        'param_code': p.param_code,
                        'field_path': p.field_path,
                        'field_type': p.field_type,
                        'agg_role': p.agg_role,
                        'output_role': p.output_role,
                        'visible_in_report': p.visible_in_report if p.visible_in_report is not None else True
                    })
                elif p.param_direction == 'input':
                    input_param_map.setdefault(p.dimension_id, []).append({
                        'param_code': p.param_code,
                        'default_value': p.default_value,
                        'field_type': p.field_type,
                        'required': p.required
                    })

        return dimensions, output_param_map, input_param_map

    def _format_dimension_data(self, dimensions, output_param_map, input_param_map):
        """将维度 ORM 对象格式化为 dim_dict 列表"""
        dimension_data_list = []
        for dim in dimensions:
            dim_outputs = output_param_map.get(dim.id, [])
            output_field_path = dim_outputs[0]['field_path'] if dim_outputs else None

            dim_dict = {
                'id': dim.id,
                'name': dim.name,
                'keywords': dim.keywords,
                'rule': dim.rule,
                'api_endpoints': dim.api_endpoints,
                'api_settings': dim.api_settings,
                'api_url': dim.api_url,
                'dimension_type': getattr(dim, 'dimension_type', 'main'),
                'parent_dimension_id': getattr(dim, 'parent_dimension_id', None),
                'task_type_code': getattr(dim, 'task_type_code', None),
                'output_field_path': output_field_path,
                'output_params': dim_outputs,
                'input_params': input_param_map.get(dim.id, [])
            }

            # 子维度继承父维度的API配置
            if getattr(dim, 'dimension_type', 'main') == 'sub' and not dim_dict.get('api_endpoints') and not dim_dict.get('api_url'):
                parent_dim = getattr(dim, 'parent_dimension', None)
                if parent_dim:
                    for k in ['api_endpoints', 'api_url', 'api_settings', 'task_type_code']:
                        if not dim_dict.get(k):
                            dim_dict[k] = getattr(parent_dim, k, None)

            dimension_data_list.append(dim_dict)

        return dimension_data_list
