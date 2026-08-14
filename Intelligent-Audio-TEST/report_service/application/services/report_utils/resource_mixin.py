# -*- coding: utf-8 -*-
import logging
from shared.utils.result_data_store import load_full_result_data
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_device,
    _grpc_get_api,
    _grpc_get_devices_by_ids,
    _grpc_get_apis_by_ids,
)

logger = logging.getLogger(__name__)


class ResourceMixin:
    @staticmethod
    def get_task_time_prefix(task):
        """获取任务执行标识前缀（任务ID + 时间）"""
        if not task:
            return "unknowntask"

        # 优先使用任务ID确保绝对唯一，辅以时间提高可读性
        started_at = task.get('started_at') if isinstance(task, dict) else getattr(task, 'started_at', None)
        task_id = task.get('id') if isinstance(task, dict) else getattr(task, 'id', None)
        # started_at 可能是 ISO 字符串或 datetime
        from datetime import datetime
        if isinstance(started_at, str) and started_at:
            try:
                time_str = datetime.fromisoformat(started_at).strftime('%Y%m%d%H%M')
            except Exception:
                time_str = "notime"
        elif hasattr(started_at, 'strftime'):
            time_str = started_at.strftime('%Y%m%d%H%M')
        else:
            time_str = "notime"
        return f"t{task_id}-{time_str}"

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
                full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                if isinstance(full_data, dict):
                    result_type = full_data.get('result_type')
                    if result_type and result_type != 'default':
                        result_type_suffix = f"-{result_type}"
        except Exception as _e:
            import logging as _log
            _log.getLogger(__name__).warning(f"Failed to extract result_type: {_e}")

        if use_time_prefix and task:
            prefix = ReportUtils.get_task_time_prefix(task)

            if hasattr(result, 'api_id') and result.api_id:
                api_id = result.api_id
                api = _grpc_get_api(api_id)
                if api:
                    version = ReportUtils._extract_api_version(api)
                    base_resource = f"{api.get('id')}-{str(api.get('name', '')).lower()}"
                else:
                    base_resource = f"{api_id}-未知api"

            elif hasattr(result, 'device_id') and result.device_id:
                device_id = result.device_id
                device = _grpc_get_device(device_id)
                if device:
                    version = device.get("app_version")
                    base_resource = f"{device.get('id')}-{str(device.get('name', '')).lower()}"
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
            api = _grpc_get_api(api_id)
            if api:
                version = ReportUtils._extract_api_version(api)
                base_resource = f"{api.get('id')}-{str(api.get('name', '')).lower()}"
            else:
                base_resource = f"{api_id}-未知api"

        elif hasattr(result, 'device_id') and result.device_id:
            device_id = result.device_id
            device = _grpc_get_device(device_id)
            if device:
                version = device.get("app_version")
                base_resource = f"{device.get('id')}-{str(device.get('name', '')).lower()}"
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
    def _build_id_name_map(items):
        mapping = {}
        if not isinstance(items, list):
            return mapping
        for item in items:
            if isinstance(item, dict):
                if item.get('id') is not None:
                    key = str(item.get('id'))
                    name = item.get('name')
                    if name is not None:
                        mapping[key] = str(name)
                elif item.get('name') is not None:
                    name = str(item.get('name'))
                    mapping[name] = name
            elif isinstance(item, str):
                mapping[item] = item
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
            # 兼容已经是 ISO 字符串或 None 的情况
            return value if isinstance(value, str) else None

    @staticmethod
    def serialize_device(device):
        if device is None:
            return None
        # 兼容 dict 与 ORM 对象
        if isinstance(device, dict):
            return {
                "id": device.get("id"),
                "name": device.get("name"),
                "model": device.get("model"),
                "description": device.get("description"),
                "type": device.get("type"),
                "system": device.get("system"),
                "system_version": device.get("system_version"),
                "app_name": device.get("app_name"),
                "app_version": device.get("app_version"),
                "location": device.get("location"),
                "max_audio_duration": device.get("max_audio_duration"),
                "needs_prompt_audio": device.get("needs_prompt_audio"),
                "connection_type": device.get("connection_type"),
                "keywords": device.get("keywords"),
                "serial_number": device.get("serial_number"),
                "ip": device.get("ip"),
                "status": device.get("status"),
                "last_online_at": ReportUtils._dt_to_iso(device.get("last_online_at")),
                "created_at": ReportUtils._dt_to_iso(device.get("created_at")),
                "updated_at": ReportUtils._dt_to_iso(device.get("updated_at")),
            }
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
        # 兼容 dict 与 ORM 对象
        if isinstance(api, dict):
            return {
                "id": api.get("id"),
                "name": api.get("name"),
                "vendor": api.get("vendor"),
                "api_url": api.get("api_url"),
                "description": api.get("description"),
                "status": api.get("status"),
                "max_process": api.get("max_process"),
                "max_timeout": api.get("max_timeout"),
                "max_audio_duration": api.get("max_audio_duration"),
                "health_score": api.get("health_score"),
                "created_at": ReportUtils._dt_to_iso(api.get("created_at")),
                "updated_at": ReportUtils._dt_to_iso(api.get("updated_at")),
            }
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
        # 兼容 dict 与 ORM 对象
        meta = api.get("meta") if isinstance(api, dict) else getattr(api, "meta", None)
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
                        full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                        if isinstance(full_data, dict):
                            result_type = full_data.get('result_type')
                            if result_type == 'default':
                                result_type = None
                except Exception:
                    logger.debug("提取结果类型失败 result_id=%s", getattr(result, 'id', None), exc_info=True)

                if getattr(result, "api_id", None):
                    api = _grpc_get_api(result.api_id)
                    headers_by_key[key] = {
                        "key": str(key),
                        "label": str(key),
                        "type": "api",
                        "id": int(result.api_id),
                        "name": str(api.get('name')) if api else str(result.api_id),
                        "version": ReportUtils._extract_api_version(api) if api else None,
                        "result_type": result_type,
                        "editable": True,
                    }
                elif getattr(result, "device_id", None):
                    device = _grpc_get_device(result.device_id)
                    headers_by_key[key] = {
                        "key": str(key),
                        "label": str(key),
                        "type": "device",
                        "id": int(result.device_id),
                        "name": str(device.get('name')) if device else str(result.device_id),
                        "version": str(device.get("app_version")) if device else None,
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
