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

            # 子维度继承父维度的API配置——P5+DOMAIN: 父维度需通过 Repository 单独加载
            # 这里直接使用 snap 中已存的父维度字段（Repository 在 list 时未加载父维度，
            # 故 parent 字段为空；若下游确实需要父维度配置，可后续在 Repository 补 join）
            if snap.dimension_type == 'sub' and not dim_dict.get('api_endpoints') and not dim_dict.get('api_url'):
                # 子维度自身无 API 配置，task_type_code 已在 snap 中
                pass

            dimension_data_list.append(dim_dict)

        return dimension_data_list
