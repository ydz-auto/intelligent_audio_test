"""维度数据加载混入：通过 Repository 加载维度并格式化为 dim_dict

P0 DDD 改造：移除模块级 infrastructure/acl import，改用方法内延迟导入。
"""


class DimensionLoaderMixin:
    """从 Repository 加载维度数据并构建 dim_dict 列表"""

    def _load_dimension_data(self, unique_dimension_ids, task_id, test_case_id, test_case):
        """从 Repository 加载维度数据并构建 dim_dict 列表

        P1.4: test_case 现为 TestCaseDetailDTO（来自 case_loader 的 gRPC 调用）
        P5+DOMAIN: 通过 EvaluationDimensionRepository 加载维度聚合根，
                   不再直接 get_db_session() 查询 Dimension PO。
        """
        # P1.4: test_case 是 TestCaseDetailDTO
        case_name = getattr(test_case, 'name', None) or str(test_case_id)

        dimensions, output_param_map, input_param_map = self._query_dimensions(
            unique_dimension_ids
        )
        if not dimensions:
            self._log(level='WARNING', content=f"用例 {case_name} 关联的维度都不可用，跳过评估", task_id=task_id, test_case_id=test_case_id)
            return []

        dimension_data_list = self._format_dimension_data(
            dimensions, output_param_map, input_param_map
        )

        self._log(
            level='DEBUG',
            content=f"[维度数据] 用例 {case_name} 加载的维度列表: {[{ 'id': d['id'], 'name': d['name'], 'task_type_code': d.get('task_type_code'), 'api_url': d.get('api_url'), 'api_settings_keys': list(d.get('api_settings', {}).keys()) if d.get('api_settings') else [] } for d in dimension_data_list]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        return dimension_data_list

    def _query_dimensions(self, unique_dimension_ids):
        """查询维度数据并预加载 output/input 参数

        Returns:
            tuple: (dimensions, output_param_map, input_param_map)

        P5+DOMAIN: 通过 Repository.list_active_dimensions_by_ids 加载聚合根，
                   不再直接 query Dimension PO。维度以聚合根形式返回，
                   下游 _format_dimension_data 通过 .snapshot 访问字段。
        P1.4: EvaluationDimensionParam 通过 gRPC 调
              task_service.AlgorithmConfigService.GetDimensionParams（属 algorithm 域）。
        P0-1: 通过依赖注入的 ABC 访问 Repository/ACL，domain 层不 import infrastructure。
        """
        dimension_aggregates = self._evaluation_dimension_repo.list_active_dimensions_by_ids(
            unique_dimension_ids
        )
        if not dimension_aggregates:
            return [], {}, {}

        # P1.4: 通过 gRPC 批量获取所有维度的参数（按 dimension_id 逐个调用）
        output_param_map = {}
        input_param_map = {}
        for agg in dimension_aggregates:
            dim_id = agg.id
            params = self._task_acl_repo.get_dimension_params(dim_id)
            for p in params:
                direction = p.param_direction
                if direction == 'output':
                    output_param_map.setdefault(dim_id, []).append({
                        'param_code': p.param_code,
                        'field_path': p.field_path,
                        'field_type': p.field_type,
                        'agg_role': p.agg_role,
                        'output_role': p.output_role,
                        'visible_in_report': p.visible_in_report if p.visible_in_report is not None else True
                    })
                elif direction == 'input':
                    input_param_map.setdefault(dim_id, []).append({
                        'param_code': p.param_code,
                        'default_value': p.default_value,
                        'field_type': p.field_type,
                        'required': p.required
                    })

        return dimension_aggregates, output_param_map, input_param_map

    def _format_dimension_data(self, dimensions, output_param_map, input_param_map):
        """将维度聚合根格式化为 dim_dict 列表

        P5+DOMAIN: 入参 dimensions 现为 EvaluationDimension 聚合根列表，
                   通过 .snapshot 值对象访问持久化字段，避免领域层依赖 PO。
        """
        dimension_data_list = []
        for agg in dimensions:
            dim_id = agg.id
            snap = agg.snapshot
            dim_outputs = output_param_map.get(dim_id, [])
            output_field_path = dim_outputs[0]['field_path'] if dim_outputs else None

            dim_dict = {
                'id': dim_id,
                'name': agg.name,
                'keywords': None,  # keywords 不在快照中，若需要可加入 DimensionSnapshot
                'rule': snap.rule.to_dict() if snap.rule else {},
                'api_endpoints': snap.api_endpoints or [],
                'api_settings': snap.api_settings,
                'api_url': snap.api_url,
                'dimension_type': snap.dimension_type or 'main',
                'parent_dimension_id': snap.parent_dimension_id,
                'task_type_code': snap.task_type_code,
                'output_field_path': output_field_path,
                'output_params': dim_outputs,
                'input_params': input_param_map.get(dim_id, [])
            }

            # 子维度继承父维度的API配置和 input_params（output_params 不继承，各子维度自己挂）
            if snap.dimension_type == 'sub':
                parent_dim = None
                parent_id = snap.parent_dimension_id
                if parent_id:
                    # 通过 Repository 加载父维度聚合根
                    parent_aggs = self._evaluation_dimension_repo.list_active_dimensions_by_ids([parent_id])
                    parent_dim = parent_aggs[0] if parent_aggs else None
                if parent_dim:
                    parent_snap = parent_dim.snapshot
                    # API 配置：仅当子维度缺 api_endpoints/api_url 时继承
                    # 注意 api_endpoints 可能为空列表 [] 或包含空URL的列表
                    sub_endpoints = dim_dict.get('api_endpoints')
                    has_valid_endpoint = False
                    if sub_endpoints and isinstance(sub_endpoints, list):
                        for ep in sub_endpoints:
                            if isinstance(ep, dict) and (ep.get('url') or ep.get('endpoint')):
                                has_valid_endpoint = True
                                break
                    if not has_valid_endpoint and not dim_dict.get('api_url'):
                        # api_endpoints/api_url/api_settings 继承父维度
                        # task_type_code 不继承：子维度各自独立（如 tor/false_takeover/takeover_latency），
                        # 发请求时 task_type 用主维度的 turn_taking，sub_tasks 从子维度 task_type_code 提取
                        for k in ['api_endpoints', 'api_url', 'api_settings']:
                            if not dim_dict.get(k):
                                dim_dict[k] = getattr(parent_snap, k, None)
                    # 子维度继承主维度的 task_type_code，用于发请求时 task_type=turn_taking
                    dim_dict['parent_task_type_code'] = getattr(parent_snap, 'task_type_code', None)

            dimension_data_list.append(dim_dict)

        return dimension_data_list
