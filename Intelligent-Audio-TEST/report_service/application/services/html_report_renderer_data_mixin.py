# -*- coding: utf-8 -*-
"""HTML 报告渲染器 —— 数据提取 Mixin。

从 html_report_renderer.py 拆分而来，承载 metric_data / tag_metric_data
到资源 × 维度值映射的格式兼容解析（dict / list 多种历史格式）。
"""


class HtmlReportDataMixin:
    """metric_data / tag_metric_data 数据提取与格式兼容解析方法。"""

    @staticmethod
    def _extract_resource_metric_map(metric_data):
        """
        从 metric_data 提取 {resource: {metric: value}} 映射（概览级全局平均）
        处理 dict 和 list 两种格式
        """
        result = {}
        if isinstance(metric_data, dict):
            # 新格式: {resource: {metric: value}}
            is_flat = all(
                isinstance(v, dict) and all(not isinstance(vv, dict) for vv in v.values())
                for v in metric_data.values()
            ) if metric_data else False
            if is_flat:
                for res, metrics in metric_data.items():
                    if isinstance(metrics, dict):
                        result[str(res)] = {k: v for k, v in metrics.items()}
            else:
                # 旧格式: {category: {resource: {metric: value}}} → 取所有 category 的全局
                # 这里取每个 resource 下所有 category 的平均
                temp = {}  # {resource: {metric: [values]}}
                for cat, res_map in metric_data.items():
                    if not isinstance(res_map, dict):
                        continue
                    for res, metrics in res_map.items():
                        if not isinstance(metrics, dict):
                            continue
                        if res not in temp:
                            temp[res] = {}
                        for mk, mv in metrics.items():
                            if mv is not None:
                                temp[res].setdefault(mk, []).append(mv)
                for res, metrics in temp.items():
                    result[res] = {k: sum(v) / len(v) for k, v in metrics.items() if v}

        elif isinstance(metric_data, list):
            # flatten 后的格式
            # 格式1: [{resource, metrics: [{metric, value}]}]  (全局平均)
            if any(isinstance(x, dict) and 'metrics' in x and 'categories' not in x for x in metric_data):
                for item in metric_data:
                    if not isinstance(item, dict):
                        continue
                    res = str(item.get('resource', ''))
                    if not res:
                        continue
                    metrics = item.get('metrics', [])
                    if isinstance(metrics, list):
                        result[res] = {m.get('metric'): m.get('value') for m in metrics if isinstance(m, dict)}

            # 格式2: [{resource, categories: [{categoryId, categoryName, metrics: [{metric, value}]}]}]
            elif any(isinstance(x, dict) and isinstance(x.get('categories'), list) for x in metric_data):
                temp = {}  # {resource: {metric: [values]}}
                for item in metric_data:
                    if not isinstance(item, dict):
                        continue
                    res = str(item.get('resource', ''))
                    if not res:
                        continue
                    if res not in temp:
                        temp[res] = {}
                    for cat in item.get('categories', []):
                        if not isinstance(cat, dict):
                            continue
                        for m in cat.get('metrics', []):
                            if isinstance(m, dict) and m.get('metric') is not None:
                                val = m.get('value')
                                if val is not None:
                                    temp[res].setdefault(m['metric'], []).append(val)
                for res, metrics in temp.items():
                    result[res] = {k: sum(v) / len(v) for k, v in metrics.items() if v}

            # 格式3: [{category_id, category_name, resource, metric, value}] 或 [{metrics: [...]}]
            else:
                for item in metric_data:
                    if not isinstance(item, dict):
                        continue
                    res = str(item.get('resource', ''))
                    if not res:
                        continue
                    if res not in result:
                        result[res] = {}
                    if isinstance(item.get('metrics'), list):
                        for m in item.get('metrics', []):
                            if isinstance(m, dict) and m.get('metric') is not None:
                                result[res][m['metric']] = m.get('value')
                    elif item.get('metric') is not None:
                        result[res][item['metric']] = item.get('value')

        return result

    @staticmethod
    def _extract_resource_category_metric_map(metric_data):
        """
        从 metric_data 提取 {resource: {category_name: {metric: value}}} 映射
        用于按分组对比表
        """
        result = {}
        if isinstance(metric_data, dict):
            # 旧格式: {category: {resource: {metric: value}}}
            for cat, res_map in metric_data.items():
                cat_name = str(cat)
                if not isinstance(res_map, dict):
                    continue
                for res, metrics in res_map.items():
                    if not isinstance(metrics, dict):
                        continue
                    res_key = str(res)
                    if res_key not in result:
                        result[res_key] = {}
                    result[res_key][cat_name] = {k: v for k, v in metrics.items() if v is not None}

        elif isinstance(metric_data, list):
            # flatten 后的格式: [{resource, categories: [{categoryId, categoryName, metrics: [{metric, value}]}]}]
            for item in metric_data:
                if not isinstance(item, dict):
                    continue
                res = str(item.get('resource', ''))
                if not res:
                    continue
                if res not in result:
                    result[res] = {}
                for cat in item.get('categories', []):
                    if not isinstance(cat, dict):
                        continue
                    cat_name = cat.get('categoryName') or cat.get('category_name') or str(cat.get('categoryId', ''))
                    metrics = cat.get('metrics', [])
                    if isinstance(metrics, list):
                        result[res][str(cat_name)] = {
                            m.get('metric'): m.get('value')
                            for m in metrics
                            if isinstance(m, dict) and m.get('metric') is not None
                        }

        return result

    @staticmethod
    def _extract_resource_tag_metric_map(tag_metric_data):
        """
        从 tag_metric_data 提取 {resource: {tag_name: {metric: value}}} 映射
        用于按标签对比表
        """
        result = {}
        if isinstance(tag_metric_data, dict):
            for tag, res_map in tag_metric_data.items():
                tag_name = str(tag)
                if not isinstance(res_map, dict):
                    continue
                for res, metrics in res_map.items():
                    if not isinstance(metrics, dict):
                        continue
                    res_key = str(res)
                    if res_key not in result:
                        result[res_key] = {}
                    result[res_key][tag_name] = {k: v for k, v in metrics.items() if v is not None}

        elif isinstance(tag_metric_data, list):
            for item in tag_metric_data:
                if not isinstance(item, dict):
                    continue
                res = str(item.get('resource', ''))
                if not res:
                    continue
                if res not in result:
                    result[res] = {}
                for tag in item.get('tags', []):
                    if not isinstance(tag, dict):
                        continue
                    tag_name = tag.get('tag_name') or tag.get('tagName') or str(tag.get('tag_id', ''))
                    metrics = tag.get('metrics', [])
                    if isinstance(metrics, list):
                        result[res][str(tag_name)] = {
                            m.get('metric'): m.get('value')
                            for m in metrics
                            if isinstance(m, dict) and m.get('metric') is not None
                        }

        return result
