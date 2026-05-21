from backend.models.models import TestResultDimension, TestCase, Device, API, Task, Dimension
from backend.models.database import db
from backend.schemas.testcase import ReportAudioItem, ReportTestCaseItem

class ReportUtils:
    @staticmethod
    def get_task_time_prefix(task):
        """获取任务执行标识前缀（任务ID + 时间）"""
        if not task:
            return "unknowntask"
        
        # 优先使用任务ID确保绝对唯一，辅以时间提高可读性
        time_str = task.started_at.strftime('%Y%m%d%H%M') if task.started_at else "notime"
        return f"t{task.id}-{time_str}"

    @staticmethod
    def get_resource_name(result, task=None, use_time_prefix=False):
        """
        获取资源的唯一标识名称。
        
        统一格式：任务ID-时间-ID-名称小写-version-result_type后缀
        例如：t246-202603251543-16-plaud-1.0.0 或 t246-202603251543-16-plaud-1.0.0-recording
        
        确保唯一性，所有字母小写。
        支持根据 result_data 中的 result_type 添加后缀以区分不同结果类型（如 recording/fix）。
        """
        version = None
        result_type_suffix = ""

        try:
            if hasattr(result, 'result_data') and result.result_data:
                if isinstance(result.result_data, dict):
                    result_type = result.result_data.get('result_type')
                else:
                    import json
                    result_data_dict = json.loads(result.result_data) if isinstance(result.result_data, str) else {}
                    result_type = result_data_dict.get('result_type')
                
                if result_type and result_type != 'default':
                    result_type_suffix = f"-{result_type}"
        except:
            pass

        if use_time_prefix and task:
            prefix = ReportUtils.get_task_time_prefix(task)
            
            if hasattr(result, 'api_id') and result.api_id:
                api_id = result.api_id
                api = API.query.get(api_id)
                if api:
                    version = ReportUtils._extract_api_version(api)
                    base_resource = f"{api.id}-{api.name.lower()}"
                else:
                    base_resource = f"{api_id}-未知api"
            
            elif hasattr(result, 'device_id') and result.device_id:
                device_id = result.device_id
                device = Device.query.get(device_id)
                if device:
                    version = getattr(device, "app_version", None)
                    base_resource = f"{device.id}-{device.name.lower()}"
                else:
                    base_resource = f"{device_id}-未知设备"
            
            if not base_resource:
                if isinstance(result, dict):
                    if result.get('api_id'):
                        base_resource = f"{result.get('api_id')}-未知api"
                    elif result.get('device_id'):
                        base_resource = f"{result.get('device_id')}-未知设备"

            if not base_resource:
                base_resource = "0-默认资源"

            resource = f"{prefix}-{base_resource}"
            if version:
                resource = f"{resource}-{version}"
            return f"{resource}{result_type_suffix}"

        if hasattr(result, 'api_id') and result.api_id:
            api_id = result.api_id
            api = API.query.get(api_id)
            if api:
                version = ReportUtils._extract_api_version(api)
                base_resource = f"{api.id}-{api.name.lower()}"
            else:
                base_resource = f"{api_id}-未知api"
        
        elif hasattr(result, 'device_id') and result.device_id:
            device_id = result.device_id
            device = Device.query.get(device_id)
            if device:
                version = getattr(device, "app_version", None)
                base_resource = f"{device.id}-{device.name.lower()}"
            else:
                base_resource = f"{device_id}-未知设备"
        
        if not base_resource:
            if isinstance(result, dict):
                if result.get('api_id'):
                    base_resource = f"{result.get('api_id')}-未知api"
                elif result.get('device_id'):
                    base_resource = f"{result.get('device_id')}-未知设备"

        if not base_resource:
            base_resource = "0-默认资源"

        resource = base_resource
        if version:
            resource = f"{resource}-{version}"
        return f"{resource}{result_type_suffix}"
    
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
            
            # 7. 更新累加器 (Category & Tags)
            # 初始化累加器结构
            if category not in category_accumulator:
                category_accumulator[category] = {}
            if resource not in category_accumulator[category]:
                # 直接使用原始维度名称
                category_accumulator[category][resource] = {dim.name: {'sum': 0, 'count': 0} for dim in all_dimensions}
                category_accumulator[category][resource]['success_rate'] = {'sum': 0, 'count': 0}
            elif 'success_rate' not in category_accumulator[category][resource]:
                 category_accumulator[category][resource]['success_rate'] = {'sum': 0, 'count': 0}

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
                    
                    # Tag
                    for tag in tags:
                        if dim_name in tag_accumulator[tag][resource]:
                            tag_accumulator[tag][resource][dim_name]['sum'] += score
                            tag_accumulator[tag][resource][dim_name]['count'] += 1
                    
                    # Raw Data
                    if dim_name in raw_data[resource]:
                        raw_data[resource][dim_name].append(score)

        # 9. 计算平均值 (Metric Data & Tag Metric Data)
        metric_data = ReportUtils._calculate_averages(category_accumulator)
        tag_metric_data = ReportUtils._calculate_averages(tag_accumulator)
        
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
    def _calculate_tag_category_averages(tag_accumulator, tag_category_map):
        """
        辅助函数：按标签分类计算平均值
        
        参数:
            tag_accumulator: 标签累加器 {tag_name: {resource: {dim: {sum, count}}}}
            tag_category_map: 标签到分类的映射 {tag_name: category_id}
        
        返回:
            dict: 按分类组织的统计数据
        """
        from backend.models.models import TagCategory
        
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
    def _build_id_name_map(items):
        mapping = {}
        if not isinstance(items, list):
            return mapping
        for item in items:
            if isinstance(item, dict) and item.get('id') is not None:
                key = str(item.get('id'))
                name = item.get('name')
                if name is not None:
                    mapping[key] = str(name)
        return mapping

    @staticmethod
    def _build_metric_name_id_map(items):
        mapping = {}
        if not isinstance(items, list):
            return mapping
        for item in items:
            if not isinstance(item, dict):
                continue
            metric_id = item.get('id')
            name = item.get('name')
            if metric_id is None or name is None:
                continue
            try:
                mapping[str(name)] = int(metric_id)
            except Exception:
                continue
        return mapping
    
    @staticmethod
    def _dt_to_iso(value):
        try:
            return value.isoformat() if value is not None else None
        except Exception:
            return None
    
    @staticmethod
    def serialize_device(device):
        if device is None:
            return None
        return {
            "id": device.id,
            "name": device.name,
            "model": getattr(device, "model", None),
            "description": getattr(device, "description", None),
            "type": getattr(device, "type", None),
            "system": getattr(device, "system", None),
            "system_version": getattr(device, "system_version", None),
            "app_name": getattr(device, "app_name", None),
            "app_version": getattr(device, "app_version", None),
            "location": getattr(device, "location", None),
            "max_audio_duration": getattr(device, "max_audio_duration", None),
            "needs_prompt_audio": getattr(device, "needs_prompt_audio", None),
            "connection_type": getattr(device, "connection_type", None),
            "keywords": getattr(device, "keywords", None),
            "serial_number": getattr(device, "serial_number", None),
            "ip": getattr(device, "ip", None),
            "status": getattr(device, "status", None),
            "last_online_at": ReportUtils._dt_to_iso(getattr(device, "last_online_at", None)),
            "created_at": ReportUtils._dt_to_iso(getattr(device, "created_at", None)),
            "updated_at": ReportUtils._dt_to_iso(getattr(device, "updated_at", None)),
        }
    
    @staticmethod
    def serialize_api(api):
        if api is None:
            return None
        return {
            "id": api.id,
            "name": api.name,
            "vendor": getattr(api, "vendor", None),
            "api_url": getattr(api, "api_url", None),
            "description": getattr(api, "description", None),
            "status": getattr(api, "status", None),
            "max_process": getattr(api, "max_process", None),
            "max_timeout": getattr(api, "max_timeout", None),
            "max_audio_duration": getattr(api, "max_audio_duration", None),
            "health_score": getattr(api, "health_score", None),
            "created_at": ReportUtils._dt_to_iso(getattr(api, "created_at", None)),
            "updated_at": ReportUtils._dt_to_iso(getattr(api, "updated_at", None)),
        }

    @staticmethod
    def _extract_api_version(api):
        if api is None:
            return None
        meta = getattr(api, "meta", None)
        if not isinstance(meta, dict):
            return None
        for key in ("version", "api_version", "model_version", "app_version"):
            value = meta.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _format_resource_label(task, name, version=None, use_time_prefix=False):
        if use_time_prefix and task:
            prefix = ReportUtils.get_task_time_prefix(task)
            resource = f"{prefix}-{name}"
            if version:
                resource = f"{resource}-{version}"
            return resource

        parts = []
        if name is not None and str(name).strip():
            parts.append(str(name).strip())
        if version is not None and str(version).strip():
            parts.append(str(version).strip())
        return "-".join(parts) if parts else ""

    @staticmethod
    def build_resource_headers(resources, results=None, tasks_map=None, use_time_prefix=False):
        headers_by_key = {}

        if isinstance(results, list):
            for result in results:
                task = None
                if tasks_map and hasattr(result, "task_id"):
                    task = tasks_map.get(result.task_id)

                key = ReportUtils.get_resource_name(result, task, use_time_prefix=use_time_prefix)
                if not key or key in headers_by_key:
                    continue

                result_type = None
                try:
                    if hasattr(result, 'result_data') and result.result_data:
                        if isinstance(result.result_data, dict):
                            result_type = result.result_data.get('result_type')
                        else:
                            import json
                            result_data_dict = json.loads(result.result_data) if isinstance(result.result_data, str) else {}
                            result_type = result_data_dict.get('result_type')
                        
                        if result_type == 'default':
                            result_type = None
                except:
                    pass

                if getattr(result, "api_id", None):
                    api = db.session.get(API, result.api_id)
                    headers_by_key[key] = {
                        "key": str(key),
                        "label": str(key),
                        "type": "api",
                        "id": int(result.api_id),
                        "name": str(api.name) if api else str(result.api_id),
                        "version": ReportUtils._extract_api_version(api) if api else None,
                        "result_type": result_type,
                        "editable": True,
                    }
                elif getattr(result, "device_id", None):
                    device = db.session.get(Device, result.device_id)
                    headers_by_key[key] = {
                        "key": str(key),
                        "label": str(key),
                        "type": "device",
                        "id": int(result.device_id),
                        "name": str(device.name) if device else str(result.device_id),
                        "version": str(getattr(device, "app_version", None)) if device else None,
                        "result_type": result_type,
                        "editable": True,
                    }
                else:
                    headers_by_key[key] = {
                        "key": str(key),
                        "label": str(key),
                        "type": "unknown",
                        "id": None,
                        "name": str(key),
                        "version": None,
                        "result_type": result_type,
                        "editable": True,
                    }

        ordered = []
        if isinstance(resources, list):
            for key in resources:
                key_str = str(key)
                if key_str in headers_by_key:
                    ordered.append(headers_by_key[key_str])
                else:
                    ordered.append(
                        {
                            "key": key_str,
                            "label": key_str,
                            "type": "unknown",
                            "id": None,
                            "name": key_str,
                            "version": None,
                            "editable": True,
                        }
                    )
            return ordered

        return list(headers_by_key.values())
    
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
                        "category_id": category_id,
                        "category_name": str(category_name) if category_name is not None else category_id_to_name.get(category_id, category_id),
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
                            "category_id": c["category_id"],
                            "category_name": c["category_name"],
                            "metrics": metrics,
                        }
                    )
                out.append({"resource": resource, "categories": categories})
            return out
        
        if not isinstance(metric_data, dict):
            return []
        
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
                    {"category_id": category_id, "category_name": category_name, "metrics": {}},
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
                categories.append({"category_id": c["category_id"], "category_name": c["category_name"], "metrics": metrics})
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
            tag_id = str(tag_key)
            tag_name = tag_id_to_name.get(tag_id, tag_id)
            for resource in sorted(tag_data.keys(), key=lambda x: str(x)):
                resource_metrics = tag_data.get(resource)
                if not isinstance(resource_metrics, dict):
                    continue
                by_resource = grouped.setdefault(str(resource), {"resource": str(resource), "tags": {}})
                by_tag = by_resource["tags"].setdefault(
                    tag_id,
                    {"tag_id": tag_id, "tag_name": tag_name, "metrics": {}},
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
            for tag_id in sorted(tag_map.keys(), key=lambda x: str(x)):
                t = tag_map[tag_id]
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
                            "api": param_info.get('api'),
                            "e2e": param_info.get('e2e'),
                        }
                        # 如果有结构化数据（segments, text, json），也保留
                        if param_info.get('segments'):
                            normalized_ref_params[code]["segments"] = param_info.get('segments')
                        if param_info.get('text'):
                            normalized_ref_params[code]["text"] = param_info.get('text')
                        if param_info.get('json'):
                            normalized_ref_params[code]["json"] = param_info.get('json')
                    new_case['reference_params'] = normalized_ref_params
                
                # 处理 algorithm_results 字段（动态保留所有算法结果字段）
                algorithm_results = case.get('algorithm_results')
                if isinstance(algorithm_results, dict) and algorithm_results:
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
