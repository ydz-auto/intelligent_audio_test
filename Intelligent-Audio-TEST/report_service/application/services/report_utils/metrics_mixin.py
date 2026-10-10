# -*- coding: utf-8 -*-
from shared.models.common_enums import TaskStatus
from report_service.domain.services.round_caliber import (
    collect_dim_items,
    get_round_value_samples,
)
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_dimension_params,
    _grpc_list_testcases_by_ids,
    _grpc_get_tag_category,
    _grpc_get_device,
    _grpc_get_api,
    _dim_agg_denominator,
    _dim_exclude_rounds,
)


def _r_get(r, key, default=None):
    """从测试结果（dict 或 ORM 对象）读取字段，兼容两种形态。"""
    if isinstance(r, dict):
        return r.get(key, default)
    return getattr(r, key, default)


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


class MetricsMixin:
    @staticmethod
    def extract_dimension_values(result_id, all_dimensions, dim_results_map=None):
        """提取测试结果的维度得分。

        与查询链（ReportHelpers.extract_dimension_values / report_aggregation.stats_mixin）
        共用同一实现（多轮场景取值优先级：有 overall 取 overall，无 overall 取各轮算术平均），
        保证报告主生成链与查询链口径一致。
        """
        from report_service.application.services.report_helpers import ReportHelpers
        return ReportHelpers.extract_dimension_values(result_id, all_dimensions, dim_results_map)

    @staticmethod
    def calculate_core_metrics(results, all_dimensions, resources, dim_results_map=None, tasks_map=None, use_time_prefix=False):
        """
        核心指标计算逻辑。
        """
        category_accumulator = {}
        tag_accumulator = {}
        # tag 名称 -> category_id 映射；必须在循环外初始化，
        # 避免结果集内 test_case 全部缺失（continue 跳过）时循环外访问未定义变量
        tag_category_map = {}

        # 直接使用原始维度名称初始化 raw_data
        raw_data = {res: {_dim_name(dim): [] for dim in all_dimensions} for res in resources}

        results_by_group = {}

        # 维度名 -> statistic_method 映射
        dim_statistic_method = {_dim_name(dim): (_dim_statistic_method(dim) or 'average') for dim in all_dimensions}
        # 需要特殊聚合的维度（非 average 的）
        custom_agg_dims = {name for name, m in dim_statistic_method.items() if m != 'average'}

        # 维度口径信息（对齐查询链 stats_mixin 的 dim_strategy_info）：
        # 非 average 维度 → 策略聚合 item 收集参数；average 且 agg_denominator='round' → 按轮次取样
        custom_agg_info = {}
        dim_round_mode_info = {}
        for dim in all_dimensions:
            _name = _dim_name(dim)
            _id = _dim_id(dim)
            if _name is None or _id is None:
                continue
            _info = {'dim_id': _id, 'exclude_rounds': _dim_exclude_rounds(dim)}
            if _name in custom_agg_dims:
                custom_agg_info[_name] = _info
            elif (_dim_statistic_method(dim) or 'average') == 'average' and _dim_agg_denominator(dim) == 'round':
                dim_round_mode_info[_name] = _info

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
                        'pass_threshold': p.get('pass_threshold'),
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
        test_case_ids = list(set(_r_get(r, 'test_case_id') for r in results if _r_get(r, 'test_case_id')))
        test_cases_map = _grpc_list_testcases_by_ids(test_case_ids)

        for result in results:
            task = tasks_map.get(_r_get(result, 'task_id')) if tasks_map else None
            resource = ReportUtils.get_resource_name(result, task, use_time_prefix)

            if resource not in raw_data:
                raw_data[resource] = {_dim_name(dim): [] for dim in all_dimensions}
                if resource not in resources:
                    resources.append(resource)

            # 3. 获取用例信息（使用预加载的映射，key 为 str(test_case_id)）
            test_case = test_cases_map.get(str(_r_get(result, 'test_case_id')))
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
            result_id = _r_get(result, 'id')
            dim_values = ReportUtils.extract_dimension_values(result_id, all_dimensions, dim_results_map)

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
            is_success = _r_get(result, 'execution_status') == TaskStatus.COMPLETED.value
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
                if score is None:
                    continue
                # 按轮次口径（agg_denominator='round'）的 average 维度：取各轮独立样本
                # （跳过排除轮次，无轮次记录回退整体值），与查询链 _get_round_value_samples 共用口径源
                round_info = dim_round_mode_info.get(dim_name)
                if round_info is not None:
                    sample_values = get_round_value_samples(
                        result_id, round_info['dim_id'], dim_results_map,
                        round_info['exclude_rounds'], score)
                else:
                    sample_values = [score]

                for sample_val in sample_values:
                    # Category
                    if dim_name in category_accumulator[category][resource]:
                        category_accumulator[category][resource][dim_name]['sum'] += sample_val
                        category_accumulator[category][resource][dim_name]['count'] += 1

                    # Resource（全局，不按 category 分组）
                    if dim_name in resource_accumulator[resource]:
                        resource_accumulator[resource][dim_name]['sum'] += sample_val
                        resource_accumulator[resource][dim_name]['count'] += 1

                    # Tag
                    for tag in tags:
                        if dim_name in tag_accumulator[tag][resource]:
                            tag_accumulator[tag][resource][dim_name]['sum'] += sample_val
                            tag_accumulator[tag][resource][dim_name]['count'] += 1

                # Raw Data（用例级值，与查询链 raw_data 口径一致）
                if dim_name in raw_data[resource]:
                    raw_data[resource][dim_name].append(score)

                # 对非 average 维度收集独立 item（整体/每轮优先级 + exclude_rounds 过滤 + round_count），
                # 与查询链 _collect_dim_items 共用口径源
                if dim_name in custom_agg_dims:
                    agg_info = custom_agg_info.get(dim_name)
                    items = collect_dim_items(
                        result_id, agg_info['dim_id'], dim_results_map, agg_info['exclude_rounds']
                    ) if agg_info else []
                    if not items and (not dim_results_map or result_id not in dim_results_map):
                        # 无维度结果映射（如对比报告 dim_results_map=None）时回退用例级值 1 个 item
                        items = [{'dimension_value': score, 'api_raw_response': None,
                                  'test_result_id': result_id, 'round_count': 0}]
                    category_agg_items.setdefault(dim_name, {}).setdefault(category, {}).setdefault(resource, []).extend(items)
                    resource_agg_items.setdefault(dim_name, {}).setdefault(resource, []).extend(items)
                    for tag in tags:
                        tag_agg_items.setdefault(dim_name, {}).setdefault(tag, {}).setdefault(resource, []).extend(items)

        # 9. 计算平均值 (Metric Data & Tag Metric Data)
        # metric_data 改为 resource 级别全局平均（不按 category 分组，与 device_stats 口径一致）
        metric_data = ReportUtils._calculate_resource_averages(resource_accumulator)
        tag_metric_data = ReportUtils._calculate_averages(tag_accumulator)

        # 9.1 对非 average 维度，用策略类聚合替换简单平均
        if custom_agg_dims:
            # dim_name -> output_params 映射
            dim_name_to_output_params = {}
            dim_agg_denominator = {}
            for dim in all_dimensions:
                dim_name = _dim_name(dim)
                if dim_name in custom_agg_dims:
                    dim_name_to_output_params[dim_name] = dim_output_params.get(_dim_id(dim), [])
                    dim_agg_denominator[dim_name] = _dim_agg_denominator(dim)
            ReportUtils._apply_resource_aggregation_strategies(
                metric_data, resource_agg_items, dim_statistic_method, dim_name_to_output_params, dim_agg_denominator)
            ReportUtils._apply_aggregation_strategies(
                tag_metric_data, tag_agg_items, dim_statistic_method, dim_name_to_output_params, dim_agg_denominator)

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
                    result_data[key][res][dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else None
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
                result_data[resource][dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else None
        return result_data

    @staticmethod
    def _apply_resource_aggregation_strategies(metric_data, agg_items, dim_statistic_method, dim_output_params=None,
                                               dim_agg_denominator=None):
        """
        对非 average 维度，用策略类聚合替换简单平均值（resource 级别）。

        agg_items 结构: {dim_name: {resource: [items]}}
        metric_data 结构: {resource: {dim_name: value}}
        dim_agg_denominator: {dim_name: 'round'|'case'} 比率统计分母口径，默认 'round'
        """
        if not agg_items:
            return

        from report_service.domain.services.aggregation_strategies import get_strategy

        for dim_name, resources in agg_items.items():
            method = dim_statistic_method.get(dim_name, 'average')
            strategy = get_strategy(method)
            output_params = (dim_output_params or {}).get(dim_name, [])
            denominator_mode = (dim_agg_denominator or {}).get(dim_name, 'round')

            for resource, items in resources.items():
                if not items:
                    continue
                agg_val = strategy.aggregate(
                    items,
                    output_params=output_params,
                    denominator_mode=denominator_mode,
                )
                if agg_val is not None and resource in metric_data:
                    metric_data[resource][dim_name] = agg_val

    @staticmethod
    def _apply_aggregation_strategies(metric_data, agg_items, dim_statistic_method, dim_output_params=None,
                                      dim_agg_denominator=None):
        """
        对非 average 维度，用策略类聚合替换简单平均值。

        agg_items 结构: {dim_name: {group_key: {resource: [items]}}}
        metric_data 结构: {group_key: {resource: {dim_name: value}}}
        dim_statistic_method: {dim_name: statistic_method}
        dim_output_params: {dim_name: [{param_code, field_path, field_type}, ...]}
        dim_agg_denominator: {dim_name: 'round'|'case'} 比率统计分母口径，默认 'round'
        """
        if not agg_items:
            return

        from report_service.domain.services.aggregation_strategies import get_strategy

        for dim_name, groups in agg_items.items():
            method = dim_statistic_method.get(dim_name, 'average')
            strategy = get_strategy(method)
            output_params = (dim_output_params or {}).get(dim_name, [])
            denominator_mode = (dim_agg_denominator or {}).get(dim_name, 'round')

            for group_key, resources in groups.items():
                for resource, items in resources.items():
                    if not items:
                        continue
                    agg_val = strategy.aggregate(
                        items,
                        output_params=output_params,
                        denominator_mode=denominator_mode,
                    )
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
                    dim_values = ReportUtils.extract_dimension_values(_r_get(result, 'id'), [dim])
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
        test_case_ids = list(set(_r_get(r, 'test_case_id') for r in results if _r_get(r, 'test_case_id')))
        test_cases_map = _grpc_list_testcases_by_ids(test_case_ids)

        for result in results:
            test_case = test_cases_map.get(_r_get(result, 'test_case_id'))
            if not test_case:
                continue
            group = test_case.get('group') if isinstance(test_case, dict) else getattr(test_case, 'group', None)
            group_id = (group.get('id') if isinstance(group, dict) else getattr(group, 'id', None)) if group else "default_group"

            if group_id not in group_scores:
                # 直接使用原始维度名称初始化
                group_scores[group_id] = {_dim_name(dim): [] for dim in all_dimensions}

            dim_values = ReportUtils.extract_dimension_values(_r_get(result, 'id'), all_dimensions, dim_results_map)

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
            device_id = _r_get(result, 'device_id')
            api_id = _r_get(result, 'api_id')

            if device_id:
                if device_id not in device_results:
                    device_results[device_id] = []
                device_results[device_id].append(result)

            if api_id:
                if api_id not in api_results:
                    api_results[api_id] = []
                api_results[api_id].append(result)

        device_stats = []
        for dev_id, res_list in device_results.items():
            device = _grpc_get_device(dev_id)
            if not device: continue

            metrics = ReportUtils._calc_list_metrics(res_list, all_dimensions, dim_results_map)
            total = len(res_list)
            completed = len([r for r in res_list if _r_get(r, 'execution_status') == TaskStatus.COMPLETED.value])

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
            completed = len([r for r in res_list if _r_get(r, 'execution_status') == TaskStatus.COMPLETED.value])

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
                vals = ReportUtils.extract_dimension_values(_r_get(result, 'id'), all_dimensions, dim_results_map)
                # 直接使用原始维度名称获取值
                if vals.get(_dim_name(dim)) is not None:
                    scores.append(vals[_dim_name(dim)])
            metrics[_dim_name(dim)] = (sum(scores) / len(scores)) if scores else 0
        return metrics
