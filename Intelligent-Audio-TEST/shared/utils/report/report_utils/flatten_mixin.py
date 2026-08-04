from shared.models.models import TestResultDimension, TestCase, Device, API, Task, Dimension
from shared.models.database import db
from shared.utils.result_data_store import load_full_result_data
from shared.schemas.testcase import ReportAudioItem, ReportTestCaseItem


class FlattenMixin:
    @staticmethod
    def flatten_raw_data(raw_data):
        if isinstance(raw_data, list):
            if any(isinstance(x, dict) and isinstance(x.get('metrics'), list) for x in raw_data):
                return raw_data
            grouped = {}
            for item in raw_data:
                if not isinstance(item, dict):
                    continue
                resource = item.get('resource')
                metric = item.get('metric')
                values = item.get('values')
                if resource is None or metric is None:
                    continue
                resource = str(resource)
                if resource not in grouped:
                    grouped[resource] = {"resource": resource, "metrics": []}
                grouped[resource]["metrics"].append(
                    {
                        "metric": str(metric),
                        "values": values if isinstance(values, list) else ([] if values is None else [values]),
                    }
                )
            for g in grouped.values():
                g["metrics"] = sorted(g["metrics"], key=lambda x: x["metric"])
            return sorted(grouped.values(), key=lambda x: x["resource"])
        
        if not isinstance(raw_data, dict):
            return []
        
        groups = []
        for resource in sorted(raw_data.keys(), key=lambda x: str(x)):
            metrics = raw_data.get(resource)
            if not isinstance(metrics, dict):
                continue
            metric_list = []
            for metric in sorted(metrics.keys(), key=lambda x: str(x)):
                values = metrics.get(metric)
                if values is None:
                    values = []
                if not isinstance(values, list):
                    values = [values]
                metric_list.append({"metric": str(metric), "values": values})
            groups.append({"resource": str(resource), "metrics": metric_list})
        return groups
    
    @staticmethod
    def flatten_metric_data(metric_data, category_id_to_name=None, metric_name_to_id=None):
        category_id_to_name = category_id_to_name or {}
        metric_name_to_id = metric_name_to_id or {}
        
        if isinstance(metric_data, list):
            if any(isinstance(x, dict) and isinstance(x.get('categories'), list) for x in metric_data):
                out = []
                for item in metric_data:
                    if not isinstance(item, dict):
                        continue
                    resource = item.get('resource')
                    categories = item.get('categories')
                    if resource is None or not isinstance(categories, list):
                        continue
                    fixed_categories = []
                    for c in categories:
                        if not isinstance(c, dict):
                            continue
                        metrics = c.get('metrics') if isinstance(c.get('metrics'), list) else []
                        fixed_metrics = []
                        for m in metrics:
                            if not isinstance(m, dict):
                                continue
                            metric_name = m.get('metric')
                            if metric_name is None:
                                continue
                            fixed_metrics.append(
                                {
                                    **m,
                                    "id": (
                                        metric_name_to_id.get(str(metric_name))
                                        if metric_name_to_id.get(str(metric_name)) is not None
                                        else (int(m.get("id")) if str(m.get("id") or "").isdigit() else None)
                                    ),
                                }
                            )
                        fixed_categories.append({**c, "metrics": fixed_metrics})
                    out.append({**item, "categories": fixed_categories})
                return out
            
            grouped = {}
            for item in metric_data:
                if not isinstance(item, dict):
                    continue
                category_id = item.get('category_id') or item.get('categoryId')
                category_name = item.get('category_name') or item.get('categoryName')
                resource = item.get('resource')
                if category_id is None or resource is None:
                    continue
                category_id = str(category_id)
                resource = str(resource)
                by_resource = grouped.setdefault(resource, {"resource": resource, "categories": {}})
                by_category = by_resource["categories"].setdefault(
                    category_id,
                    {
                        "categoryId": category_id,
                        "categoryName": str(category_name) if category_name is not None else category_id_to_name.get(category_id, category_id),
                        "metrics": {},
                    },
                )
                
                if isinstance(item.get('metrics'), list):
                    for m in item.get('metrics') or []:
                        if not isinstance(m, dict):
                            continue
                        metric = m.get('metric')
                        if metric is None:
                            continue
                        value = m.get('value', 0)
                        by_category["metrics"][str(metric)] = 0 if value is None else value
                else:
                    metric = item.get('metric')
                    if metric is None:
                        continue
                    value = item.get('value', 0)
                    by_category["metrics"][str(metric)] = 0 if value is None else value
            
            out = []
            for resource in sorted(grouped.keys(), key=lambda x: str(x)):
                cat_map = grouped[resource]["categories"]
                categories = []
                for category_id in sorted(cat_map.keys(), key=lambda x: str(x)):
                    c = cat_map[category_id]
                    metrics = [
                        {"id": metric_name_to_id.get(k), "metric": k, "value": v}
                        for k, v in sorted(c["metrics"].items(), key=lambda kv: kv[0])
                    ]
                    categories.append(
                        {
                            "categoryId": c["categoryId"],
                            "categoryName": c["categoryName"],
                            "metrics": metrics,
                        }
                    )
                out.append({"resource": resource, "categories": categories})
            return out
        
        if not isinstance(metric_data, dict):
            return []

        # 新格式: {resource: {metric: value}}（resource 级别全局平均，无 category 分组）
        # 检测是否为新格式：value 是 dict 且其 value 是 number（不是嵌套 dict）
        is_resource_flat = all(
            isinstance(v, dict) and all(not isinstance(vv, dict) for vv in v.values())
            for v in metric_data.values()
        )

        if is_resource_flat:
            out = []
            for resource in sorted(metric_data.keys(), key=lambda x: str(x)):
                resource_metrics = metric_data.get(resource)
                if not isinstance(resource_metrics, dict):
                    continue
                metrics = [
                    {"id": metric_name_to_id.get(k), "metric": k, "value": (0 if v is None else v)}
                    for k, v in sorted(resource_metrics.items(), key=lambda kv: kv[0])
                ]
                out.append({"resource": str(resource), "metrics": metrics})
            return out

        # 旧格式: {category: {resource: {metric: value}}}
        grouped = {}
        for category_key in sorted(metric_data.keys(), key=lambda x: str(x)):
            category_data = metric_data.get(category_key)
            if not isinstance(category_data, dict):
                continue
            category_id = str(category_key)
            category_name = category_id_to_name.get(category_id, category_id)
            for resource in sorted(category_data.keys(), key=lambda x: str(x)):
                resource_metrics = category_data.get(resource)
                if not isinstance(resource_metrics, dict):
                    continue
                by_resource = grouped.setdefault(str(resource), {"resource": str(resource), "categories": {}})
                by_category = by_resource["categories"].setdefault(
                    category_id,
                    {"categoryId": category_id, "categoryName": category_name, "metrics": {}},
                )
                for metric in sorted(resource_metrics.keys(), key=lambda x: str(x)):
                    value = resource_metrics.get(metric)
                    if value is None:
                        value = 0
                    by_category["metrics"][str(metric)] = value

        out = []
        for resource in sorted(grouped.keys(), key=lambda x: str(x)):
            cat_map = grouped[resource]["categories"]
            categories = []
            for category_id in sorted(cat_map.keys(), key=lambda x: str(x)):
                c = cat_map[category_id]
                metrics = [
                    {"id": metric_name_to_id.get(k), "metric": k, "value": v}
                    for k, v in sorted(c["metrics"].items(), key=lambda kv: kv[0])
                ]
                categories.append({"categoryId": c["categoryId"], "categoryName": c["categoryName"], "metrics": metrics})
            out.append({"resource": resource, "categories": categories})
        return out
    
    @staticmethod
    def flatten_tag_metric_data(tag_metric_data, tag_id_to_name=None, metric_name_to_id=None):
        tag_id_to_name = tag_id_to_name or {}
        metric_name_to_id = metric_name_to_id or {}
        
        if isinstance(tag_metric_data, list):
            if any(isinstance(x, dict) and isinstance(x.get('tags'), list) for x in tag_metric_data):
                out = []
                for item in tag_metric_data:
                    if not isinstance(item, dict):
                        continue
                    resource = item.get('resource')
                    tags = item.get('tags')
                    if resource is None or not isinstance(tags, list):
                        continue
                    fixed_tags = []
                    for t in tags:
                        if not isinstance(t, dict):
                            continue
                        metrics = t.get('metrics') if isinstance(t.get('metrics'), list) else []
                        fixed_metrics = []
                        for m in metrics:
                            if not isinstance(m, dict):
                                continue
                            metric_name = m.get('metric')
                            if metric_name is None:
                                continue
                            mapped = metric_name_to_id.get(str(metric_name))
                            fallback_id = int(m.get("id")) if str(m.get("id") or "").isdigit() else None
                            fixed_metrics.append({**m, "id": mapped if mapped is not None else fallback_id})
                        fixed_tags.append({**t, "metrics": fixed_metrics})
                    out.append({**item, "tags": fixed_tags})
                return out
            
            grouped = {}
            for item in tag_metric_data:
                if not isinstance(item, dict):
                    continue
                tag_id = item.get('tag_id') or item.get('tagId')
                tag_name = item.get('tag_name') or item.get('tagName')
                resource = item.get('resource')
                if tag_id is None or resource is None:
                    continue
                tag_id = str(tag_id)
                resource = str(resource)
                by_resource = grouped.setdefault(resource, {"resource": resource, "tags": {}})
                by_tag = by_resource["tags"].setdefault(
                    tag_id,
                    {
                        "tag_id": tag_id,
                        "tag_name": str(tag_name) if tag_name is not None else tag_id_to_name.get(tag_id, tag_id),
                        "metrics": {},
                    },
                )
                
                if isinstance(item.get('metrics'), list):
                    for m in item.get('metrics') or []:
                        if not isinstance(m, dict):
                            continue
                        metric = m.get('metric')
                        if metric is None:
                            continue
                        value = m.get('value', 0)
                        by_tag["metrics"][str(metric)] = 0 if value is None else value
                else:
                    metric = item.get('metric')
                    if metric is None:
                        continue
                    value = item.get('value', 0)
                    by_tag["metrics"][str(metric)] = 0 if value is None else value
            
            out = []
            for resource in sorted(grouped.keys(), key=lambda x: str(x)):
                tag_map = grouped[resource]["tags"]
                tags = []
                for tag_id in sorted(tag_map.keys(), key=lambda x: str(x)):
                    t = tag_map[tag_id]
                    metrics = [
                        {"id": metric_name_to_id.get(k), "metric": k, "value": v}
                        for k, v in sorted(t["metrics"].items(), key=lambda kv: kv[0])
                    ]
                    tags.append({"tag_id": t["tag_id"], "tag_name": t["tag_name"], "metrics": metrics})
                out.append({"resource": resource, "tags": tags})
            return out
        
        if not isinstance(tag_metric_data, dict):
            return []
        
        grouped = {}
        for tag_key in sorted(tag_metric_data.keys(), key=lambda x: str(x)):
            tag_data = tag_metric_data.get(tag_key)
            if not isinstance(tag_data, dict):
                continue
            tag_key_str = str(tag_key)
            tag_name = tag_id_to_name.get(tag_key_str) or tag_key_str
            for resource in sorted(tag_data.keys(), key=lambda x: str(x)):
                resource_metrics = tag_data.get(resource)
                if not isinstance(resource_metrics, dict):
                    continue
                by_resource = grouped.setdefault(str(resource), {"resource": str(resource), "tags": {}})
                by_tag = by_resource["tags"].setdefault(
                    tag_key_str,
                    {"tag_id": tag_key_str, "tag_name": tag_name, "metrics": {}},
                )
                for metric in sorted(resource_metrics.keys(), key=lambda x: str(x)):
                    value = resource_metrics.get(metric)
                    if value is None:
                        value = 0
                    by_tag["metrics"][str(metric)] = value
        
        out = []
        for resource in sorted(grouped.keys(), key=lambda x: str(x)):
            tag_map = grouped[resource]["tags"]
            tags = []
            for tag_key in sorted(tag_map.keys(), key=lambda x: str(x)):
                t = tag_map[tag_key]
                metrics = [
                    {"id": metric_name_to_id.get(k), "metric": k, "value": v}
                    for k, v in sorted(t["metrics"].items(), key=lambda kv: kv[0])
                ]
                tags.append({"tag_id": t["tag_id"], "tag_name": t["tag_name"], "metrics": metrics})
            out.append({"resource": resource, "tags": tags})
        return out
    
    @staticmethod
    def flatten_case_type_stats(case_type_stats, group_id_to_name=None, metric_name_to_id=None):
        group_id_to_name = group_id_to_name or {}
        metric_name_to_id = metric_name_to_id or {}
        grouped = {}
        
        if isinstance(case_type_stats, list):
            for item in case_type_stats:
                if not isinstance(item, dict):
                    continue
                group_id = item.get('group_id') or item.get('groupId')
                group_name = item.get('group_name') or item.get('groupName')
                metric = item.get('metric')
                value = item.get('value', 0)
                if group_id is None or metric is None:
                    continue
                group_id = str(group_id)
                if group_id not in grouped:
                    grouped[group_id] = {
                        "group_id": group_id,
                        "group_name": str(group_name) if group_name is not None else group_id_to_name.get(group_id, group_id),
                        "metrics": [],
                    }
                m = str(metric)
                grouped[group_id]["metrics"].append({"id": metric_name_to_id.get(m), "metric": m, "value": value})
            for group in grouped.values():
                group["metrics"] = sorted(group["metrics"], key=lambda x: x["metric"])
            return sorted(grouped.values(), key=lambda x: x["group_id"])
        
        if not isinstance(case_type_stats, dict):
            return []
        
        for group_key in sorted(case_type_stats.keys(), key=lambda x: str(x)):
            group_data = case_type_stats.get(group_key)
            if not isinstance(group_data, dict):
                continue
            group_id = str(group_key)
            group_name = group_id_to_name.get(group_id, group_id)
            metrics = []
            for metric in sorted(group_data.keys(), key=lambda x: str(x)):
                value = group_data.get(metric)
                if value is None:
                    value = 0
                m = str(metric)
                metrics.append({"id": metric_name_to_id.get(m), "metric": m, "value": value})
            grouped[group_id] = {"group_id": group_id, "group_name": group_name, "metrics": metrics}
        return list(grouped.values())
