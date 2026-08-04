from shared.models.models import TestResultDimension, TestCase, Device, API, Task, Dimension
from shared.models.database import db
from shared.utils.result_data_store import load_full_result_data
from shared.schemas.testcase import ReportAudioItem, ReportTestCaseItem


class MetricsMixin:
    @staticmethod
    def extract_dimension_values(result_id, all_dimensions, dim_results_map=None):
        """
        提取测试结果的维度得分。
        """
        values = {}
        
        # 创建维度ID到名称的映射
        dim_id_to_name = {dim.id: dim.name for dim in all_dimensions}
        
        if dim_results_map and result_id in dim_results_map:
            # 使用预加载的映射
            dim_results = dim_results_map[result_id]
            for dr in dim_results:
                # 注意：这里 dr 可能是字典（推荐）或 tuple 或对象
                
                dim_id = None
                dim_val = None
                
                # 情况1: dr 是字典 {"id": dimension_id, "value": dimension_value, "name": dimension_name}
                if isinstance(dr, dict):
                    dim_id = dr.get('id')
                    dim_val = dr.get('value')
                
                # 情况2: dr 是 TestResultDimension 对象
                elif hasattr(dr, 'dimension_id'):
                    dim_id = dr.dimension_id
                    dim_val = dr.dimension_value
                
                # 情况3: dr 是 SQLAlchemy Row 或 namedtuple
                elif hasattr(dr, '_fields') or isinstance(dr, tuple):
                    if isinstance(dr, tuple) or hasattr(dr, '_fields'):
                        if hasattr(dr, 'dimension_id'):
                            dim_id = dr.dimension_id
                            dim_val = dr.dimension_value
                        elif hasattr(dr, 'id'):
                            dim_id = dr.id
                            dim_val = dr.value
                
                # 使用维度ID对应的名称作为键
                if dim_id and dim_id in dim_id_to_name:
                    values[dim_id_to_name[dim_id]] = dim_val
        else:
            # 数据库查询兜底
            for dim in all_dimensions:
                dim_result = TestResultDimension.query.filter_by(
                    test_result_id=result_id, 
                    dimension_id=dim.id
                ).first()
                
                if dim_result:
                    # 直接使用原始维度名称
                    values[dim.name] = dim_result.dimension_value
        
        return values
    
    @staticmethod
    def calculate_core_metrics(results, all_dimensions, resources, dim_results_map=None, tasks_map=None, use_time_prefix=False):
        """
        核心指标计算逻辑。
        """
        category_accumulator = {}
        tag_accumulator = {}

        # 直接使用原始维度名称初始化 raw_data
        raw_data = {res: {dim.name: [] for dim in all_dimensions} for res in resources}

        results_by_group = {}

        # 维度名 -> statistic_method 映射
        dim_statistic_method = {dim.name: getattr(dim, 'statistic_method', 'average') or 'average' for dim in all_dimensions}
        # 需要特殊聚合的维度（非 average 的）
        custom_agg_dims = {name for name, m in dim_statistic_method.items() if m != 'average'}
        # dim_id -> name 反向映射，用于从 dim_results_map 查 api_raw_response
        dim_id_to_name_inv = {dim.id: dim.name for dim in all_dimensions}

        # 预加载维度的 output 参数（field_path 配置），用于聚合策略提取结果字段
        dim_output_params = {}
        if custom_agg_dims:
            from shared.models.algorithm_models import EvaluationDimensionParam
            output_dim_ids = [dim.id for dim in all_dimensions if dim.name in custom_agg_dims]
            if output_dim_ids:
                output_params = EvaluationDimensionParam.query.filter(
                    EvaluationDimensionParam.dimension_id.in_(output_dim_ids),
                    EvaluationDimensionParam.param_direction == 'output',
                    EvaluationDimensionParam.deleted == False
                ).all()
                for p in output_params:
                    dim_output_params.setdefault(p.dimension_id, []).append({
                        'param_code': p.param_code,
                        'field_path': p.field_path,
                        'field_type': p.field_type,
                        'agg_role': p.agg_role,
                        'output_role': p.output_role,
                        'visible_in_report': p.visible_in_report if p.visible_in_report is not None else True
                    })

        # 收集需要聚合的 items: {dim_name: {group_key: {resource: [items]}}}
        # 每个 item 是 {dimension_value, api_raw_response, test_result_id}
        category_agg_items = {}
        tag_agg_items = {}
        # resource 级别累加器（不按 category 分组，与 device_stats 口径一致）
        resource_accumulator = {}
        resource_agg_items = {}

        # 预加载所有 TestCase，避免循环内 N+1 查询
        test_case_ids = list(set(r.test_case_id for r in results if r.test_case_id))
        test_cases_map = {}
        if test_case_ids:
            test_cases = TestCase.query.filter(TestCase.id.in_(test_case_ids)).all()
            test_cases_map = {tc.id: tc for tc in test_cases}

        for result in results:
            task = tasks_map.get(result.task_id) if tasks_map else None
            resource = ReportUtils.get_resource_name(result, task, use_time_prefix)
            
            if resource not in raw_data:
                raw_data[resource] = {dim.name: [] for dim in all_dimensions}
                if resource not in resources:
                    resources.append(resource)
            
            # 3. 获取用例信息（使用预加载的映射）
            test_case = test_cases_map.get(result.test_case_id)
            if not test_case:
                continue
            
            # 4. 获取分类(Group)和标签(Tags)
            # category 使用 ID，tags 使用 name（前端需要显示名称）
            category = test_case.group.id if test_case.group else "default_group"
            
            tc_tags = getattr(test_case, 'tags', []) or []
            tags = [tag.name for tag in tc_tags if tag.name] or ["default_tag"]
            
            tag_category_map = {}
            for tag in tc_tags:
                if hasattr(tag, 'category_id') and tag.category_id:
                    tag_category_map[tag.name] = tag.category_id

            # 5. 收集分组统计数据
            if category not in results_by_group:
                results_by_group[category] = []
            results_by_group[category].append(result)

            # 6. 提取维度值
            dim_values = ReportUtils.extract_dimension_values(result.id, all_dimensions, dim_results_map)
            
            # 7. 更新累加器 (Category & Tags & Resource)
            # 初始化累加器结构
            if category not in category_accumulator:
                category_accumulator[category] = {}
            if resource not in category_accumulator[category]:
                # 直接使用原始维度名称
                category_accumulator[category][resource] = {dim.name: {'sum': 0, 'count': 0} for dim in all_dimensions}
                category_accumulator[category][resource]['success_rate'] = {'sum': 0, 'count': 0}
            elif 'success_rate' not in category_accumulator[category][resource]:
                 category_accumulator[category][resource]['success_rate'] = {'sum': 0, 'count': 0}

            # resource 级别累加器初始化（不按 category 分组）
            if resource not in resource_accumulator:
                resource_accumulator[resource] = {dim.name: {'sum': 0, 'count': 0} for dim in all_dimensions}
                resource_accumulator[resource]['success_rate'] = {'sum': 0, 'count': 0}
            elif 'success_rate' not in resource_accumulator[resource]:
                resource_accumulator[resource]['success_rate'] = {'sum': 0, 'count': 0}

            for tag in tags:
                if tag not in tag_accumulator:
                    tag_accumulator[tag] = {}
                if resource not in tag_accumulator[tag]:
                    # 直接使用原始维度名称
                    tag_accumulator[tag][resource] = {dim.name: {'sum': 0, 'count': 0} for dim in all_dimensions}
                    tag_accumulator[tag][resource]['success_rate'] = {'sum': 0, 'count': 0}
                elif 'success_rate' not in tag_accumulator[tag][resource]:
                    tag_accumulator[tag][resource]['success_rate'] = {'sum': 0, 'count': 0}

            # 8. 累加数据
            is_success = result.execution_status == 'completed'
            success_val = 100 if is_success else 0
            
            # 累加通过率
            category_accumulator[category][resource]['success_rate']['sum'] += success_val
            category_accumulator[category][resource]['success_rate']['count'] += 1
            resource_accumulator[resource]['success_rate']['sum'] += success_val
            resource_accumulator[resource]['success_rate']['count'] += 1
            
            for tag in tags:
                tag_accumulator[tag][resource]['success_rate']['sum'] += success_val
                tag_accumulator[tag][resource]['success_rate']['count'] += 1
            
            # 累加维度分
            for dim_name, score in dim_values.items():
                if score is not None:
                    # Category
                    if dim_name in category_accumulator[category][resource]:
                        category_accumulator[category][resource][dim_name]['sum'] += score
                        category_accumulator[category][resource][dim_name]['count'] += 1

                    # Resource（全局，不按 category 分组）
                    if dim_name in resource_accumulator[resource]:
                        resource_accumulator[resource][dim_name]['sum'] += score
                        resource_accumulator[resource][dim_name]['count'] += 1

                    # Tag
                    for tag in tags:
                        if dim_name in tag_accumulator[tag][resource]:
                            tag_accumulator[tag][resource][dim_name]['sum'] += score
                            tag_accumulator[tag][resource][dim_name]['count'] += 1

                    # Raw Data
                    if dim_name in raw_data[resource]:
                        raw_data[resource][dim_name].append(score)

                    # 对非 average 维度收集完整 item，用于后续策略聚合
                    if dim_name in custom_agg_dims:
                        # 从 dim_results_map 拿 api_raw_response
                        raw_resp = None
                        if dim_results_map and result.id in dim_results_map:
                            for dr in dim_results_map[result.id]:
                                dr_dim_id = getattr(dr, 'dimension_id', None) or (dr.get('id') if isinstance(dr, dict) else None)
                                if dr_dim_id and dim_name in dim_id_to_name_inv and dr_dim_id == dim_id_to_name_inv[dim_name]:
                                    raw_resp = getattr(dr, 'api_raw_response', None) or (dr.get('api_raw_response') if isinstance(dr, dict) else None)
                                    break

                        agg_item = {'dimension_value': score, 'api_raw_response': raw_resp, 'test_result_id': result.id}
                        category_agg_items.setdefault(dim_name, {}).setdefault(category, {}).setdefault(resource, []).append(agg_item)
                        resource_agg_items.setdefault(dim_name, {}).setdefault(resource, []).append(agg_item)
                        for tag in tags:
                            tag_agg_items.setdefault(dim_name, {}).setdefault(tag, {}).setdefault(resource, []).append(agg_item)

        # 9. 计算平均值 (Metric Data & Tag Metric Data)
        # metric_data 改为 resource 级别全局平均（不按 category 分组，与 device_stats 口径一致）
        metric_data = ReportUtils._calculate_resource_averages(resource_accumulator)
        tag_metric_data = ReportUtils._calculate_averages(tag_accumulator)

        # 9.1 对非 average 维度，用策略类聚合替换简单平均
        if custom_agg_dims:
            # dim_name -> output_params 映射
            dim_name_to_output_params = {}
            for dim in all_dimensions:
                if dim.name in custom_agg_dims:
                    dim_name_to_output_params[dim.name] = dim_output_params.get(dim.id, [])
            ReportUtils._apply_resource_aggregation_strategies(metric_data, resource_agg_items, dim_statistic_method, dim_name_to_output_params)
            ReportUtils._apply_aggregation_strategies(tag_metric_data, tag_agg_items, dim_statistic_method, dim_name_to_output_params)

        # 9.5 计算按标签分类统计的数据
        tag_category_metric_data = ReportUtils._calculate_tag_category_averages(
            tag_accumulator, tag_category_map
        )

        # 10. 计算 Case Type Stats (即按分组统计)
        # 优化：使用 calculate_case_type_stats_optimized 并传入 dim_results_map 提高性能
        case_type_stats = ReportUtils.calculate_case_type_stats_optimized(results, all_dimensions, dim_results_map)

        return {
            "metric_data": metric_data,
            "tag_metric_data": tag_metric_data,
            "tag_category_metric_data": tag_category_metric_data,
            "raw_data": raw_data,
            "case_type_stats": case_type_stats,
            "resources": resources
        }
    
    @staticmethod
    def _calculate_averages(accumulator):
        """辅助函数：计算平均值"""
        result_data = {}
        for key, res_data in accumulator.items():
            if key not in result_data:
                result_data[key] = {}
            for res, dims in res_data.items():
                if res not in result_data[key]:
                    result_data[key][res] = {}
                for dim_name, stats in dims.items():
                    result_data[key][res][dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else 0
        return result_data

    @staticmethod
    def _calculate_resource_averages(resource_accumulator):
        """
        计算 resource 级别全局平均值（不按 category 分组）。

        resource_accumulator 结构: {resource: {dim_name: {sum, count}}}
        返回结构: {resource: {dim_name: avg}}
        """
        result_data = {}
        for resource, dims in resource_accumulator.items():
            if resource not in result_data:
                result_data[resource] = {}
            for dim_name, stats in dims.items():
                result_data[resource][dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else 0
        return result_data

    @staticmethod
    def _apply_resource_aggregation_strategies(metric_data, agg_items, dim_statistic_method, dim_output_params=None):
        """
        对非 average 维度，用策略类聚合替换简单平均值（resource 级别）。

        agg_items 结构: {dim_name: {resource: [items]}}
        metric_data 结构: {resource: {dim_name: value}}
        """
        if not agg_items:
            return

        from shared.utils.report.aggregation_strategies import get_strategy

        for dim_name, resources in agg_items.items():
            method = dim_statistic_method.get(dim_name, 'average')
            strategy = get_strategy(method)
            output_params = (dim_output_params or {}).get(dim_name, [])

            for resource, items in resources.items():
                if not items:
                    continue
                agg_val = strategy.aggregate(items, output_params=output_params)
                if agg_val is not None and resource in metric_data:
                    metric_data[resource][dim_name] = agg_val

    @staticmethod
    def _apply_aggregation_strategies(metric_data, agg_items, dim_statistic_method, dim_output_params=None):
        """
        对非 average 维度，用策略类聚合替换简单平均值。

        agg_items 结构: {dim_name: {group_key: {resource: [items]}}}
        metric_data 结构: {group_key: {resource: {dim_name: value}}}
        dim_statistic_method: {dim_name: statistic_method}
        dim_output_params: {dim_name: [{param_code, field_path, field_type}, ...]}
        """
        if not agg_items:
            return

        from shared.utils.report.aggregation_strategies import get_strategy

        for dim_name, groups in agg_items.items():
            method = dim_statistic_method.get(dim_name, 'average')
            strategy = get_strategy(method)
            output_params = (dim_output_params or {}).get(dim_name, [])

            for group_key, resources in groups.items():
                for resource, items in resources.items():
                    if not items:
                        continue
                    agg_val = strategy.aggregate(items, output_params=output_params)
                    if agg_val is not None and group_key in metric_data and resource in metric_data[group_key]:
                        metric_data[group_key][resource][dim_name] = agg_val

    @staticmethod
    def _calculate_tag_category_averages(tag_accumulator, tag_category_map):
        """
        辅助函数：按标签分类计算平均值

        参数:
            tag_accumulator: 标签累加器 {tag_name: {resource: {dim: {sum, count}}}}
            tag_category_map: 标签到分类的映射 {tag_name: category_id}

        返回:
            dict: 按分类组织的统计数据
        """
        from shared.models.models import TagCategory

        result_data = {}
        
        category_tags = {}
        for tag_name in tag_accumulator.keys():
            if tag_name == "default_tag":
                continue
            category_id = tag_category_map.get(tag_name)
            if category_id not in category_tags:
                category_tags[category_id] = []
            category_tags[category_id].append(tag_name)
        
        uncategorized_tags = [t for t in tag_accumulator.keys() if t not in tag_category_map and t != "default_tag"]
        if uncategorized_tags:
            category_tags[None] = uncategorized_tags
        
        for category_id, tag_names in category_tags.items():
            category_info = {}
            
            if category_id:
                cat = db.session.get(TagCategory, category_id)
                if cat:
                    category_info = {
                        'category_id': cat.id,
                        'category_name': cat.name,
                        'category_color': cat.color
                    }
            
            for tag_name in tag_names:
                tag_data = tag_accumulator.get(tag_name, {})
                
                for resource, dims in tag_data.items():
                    if resource not in result_data:
                        result_data[resource] = {'categories': {}}
                    
                    cat_key = category_id if category_id else 'uncategorized'
                    if cat_key not in result_data[resource]['categories']:
                        result_data[resource]['categories'][cat_key] = {
                            **category_info,
                            'tags': []
                        }
                    
                    tag_metrics = {}
                    for dim_name, stats in dims.items():
                        tag_metrics[dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else 0
                    
                    result_data[resource]['categories'][cat_key]['tags'].append({
                        'tag_name': tag_name,
                        'category_id': category_id,
                        'category_name': category_info.get('category_name'),
                        'metrics': tag_metrics
                    })
        
        return result_data
    
    @staticmethod
    def _calculate_case_type_stats(results_by_group, all_dimensions):
        """辅助函数：计算分组统计"""
        stats = {}
        for group_id, group_results in results_by_group.items():
            type_metrics = {}
            for dim in all_dimensions:
                dim_scores = []
                for result in group_results:
                    # 复用 extract_dimension_values 逻辑
                    # 注意：这里会重新查询维度值，如果有性能问题，应传入 dim_results_map
                    # 暂时为了简单直接查询
                    dim_values = ReportUtils.extract_dimension_values(result.id, [dim])
                    # 直接使用原始维度名称获取值
                    if dim_values.get(dim.name) is not None:
                        dim_scores.append(dim_values[dim.name])
                
                type_metrics[dim.name] = (sum(dim_scores) / len(dim_scores)) if dim_scores else 0
            stats[group_id] = type_metrics
        return stats
    
    @staticmethod
    def calculate_case_type_stats_optimized(results, all_dimensions, dim_results_map=None):
        """
        计算按用例分组(Case Type)的统计数据。
        """
        group_scores = {} # {group_id: {dim_name: [scores]}}
        
        # 预加载所有 TestCase，避免循环内 N+1 查询
        test_case_ids = list(set(r.test_case_id for r in results if r.test_case_id))
        test_cases_map = {}
        if test_case_ids:
            test_cases = TestCase.query.filter(TestCase.id.in_(test_case_ids)).all()
            test_cases_map = {tc.id: tc for tc in test_cases}
        
        for result in results:
            test_case = test_cases_map.get(result.test_case_id)
            if not test_case:
                continue
            group_id = test_case.group.id if test_case.group else "default_group"
            
            if group_id not in group_scores:
                # 直接使用原始维度名称初始化
                group_scores[group_id] = {dim.name: [] for dim in all_dimensions}
            
            dim_values = ReportUtils.extract_dimension_values(result.id, all_dimensions, dim_results_map)
            
            for dim_name, score in dim_values.items():
                if score is not None and dim_name in group_scores[group_id]:
                    group_scores[group_id][dim_name].append(score)
        
        # 计算平均分
        stats = {}
        for group_id, dims in group_scores.items():
            stats[group_id] = {}
            for dim_name, scores in dims.items():
                stats[group_id][dim_name] = (sum(scores) / len(scores)) if scores else 0
        return stats
    
    @staticmethod
    def calculate_device_api_stats(results, all_dimensions, dim_results_map=None):
        """
        计算设备和API的统计数据。
        """
        device_results = {}
        api_results = {}
        
        for result in results:
            if result.device_id:
                if result.device_id not in device_results:
                    device_results[result.device_id] = []
                device_results[result.device_id].append(result)
            
            if result.api_id:
                if result.api_id not in api_results:
                    api_results[result.api_id] = []
                api_results[result.api_id].append(result)
        
        device_stats = []
        for dev_id, res_list in device_results.items():
            device = db.session.get(Device, dev_id)
            if not device: continue
            
            metrics = ReportUtils._calc_list_metrics(res_list, all_dimensions, dim_results_map)
            total = len(res_list)
            completed = len([r for r in res_list if r.execution_status == 'completed'])
            
            device_stats.append({
                "id": device.id, "name": device.name, "model": device.model, "type": device.type,
                "system": device.system, "system_version": device.system_version, "status": device.status,
                "metrics": metrics, "total_cases": total, "completed_cases": completed,
                "failed_cases": total - completed, "success_rate": round(completed / total * 100, 2) if total > 0 else 0
            })
            
        api_stats = []
        for api_id, res_list in api_results.items():
            api = db.session.get(API, api_id)
            if not api: continue
            
            metrics = ReportUtils._calc_list_metrics(res_list, all_dimensions, dim_results_map)
            total = len(res_list)
            completed = len([r for r in res_list if r.execution_status == 'completed'])
            
            api_stats.append({
                "id": api.id, "name": api.name, "status": api.status, "max_process": api.max_process,
                "health_score": api.health_score, "metrics": metrics, "total_cases": total,
                "completed_cases": completed, "failed_cases": total - completed, "success_rate": round(completed / total * 100, 2) if total > 0 else 0
            })
            
        return device_stats, api_stats

    @staticmethod
    def normalize_summary_metrics(summary):
        if not isinstance(summary, dict):
            return {}
        
        category_items = summary.get('case_categories') or []
        tag_items = summary.get('all_case_tags') or summary.get('all_tags') or []
        category_id_to_name = ReportUtils._build_id_name_map(category_items)
        tag_id_to_name = ReportUtils._build_id_name_map(tag_items)
        all_metrics_items = summary.get('all_metrics') or summary.get('allMetrics') or []
        if isinstance(all_metrics_items, list):
            needs_decimal_places = any(
                isinstance(m, dict)
                and m.get('id') is not None
                and ('decimal_places' not in m and 'decimalPlaces' not in m)
                for m in all_metrics_items
            )
            if needs_decimal_places:
                ids = []
                for m in all_metrics_items:
                    if not isinstance(m, dict):
                        continue
                    mid = m.get('id')
                    if mid is None:
                        continue
                    try:
                        ids.append(int(mid))
                    except Exception:
                        continue
                if ids:
                    dims = Dimension.query.filter(Dimension.id.in_(list(set(ids)))).all()
                    id_to_decimal_places = {
                        int(d.id): (d.decimal_places if d.decimal_places is not None else 2)
                        for d in dims
                        if getattr(d, 'id', None) is not None
                    }
                    for m in all_metrics_items:
                        if not isinstance(m, dict):
                            continue
                        if 'decimal_places' in m or 'decimalPlaces' in m:
                            continue
                        mid = m.get('id')
                        try:
                            mid_int = int(mid)
                        except Exception:
                            continue
                        if mid_int in id_to_decimal_places:
                            m['decimal_places'] = id_to_decimal_places[mid_int]
        
        raw_data_flat = ReportUtils.flatten_raw_data(summary.get('raw_data') or summary.get('rawData'))
        used_metric_names = set()
        for item in raw_data_flat:
            if not isinstance(item, dict):
                continue
            metrics = item.get('metrics') or []
            if not isinstance(metrics, list):
                continue
            for m in metrics:
                if not isinstance(m, dict):
                    continue
                name = m.get('metric')
                values = m.get('values')
                if name is None:
                    continue
                if isinstance(values, list) and len(values) > 0:
                    used_metric_names.add(str(name))
                elif values is not None and not isinstance(values, list):
                    used_metric_names.add(str(name))

        filtered_all_metrics_items = all_metrics_items
        if isinstance(all_metrics_items, list) and used_metric_names:
            filtered_all_metrics_items = [
                m
                for m in all_metrics_items
                if isinstance(m, dict)
                and m.get('name') is not None
                and str(m.get('name')) in used_metric_names
            ]

        metric_name_to_id = ReportUtils._build_metric_name_id_map(filtered_all_metrics_items)
        
        normalized = dict(summary)
        normalized['raw_data'] = raw_data_flat
        if 'rawData' in normalized:
            normalized['rawData'] = raw_data_flat
        if 'all_metrics' in normalized:
            normalized['all_metrics'] = filtered_all_metrics_items
        if 'allMetrics' in normalized:
            normalized['allMetrics'] = filtered_all_metrics_items
        normalized['metric_data'] = ReportUtils.flatten_metric_data(summary.get('metric_data'), category_id_to_name, metric_name_to_id)
        normalized['tag_metric_data'] = ReportUtils.flatten_tag_metric_data(summary.get('tag_metric_data'), tag_id_to_name, metric_name_to_id)
        normalized['case_type_stats'] = ReportUtils.flatten_case_type_stats(summary.get('case_type_stats'), category_id_to_name, metric_name_to_id)
        
        cases = summary.get('cases')
        if isinstance(cases, list):
            normalized_cases = []
            for case in cases:
                if not isinstance(case, dict):
                    normalized_cases.append(case)
                    continue
                new_case = dict(case)
                results = case.get('results')
                if isinstance(results, dict):
                    result_rows = []
                    for resource in sorted(results.keys(), key=lambda x: str(x)):
                        info = results.get(resource)
                        if not isinstance(info, dict):
                            continue
                        result_rows.append({"resource": str(resource), **info})
                    new_case['results'] = result_rows
                
                metrics = case.get('metrics')
                if isinstance(metrics, list):
                    new_case['metrics'] = metrics
                elif isinstance(metrics, dict):
                    metric_groups = []
                    for resource in sorted(metrics.keys(), key=lambda x: str(x)):
                        dim_values = metrics.get(resource)
                        if not isinstance(dim_values, dict):
                            continue
                        metric_list = []
                        for metric in sorted(dim_values.keys(), key=lambda x: str(x)):
                            value = dim_values.get(metric)
                            m = str(metric)
                            metric_list.append({"id": metric_name_to_id.get(m), "metric": m, "value": 0 if value is None else value})
                        metric_groups.append({"resource": str(resource), "metrics": metric_list})
                    new_case['metrics'] = metric_groups
                
                # 处理 reference_params 字段（支持多种参考类型：asr, translation, rttm, stm等）
                reference_params = case.get('reference_params')
                if isinstance(reference_params, dict) and reference_params:
                    normalized_ref_params = {}
                    for code, param_info in reference_params.items():
                        if not isinstance(param_info, dict):
                            continue
                        normalized_ref_params[code] = {
                            "code": param_info.get('code', code),
                            "type": param_info.get('type', 'text'),
                            "value": param_info.get('value'),
                        }
                        # 如果有结构化数据（segments, text, json），也保留
                        if param_info.get('segments'):
                            normalized_ref_params[code]["segments"] = param_info.get('segments')
                        if param_info.get('text'):
                            normalized_ref_params[code]["text"] = param_info.get('text')
                        if param_info.get('json'):
                            normalized_ref_params[code]["json"] = param_info.get('json')
                    new_case['reference_params'] = normalized_ref_params
                
                # 处理 algorithm_results 字段（兼容 dict 和数组格式）
                algorithm_results = case.get('algorithm_results')
                if isinstance(algorithm_results, list) and algorithm_results:
                    # 新格式：扁平列表 [{device, param_code, param_type, label, value}, ...]
                    normalized_algo_list = []
                    for item in algorithm_results:
                        if isinstance(item, dict) and item.get('value') is not None:
                            normalized_algo_list.append(item)
                    new_case['algorithm_results'] = normalized_algo_list
                elif isinstance(algorithm_results, dict) and algorithm_results:
                    # 旧格式：dict {resource: {param_key: value}}
                    normalized_algo_results = {}
                    for resource, algo_data in algorithm_results.items():
                        if not isinstance(algo_data, dict):
                            continue
                        normalized_algo_results[resource] = {}
                        for field_key, field_value in algo_data.items():
                            if field_value is not None:
                                normalized_algo_results[resource][field_key] = field_value
                    new_case['algorithm_results'] = normalized_algo_results
                
                audios = case.get('audios')
                
                if audios and isinstance(audios, list):
                    normalized_audios = []
                    for audio in audios:
                        if not isinstance(audio, dict):
                            continue
                        try:
                            audio_item = ReportAudioItem.model_validate(audio)
                            result = audio_item.model_dump(mode='json')
                            normalized_audios.append(result)
                        except Exception as e:
                            print(f"Pydantic 错误: {e}")
                            normalized_audios.append(audio)
                    new_case['audios'] = normalized_audios
                else:
                    old_audios = []
                    api_audio = case.get('api_audio')
                    e2e_audio = case.get('e2e_audio')
                    e2e_audios = case.get('e2e_audios', [])
                    old_audio = case.get('audio')
                    
                    if api_audio and isinstance(api_audio, dict):
                        api_audio['audio_type'] = 'api'
                        old_audios.append(api_audio)
                    
                    if e2e_audio and isinstance(e2e_audio, dict):
                        e2e_audio['audio_type'] = 'e2e'
                        old_audios.append(e2e_audio)
                    
                    if isinstance(e2e_audios, list):
                        for audio in e2e_audios:
                            if isinstance(audio, dict) and audio not in old_audios:
                                audio['audio_type'] = 'e2e'
                                old_audios.append(audio)
                    
                    if old_audio and isinstance(old_audio, dict) and old_audio not in old_audios:
                        old_audio['audio_type'] = old_audio.get('audio_type', 'api')
                        old_audios.append(old_audio)
                    
                    if old_audios:
                        new_case['audios'] = old_audios
                
                normalized_cases.append(new_case)
            normalized['cases'] = normalized_cases
        
        return normalized
    
    @staticmethod
    def _calc_list_metrics(results, all_dimensions, dim_results_map):
        metrics = {}
        for dim in all_dimensions:
            scores = []
            for result in results:
                vals = ReportUtils.extract_dimension_values(result.id, all_dimensions, dim_results_map)
                # 直接使用原始维度名称获取值
                if vals.get(dim.name) is not None:
                    scores.append(vals[dim.name])
            metrics[dim.name] = (sum(scores) / len(scores)) if scores else 0
        return metrics
