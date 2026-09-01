# -*- coding: utf-8 -*-
from shared.models.common_enums import TaskStatus
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_dimension_results_by_result_ids,
    _grpc_list_dimensions_all,
    _grpc_get_dimension_params,
    _grpc_list_testcases_by_ids,
    _grpc_get_tag_category,
    _grpc_get_device,
    _grpc_get_api,
)


def _dim_id(dim):
    """从维度对象（dict 或 ORM）读取 id。"""
    if isinstance(dim, dict):
        return dim.get('id')
    return getattr(dim, 'id', None)


def _dim_name(dim):
    """从维度对象（dict 或 ORM）读取 name。"""
    if isinstance(dim, dict):
        return dim.get('name')
    return getattr(dim, 'name', None)


def _dim_weight(dim):
    """从维度对象读取 weight。"""
    if isinstance(dim, dict):
        return dim.get('weight')
    return getattr(dim, 'weight', None)


def _dim_statistic_method(dim):
    """从维度对象读取 statistic_method。"""
    if isinstance(dim, dict):
        return dim.get('statistic_method')
    return getattr(dim, 'statistic_method', None)


def _dim_score_unit(dim):
    """从维度对象读取 score_unit。"""
    if isinstance(dim, dict):
        return dim.get('score_unit')
    return getattr(dim, 'score_unit', None)


def _dim_decimal_places(dim):
    """从维度对象读取 decimal_places。"""
    if isinstance(dim, dict):
        return dim.get('decimal_places')
    return getattr(dim, 'decimal_places', None)


def _dim_result_dim_id(dr):
    """从维度结果对象读取 dimension_id。"""
    if isinstance(dr, dict):
        return dr.get('dimension_id') or dr.get('id')
    return getattr(dr, 'dimension_id', None) or getattr(dr, 'id', None)


def _dim_result_value(dr):
    """从维度结果对象读取 dimension_value。"""
    if isinstance(dr, dict):
        return dr.get('dimension_value') or dr.get('value')
    return getattr(dr, 'dimension_value', None)


def _dim_result_raw_response(dr):
    """从维度结果对象读取 api_raw_response。"""
    if isinstance(dr, dict):
        return dr.get('api_raw_response')
    return getattr(dr, 'api_raw_response', None)


class MetricsMixin:
    @staticmethod
    def extract_dimension_values(result_id, all_dimensions, dim_results_map=None):
        """
        提取测试结果的维度得分。
        """
        values = {}

        # 创建维度ID到名称的映射（兼容 dict 与 ORM）
        dim_id_to_name = {_dim_id(d): _dim_name(d) for d in all_dimensions}

        if dim_results_map and result_id in dim_results_map:
            # 使用预加载的映射
            dim_results = dim_results_map[result_id]
            for dr in dim_results:
                dim_id = None
                dim_val = None

                # 情况1: dr 是字典
                if isinstance(dr, dict):
                    dim_id = dr.get('id') or dr.get('dimension_id')
                    dim_val = dr.get('value') or dr.get('dimension_value')

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
            # gRPC 兜底：通过 evaluation_service 查询单个 result 的维度结果
            dim_map = _grpc_get_dimension_results_by_result_ids([result_id])
            dim_results = dim_map.get(result_id, [])
            for dr in dim_results:
                dim_id = _dim_result_dim_id(dr)
                dim_val = _dim_result_value(dr)
                if dim_id and dim_id in dim_id_to_name:
                    values[dim_id_to_name[dim_id]] = dim_val

        return values

    @staticmethod
    def calculate_core_metrics(results, all_dimensions, resources, dim_results_map=None, tasks_map=None, use_time_prefix=False):
        """
        核心指标计算逻辑。
        """
        category_accumulator = {}
        tag_accumulator = {}

        # 直接使用原始维度名称初始化 raw_data
        raw_data = {res: {_dim_name(dim): [] for dim in all_dimensions} for res in resources}

        results_by_group = {}

        # 维度名 -> statistic_method 映射
        dim_statistic_method = {_dim_name(dim): (_dim_statistic_method(dim) or 'average') for dim in all_dimensions}
        # 需要特殊聚合的维度（非 average 的）
        custom_agg_dims = {name for name, m in dim_statistic_method.items() if m != 'average'}
        # dim_id -> name 反向映射，用于从 dim_results_map 查 api_raw_response
        dim_id_to_name_inv = {_dim_id(dim): _dim_name(dim) for dim in all_dimensions}

        # 预加载维度的 output 参数（field_path 配置），用于聚合策略提取结果字段
        dim_output_params = {}
        if custom_agg_dims:
            output_dim_ids = [_dim_id(dim) for dim in all_dimensions if _dim_name(dim) in custom_agg_dims]
            for dim_id in output_dim_ids:
                if dim_id is None:
                    continue
                params = _grpc_get_dimension_params(dim_id)
                for p in params:
                    if not isinstance(p, dict):
                        continue
                    if p.get('param_direction') != 'output':
                        continue
                    dim_output_params.setdefault(dim_id, []).append({
                        'param_code': p.get('param_code') or p.get('code'),
                        'field_path': p.get('field_path'),
                        'field_type': p.get('field_type'),
                        'agg_role': p.get('agg_role'),
                        'output_role': p.get('output_role'),
                        'visible_in_report': p.get('visible_in_report') if p.get('visible_in_report') is not None else True
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
        test_cases_map = _grpc_list_testcases_by_ids(test_case_ids)

        for result in results:
            task = tasks_map.get(result.task_id) if tasks_map else None
            resource = ReportUtils.get_resource_name(result, task, use_time_prefix)

            if resource not in raw_data:
                raw_data[resource] = {_dim_name(dim): [] for dim in all_dimensions}
                if resource not in resources:
                    resources.append(resource)

            # 3. 获取用例信息（使用预加载的映射）
            test_case = test_cases_map.get(result.test_case_id)
            if not test_case:
                continue

            # 4. 获取分类(Group)和标签(Tags)
            # category 使用 ID，tags 使用 name（前端需要显示名称）
            group = test_case.get('group') if isinstance(test_case, dict) else getattr(test_case, 'group', None)
            category = (group.get('id') if isinstance(group, dict) else getattr(group, 'id', None)) if group else "default_group"

            tc_tags = (test_case.get('tags') if isinstance(test_case, dict) else getattr(test_case, 'tags', [])) or []
            tags = []
            for tag in tc_tags:
                tag_name = tag.get('name') if isinstance(tag, dict) else getattr(tag, 'name', None)
                if tag_name:
                    tags.append(tag_name)
            if not tags:
                tags = ["default_tag"]

            tag_category_map = {}
            for tag in tc_tags:
                cat_id = tag.get('category_id') if isinstance(tag, dict) else getattr(tag, 'category_id', None)
                tag_name = tag.get('name') if isinstance(tag, dict) else getattr(tag, 'name', None)
                if cat_id and tag_name:
                    tag_category_map[tag_name] = cat_id

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
                category_accumulator[category][resource] = {_dim_name(dim): {'sum': 0, 'count': 0} for dim in all_dimensions}
                category_accumulator[category][resource]['success_rate'] = {'sum': 0, 'count': 0}
            elif 'success_rate' not in category_accumulator[category][resource]:
                 category_accumulator[category][resource]['success_rate'] = {'sum': 0, 'count': 0}

            # resource 级别累加器初始化（不按 category 分组）
            if resource not in resource_accumulator:
                resource_accumulator[resource] = {_dim_name(dim): {'sum': 0, 'count': 0} for dim in all_dimensions}
                resource_accumulator[resource]['success_rate'] = {'sum': 0, 'count': 0}
            elif 'success_rate' not in resource_accumulator[resource]:
                resource_accumulator[resource]['success_rate'] = {'sum': 0, 'count': 0}

            for tag in tags:
                if tag not in tag_accumulator:
                    tag_accumulator[tag] = {}
                if resource not in tag_accumulator[tag]:
                    # 直接使用原始维度名称
                    tag_accumulator[tag][resource] = {_dim_name(dim): {'sum': 0, 'count': 0} for dim in all_dimensions}
                    tag_accumulator[tag][resource]['success_rate'] = {'sum': 0, 'count': 0}
                elif 'success_rate' not in tag_accumulator[tag][resource]:
                    tag_accumulator[tag][resource]['success_rate'] = {'sum': 0, 'count': 0}

            # 8. 累加数据
            is_success = result.execution_status == TaskStatus.COMPLETED.value
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
                                dr_dim_id = _dim_result_dim_id(dr)
                                if dr_dim_id and dim_name in dim_id_to_name_inv and dr_dim_id == dim_id_to_name_inv[dim_name]:
                                    raw_resp = _dim_result_raw_response(dr)
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
                if _dim_name(dim) in custom_agg_dims:
                    dim_name_to_output_params[_dim_name(dim)] = dim_output_params.get(_dim_id(dim), [])
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

        from report_service.application.services.aggregation_strategies import get_strategy

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

        from report_service.application.services.aggregation_strategies import get_strategy

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
                cat = _grpc_get_tag_category(category_id)
                if cat:
                    category_info = {
                        'category_id': cat.get('id') if isinstance(cat, dict) else getattr(cat, 'id', None),
                        'category_name': cat.get('name') if isinstance(cat, dict) else getattr(cat, 'name', None),
                        'category_color': cat.get('color') if isinstance(cat, dict) else getattr(cat, 'color', None)
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
                    if dim_values.get(_dim_name(dim)) is not None:
                        dim_scores.append(dim_values[_dim_name(dim)])

                type_metrics[_dim_name(dim)] = (sum(dim_scores) / len(dim_scores)) if dim_scores else 0
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
        test_cases_map = _grpc_list_testcases_by_ids(test_case_ids)

        for result in results:
            test_case = test_cases_map.get(result.test_case_id)
            if not test_case:
                continue
            group = test_case.get('group') if isinstance(test_case, dict) else getattr(test_case, 'group', None)
            group_id = (group.get('id') if isinstance(group, dict) else getattr(group, 'id', None)) if group else "default_group"

            if group_id not in group_scores:
                # 直接使用原始维度名称初始化
                group_scores[group_id] = {_dim_name(dim): [] for dim in all_dimensions}

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
            device = _grpc_get_device(dev_id)
            if not device: continue

            metrics = ReportUtils._calc_list_metrics(res_list, all_dimensions, dim_results_map)
            total = len(res_list)
            completed = len([r for r in res_list if r.execution_status == TaskStatus.COMPLETED.value])

            device_stats.append({
                "id": device.get('id'), "name": device.get('name'), "model": device.get('model'), "type": device.get('type'),
                "system": device.get('system'), "system_version": device.get('system_version'), "status": device.get('status'),
                "metrics": metrics, "total_cases": total, "completed_cases": completed,
                "failed_cases": total - completed, "success_rate": round(completed / total * 100, 2) if total > 0 else 0
            })

        api_stats = []
        for api_id, res_list in api_results.items():
            api = _grpc_get_api(api_id)
            if not api: continue

            metrics = ReportUtils._calc_list_metrics(res_list, all_dimensions, dim_results_map)
            total = len(res_list)
            completed = len([r for r in res_list if r.execution_status == TaskStatus.COMPLETED.value])

            api_stats.append({
                "id": api.get('id'), "name": api.get('name'), "status": api.get('status'), "max_process": api.get('max_process'),
                "health_score": api.get('health_score'), "metrics": metrics, "total_cases": total,
                "completed_cases": completed, "failed_cases": total - completed, "success_rate": round(completed / total * 100, 2) if total > 0 else 0
            })

        return device_stats, api_stats

    @staticmethod
    def normalize_summary_metrics(summary):
        """委托到 report_service.application.services.normalize 共享实现。"""
        from report_service.application.services.normalize import normalize_summary_metrics as _fn

        def _dim_lookup(dim_ids):
            from report_service.infrastructure.clients.grpc_clients import _grpc_get_dimensions_by_ids
            return _grpc_get_dimensions_by_ids(dim_ids)

        return _fn(summary, dimension_lookup=_dim_lookup)

    @staticmethod
    def _calc_list_metrics(results, all_dimensions, dim_results_map):
        metrics = {}
        for dim in all_dimensions:
            scores = []
            for result in results:
                vals = ReportUtils.extract_dimension_values(result.id, all_dimensions, dim_results_map)
                # 直接使用原始维度名称获取值
                if vals.get(_dim_name(dim)) is not None:
                    scores.append(vals[_dim_name(dim)])
            metrics[_dim_name(dim)] = (sum(scores) / len(scores)) if scores else 0
        return metrics
