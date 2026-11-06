# -*- coding: utf-8 -*-
"""SPL 映射命令 Service（写侧 / CRUD + 校准 + 测试音）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
保留 Pydantic schema 校验。校准点校验逻辑已下沉到微服务。
"""
import io
import json

import pandas as pd
from fastapi.responses import Response

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import SplConfigAclRepositoryImpl
from api_gateway.schemas.common import IdData
from api_gateway.schemas.spl import (
    SPLMappingCreateRequest,
    SPLMappingUpdateRequest,
    PlayTestToneRequest,
    StopTestToneRequest,
    SplImportResult,
)


_spl_acl = SplConfigAclRepositoryImpl()

_EXCEL_EXTENSIONS = ('xlsx', 'xls')

# 导入列（snake_case，对齐 SPLMappingCreateRequest 与卡面契约）
_IMPORT_HEADERS = [
    'name', 'description', 'device_id', 'device_type', 'distance',
    'target_spl', 'digital_gain', 'test_frequency', 'calibration_points',
]

# 模板示例行（calibration_points 为 JSON 数组字符串）
_IMPORT_TEMPLATE_EXAMPLE = [
    '示例映射', '', '1', '', '1.0', '65', '', '1000',
    '[{"spl":65,"gainOffset":0}]',
]


class SPLCommandService:
    """SPL 映射写操作 Service —— 通过 gRPC 代理调用微服务"""

    # ========== 写操作 ==========

    # 创建新的 SPL 映射记录
    @staticmethod
    def create():
        try:
            req_data = SPLMappingCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        device_id = req_data.device_id
        device_type = req_data.device_type

        if device_id is None and device_type is None:
            return error_response("必须提供 device_id 或 device_type 之一", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.INVALID_PARAMS)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', 'SPL 映射记录创建成功'), http_code=201)

    # 更新 SPL 映射信息
    @staticmethod
    def update(mapping_id):
        try:
            req_data = SPLMappingUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.update(mapping_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到 SPL 映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.INVALID_PARAMS)

        return success_response(None, result.get('message', 'SPL 映射记录更新成功'))

    # 删除 SPL 映射记录
    @staticmethod
    def delete(mapping_id):
        result = _spl_acl.delete(mapping_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到 SPL 映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(None, result.get('message', 'SPL 映射记录已删除'))

    # 执行 SPL 校准流程
    @staticmethod
    def calibrate(mapping_id):
        result = _spl_acl.calibrate(mapping_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '校准失败'), code=ErrorCode.CALIBRATION_FAILED)

        return success_response(result.get('data'), result.get('message', '校准成功'))

    # 播放测试音（改为播放指定的音频文件）
    @staticmethod
    def play_test_tone(mapping_id=None):
        try:
            req_data = PlayTestToneRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.play_test_tone(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到'), code=ErrorCode.NOT_FOUND, http_code=404)
            if code == 403:
                return error_response(result.get('message', '操作失败'), code=ErrorCode.FORBIDDEN, http_code=403)
            return error_response(result.get('message', '播放失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'), result.get('message', '测试音频已播放'))

    @staticmethod
    def stop_test_tone():
        try:
            req_data = StopTestToneRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.stop_test_tone(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '设备未找到'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'), result.get('message', '测试音已停止'))

    # ========== 批量导入（INT-1383） ==========

    @staticmethod
    def import_mappings():
        """批量导入 SPL 映射（multipart 文件，CSV/XLSX/JSON）。

        纯新增（create-only）：同名行各自新建，不按 name 匹配更新。
        逐行经 ACL create → device_service SPLCommandService.create，
        成功 imported+1，失败 failed+1 并记 `第N行: <原因>`。
        """
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            file = request.files['file']
            if not file.filename:
                return error_response("未选择文件")

            rows, err = SPLCommandService._parse_import_file(file)
            if err is not None:
                return err

            imported_count, failed_count, errors = SPLCommandService._apply_import_rows(rows)
            return success_response(
                SplImportResult(
                    imported_count=imported_count,
                    failed_count=failed_count,
                    errors=errors,
                ),
                f"成功导入 {imported_count} 个，失败 {failed_count} 个",
            )
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def get_import_template():
        """返回导入模板 CSV（列头 + 示例行），Content-Disposition attachment。"""
        import csv as _csv

        buffer = io.StringIO()
        writer = _csv.writer(buffer)
        writer.writerow(_IMPORT_HEADERS)
        writer.writerow(_IMPORT_TEMPLATE_EXAMPLE)
        # 带 UTF-8 BOM，Excel 直接打开不乱码
        content = ('﻿' + buffer.getvalue()).encode('utf-8')
        return Response(
            content=content,
            media_type='text/csv',
            headers={"Content-Disposition": "attachment; filename=spl_import_template.csv"},
        )

    @staticmethod
    def _parse_import_file(file):
        """解析上传文件（JSON / CSV / Excel），返回 (rows, None) 或 (None, err)。"""
        filename = (file.filename or '').lower()
        ext = filename.rsplit('.', 1)[-1] if '.' in filename else ''

        try:
            if ext == 'json':
                data = json.loads(file.read().decode('utf-8'))
                if isinstance(data, dict):
                    rows = data.get('spl_mappings') or data.get('rows') or data.get('items')
                else:
                    rows = data
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
    def _apply_import_rows(rows):
        """逐行导入：行级校验 → 过创建 schema → ACL create；失败记行号错误。"""
        imported_count = 0
        failed_count = 0
        errors = []

        for idx, raw_row in enumerate(rows):
            try:
                row = SPLCommandService._clean_import_row(raw_row)
                if not row.get('name'):
                    raise ValueError('缺少必填字段 name')
                if row.get('device_id') is None and row.get('device_type') is None:
                    raise ValueError('必须提供 device_id 或 device_type 之一')

                payload = SPLCommandService._build_create_payload(row)
                if payload is None:
                    raise ValueError('数据校验失败')

                result = _spl_acl.create(payload)
                if not result.get('success'):
                    raise Exception(result.get('message') or '创建失败')
                imported_count += 1
            except Exception as e:
                failed_count += 1
                errors.append(f"第{idx + 1}行: {str(e)}")

        return imported_count, failed_count, errors

    @staticmethod
    def _clean_import_row(raw_row):
        """清洗单行：NaN → 剔除；calibration_points JSON 字符串 → calibration_data。"""
        row = {}
        for k, v in raw_row.items():
            v = SPLCommandService._clean_cell(v)
            if v is None:
                continue
            row[k] = v

        cp = row.pop('calibration_points', None)
        if cp is not None:
            points = cp
            if isinstance(cp, str):
                stripped = cp.strip()
                if stripped:
                    try:
                        points = json.loads(stripped)
                    except Exception:
                        raise ValueError('calibration_points 必须是 JSON 数组字符串')
            if isinstance(points, list):
                row['calibration_data'] = {'points': points}
            else:
                raise ValueError('calibration_points 必须是 JSON 数组字符串')
        return row

    @staticmethod
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

    @staticmethod
    def _build_create_payload(row):
        """按创建 schema 校验并 dump（exclude_none），非法返回 None。"""
        try:
            model = SPLMappingCreateRequest.model_validate(row)
        except Exception:
            return None
        return model.model_dump(by_alias=False, exclude_none=True)
