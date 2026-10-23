"""设备/播放/API 三资源导入导出 Service（INT-816）。

网关级导入导出，镜像 testcases/evaluation 现有模式（testcase_import_service /
testcase_export_service / evaluation_bp GET /dimensions/export），不扩展
data-transfer、不改 device_service（ACL create/get_all 已具备）。

- GET /{resource}/export（query：ids 可选、format∈{json,excel} 默认 json）
  → 文件流下载，CQRS 查询侧无副作用
- POST /{resource}/import（multipart 文件）→ {imported/updated/skipped} 计数报告

匹配键：测试设备=serial_number、播放设备=device_unique_id（兜底 name）、
API=name；匹配到→更新、未匹配→新建、非法行→跳过并回报告（页面设计 §4.5）。
"""
import io
import json
import logging
from datetime import datetime

import pandas as pd
from fastapi.responses import Response

from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.acl import (
    ApiConfigAclRepositoryImpl,
    DeviceAclRepositoryImpl,
    PlaybackConfigAclRepositoryImpl,
)
from api_gateway.schemas.api import ApiCreateInput, ApiUpdateInput
from api_gateway.schemas.common import (
    ResourceExportQuery,
    ResourceImportResult,
)
from api_gateway.schemas.device import DeviceCreateSchema, DeviceUpdateSchema
from api_gateway.schemas.playback import PlaybackCreateSchema, PlaybackUpdateSchema
from api_gateway.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)

_device_acl = DeviceAclRepositoryImpl()
_playback_acl = PlaybackConfigAclRepositoryImpl()
_api_acl = ApiConfigAclRepositoryImpl()

# 导入/导出取全量的分页大小（对齐 evaluation 导出 _EXPORT_ALL_PER_PAGE）
_EXPORT_ALL_PER_PAGE = 100000

_EXCEL_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
_EXCEL_EXTENSIONS = ('xlsx', 'xls')


class _ResourceSpec:
    """单个资源的导入导出配置（匹配键 / ACL / 导出字段 / 文件命名）。"""

    def __init__(self, resource, acl, match_key, match_key_alt, create_schema,
                 update_schema, export_key, export_prefix, export_sheet,
                 export_fields, complex_fields):
        self.resource = resource
        self.acl = acl
        self.match_key = match_key
        self.match_key_alt = match_key_alt
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.export_key = export_key
        self.export_prefix = export_prefix
        self.export_sheet = export_sheet
        self.export_fields = export_fields
        self.complex_fields = set(complex_fields)


_TEST_DEVICE_FIELDS = [
    'name', 'model', 'type', 'system', 'system_version', 'app_name',
    'app_version', 'description', 'location', 'max_audio_duration',
    'needs_prompt_audio', 'prompt_config', 'connection_type',
    'keywords', 'serial_number', 'ip', 'status', 'supported_algorithms',
]

_PLAYBACK_DEVICE_FIELDS = [
    'name', 'model', 'device_type', 'sample_rate', 'device_unique_id',
    'channel_index', 'description', 'status',
]

_API_FIELDS = [
    'name', 'vendor', 'description', 'meta', 'algorithm_type',
    'default_max_process', 'default_max_timeout', 'default_max_audio_duration',
    'status', 'endpoints', 'output_types', 'device_type', 'adapter_class',
    'audio_config',
]


def _make_resource_specs():
    """构建三资源导入导出规格（模块导入期惰性构建，避免 ACL 初始化早于配置）。"""
    return {
        'test-devices': _ResourceSpec(
            resource='test-devices',
            acl=_device_acl,
            match_key='serial_number',
            match_key_alt=None,
            create_schema=DeviceCreateSchema,
            update_schema=DeviceUpdateSchema,
            export_key='test_devices',
            export_prefix='test_devices',
            export_sheet='测试设备',
            export_fields=_TEST_DEVICE_FIELDS,
            complex_fields=['prompt_config', 'supported_algorithms'],
        ),
        'playback-devices': _ResourceSpec(
            resource='playback-devices',
            acl=_playback_acl,
            match_key='device_unique_id',
            match_key_alt='name',
            create_schema=PlaybackCreateSchema,
            update_schema=PlaybackUpdateSchema,
            export_key='playback_devices',
            export_prefix='playback_devices',
            export_sheet='播放设备',
            export_fields=_PLAYBACK_DEVICE_FIELDS,
            complex_fields=[],
        ),
        'apis': _ResourceSpec(
            resource='apis',
            acl=_api_acl,
            match_key='name',
            match_key_alt=None,
            create_schema=ApiCreateInput,
            update_schema=ApiUpdateInput,
            export_key='apis',
            export_prefix='apis',
            export_sheet='API配置',
            export_fields=_API_FIELDS,
            complex_fields=['meta', 'endpoints', 'output_types', 'audio_config'],
        ),
    }


_RESOURCE_SPECS = _make_resource_specs()


def _is_empty(val):
    """单元格空判定：None / pandas NaN / 空白字符串。"""
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except Exception:
        pass
    return isinstance(val, str) and not val.strip()


def _normalize_key(val):
    """匹配键规范化：空值返回 None，其余转为去空白字符串。"""
    if _is_empty(val):
        return None
    text = str(val).strip()
    return text or None


def _clean_cell(val):
    """单元格清洗：None / NaN → None，其余原样返回。"""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    return val


class ResourceImportExportService:
    """设备/播放/API 三资源导入导出服务（薄编排层）。

    静态方法 + success_response/error_response 包装，路由层直接返回。
    """

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    @staticmethod
    def export(resource: str):
        """导出指定资源（json/excel 文件流，默认 json）。"""
        spec = _RESOURCE_SPECS[resource]
        try:
            query = ResourceExportQuery.model_validate({
                k: v[0] if isinstance(v, list) else v
                for k, v in request.args.to_dict().items()
            })
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        result = spec.acl.get_all(page=1, per_page=_EXPORT_ALL_PER_PAGE)
        if not result.get('success'):
            return error_response(result.get('message', '获取数据失败'))

        raw = result.get('data') or {}
        items = raw.get('items', []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        if query.ids:
            id_set = set(query.ids)
            items = [it for it in items if it.get('id') in id_set]

        rows = ResourceImportExportService._build_export_rows(spec, items)
        format_type = (query.format or 'json').lower()
        if format_type == 'excel':
            return ResourceImportExportService._render_excel(spec, rows)
        if format_type == 'json':
            return ResourceImportExportService._render_json(spec, rows)
        return error_response(f"不支持的导出格式: {format_type}")

    @staticmethod
    def _build_export_rows(spec, items):
        """将 ACL 返回的条目裁剪为导出字段行（snake_case，可回灌导入）。"""
        rows = []
        for item in items:
            row = {}
            for field in spec.export_fields:
                if field in item:
                    row[field] = item.get(field)
            rows.append(row)
        return rows

    @staticmethod
    def _render_excel(spec, rows):
        """Excel 导出：复杂字段（dict/list）序列化为 JSON 字符串单元格。"""
        export_rows = []
        for row in rows:
            new_row = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    new_row[k] = json.dumps(v, ensure_ascii=False, default=str)
                else:
                    new_row[k] = v
            export_rows.append(new_row)

        df = pd.DataFrame(export_rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=spec.export_sheet)
        output.seek(0)

        filename = f"{spec.export_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return Response(
            content=output.getvalue(),
            media_type=_EXCEL_MEDIA_TYPE,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @staticmethod
    def _render_json(spec, rows):
        """JSON 导出：{resource_key: [...], exported_at, total_count} 文件流。"""
        payload = {
            spec.export_key: rows,
            'exported_at': now_cst().isoformat(),
            'total_count': len(rows),
        }
        content = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
        filename = f"{spec.export_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return Response(
            content=content,
            media_type='application/json',
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # ------------------------------------------------------------------
    # 导入
    # ------------------------------------------------------------------
    @staticmethod
    def import_resource(resource: str):
        """导入指定资源（multipart 文件），返回成功/更新/跳过计数报告。"""
        spec = _RESOURCE_SPECS[resource]
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            file = request.files['file']
            if not file.filename:
                return error_response("未选择文件")

            rows, err = ResourceImportExportService._parse_import_file(spec, file)
            if err is not None:
                return err

            existing_by_key = ResourceImportExportService._fetch_existing_by_key(spec)
            imported_count, updated_count, skipped_count, errors = \
                ResourceImportExportService._apply_rows(spec, rows, existing_by_key)

            return success_response(
                ResourceImportResult(
                    imported_count=imported_count,
                    updated_count=updated_count,
                    skipped_count=skipped_count,
                    errors=errors,
                ),
                f"成功导入 {imported_count} 个，更新 {updated_count} 个，跳过 {skipped_count} 个",
            )
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def _parse_import_file(spec, file):
        """解析上传文件（JSON / CSV / Excel），返回 (rows, None) 或 (None, err)。"""
        filename = (file.filename or '').lower()
        ext = filename.rsplit('.', 1)[-1] if '.' in filename else ''

        try:
            if ext == 'json':
                data = json.loads(file.read().decode('utf-8'))
                rows = data.get(spec.export_key) if isinstance(data, dict) else data
            elif ext == 'csv':
                df = pd.read_csv(io.BytesIO(file.read()), encoding='utf-8-sig')
                rows = df.to_dict('records')
            elif ext in _EXCEL_EXTENSIONS:
                df = pd.read_excel(io.BytesIO(file.read()))
                rows = df.to_dict('records')
            else:
                return None, error_response("仅支持 JSON, CSV 或 Excel 格式的导入")
        except Exception as e:
            return None, error_response(f"文件解析失败: {str(e)}")

        if not isinstance(rows, list) or not rows:
            return None, error_response("导入数据为空")
        return rows, None

    @staticmethod
    def _fetch_existing_by_key(spec):
        """拉取现有记录并按键建索引 {match_key: item}（仅非空键）。

        主键与兜底键（如播放设备 name）都入索引，使「行缺唯一ID但同名」也能
        命中现有记录（INT-816 契约：device_unique_id 兜底 name）。
        """
        result = spec.acl.get_all(page=1, per_page=_EXPORT_ALL_PER_PAGE)
        if not result.get('success'):
            return {}
        raw = result.get('data') or {}
        items = raw.get('items', []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])

        by_key = {}
        for item in items:
            key = _normalize_key(item.get(spec.match_key))
            if key is not None:
                by_key.setdefault(key, item)
            if spec.match_key_alt:
                alt_key = _normalize_key(item.get(spec.match_key_alt))
                if alt_key is not None:
                    by_key.setdefault(alt_key, item)
        return by_key

    @staticmethod
    def _apply_rows(spec, rows, existing_by_key):
        """逐行导入：匹配到→更新、未匹配→新建、非法行→跳过并记录错误。"""
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        for idx, raw_row in enumerate(rows):
            try:
                row = ResourceImportExportService._clean_row(spec, raw_row)
                key = _normalize_key(row.get(spec.match_key))
                if key is None and spec.match_key_alt:
                    key = _normalize_key(row.get(spec.match_key_alt))

                if key is None:
                    skipped_count += 1
                    errors.append(f"第{idx + 1}行: 缺少匹配键 {spec.match_key}")
                    continue

                existing = existing_by_key.get(key)
                if existing is not None:
                    payload = ResourceImportExportService._build_update_payload(spec, row)
                    if payload is None:
                        skipped_count += 1
                        errors.append(f"第{idx + 1}行: 数据校验失败，无法更新")
                        continue
                    res = spec.acl.update(existing.get('id'), payload)
                    if not res.get('success'):
                        raise Exception(res.get('message') or '更新失败')
                    updated_count += 1
                else:
                    payload = ResourceImportExportService._build_create_payload(spec, row)
                    if payload is None:
                        skipped_count += 1
                        errors.append(f"第{idx + 1}行: 缺少必填字段，无法新建")
                        continue
                    res = spec.acl.create(payload)
                    if not res.get('success'):
                        raise Exception(res.get('message') or '创建失败')
                    imported_count += 1
            except Exception as e:
                skipped_count += 1
                errors.append(f"第{idx + 1}行: {str(e)}")

        return imported_count, updated_count, skipped_count, errors

    @staticmethod
    def _clean_row(spec, raw_row):
        """清洗单行：NaN → 剔除空单元格；复杂字段 JSON 字符串回解析为对象。"""
        row = {}
        for k, v in raw_row.items():
            v = _clean_cell(v)
            if v is None:
                continue
            if k in spec.complex_fields and isinstance(v, str):
                stripped = v.strip()
                if stripped.startswith('{') or stripped.startswith('['):
                    try:
                        v = json.loads(stripped)
                    except Exception:
                        pass
            row[k] = v
        return row

    @staticmethod
    def _build_update_payload(spec, row):
        """按更新 schema 校验并 dump（exclude_none），非法返回 None。"""
        try:
            model = spec.update_schema.model_validate(row)
        except Exception:
            return None
        return model.model_dump(by_alias=False, exclude_none=True)

    @staticmethod
    def _build_create_payload(spec, row):
        """按创建 schema 校验并 dump（exclude_none），非法返回 None。"""
        try:
            model = spec.create_schema.model_validate(row)
        except Exception:
            return None
        return model.model_dump(by_alias=False, exclude_none=True)
