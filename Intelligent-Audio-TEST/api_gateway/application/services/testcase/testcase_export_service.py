"""测试用例导出 Service。

从 TestCaseImportExportService 拆分，负责所有导出相关逻辑：
- 解析导出请求（同步/异步两条入口共用）
- 查询导出数据、构建 Excel/CSV/JSON/ZIP 导出文件
- 列定义、单元格格式化、Sheet 创建等辅助方法
- ZIP 数据包（manifest + testcases.json + 可选参考参数文件/音频），与任务数据导出口径对齐

INT-2312：入口拆成「解析请求（parse_request）/ 执行导出（execute_export）」，
执行体只往注入的 `sink`（同步 BytesIO / 异步临时文件句柄）写，产物与音频都
不整包驻留内存：ZIP 音频逐条落临时文件后 `zf.write`，异步产物落盘再上传存储。
"""
import json
import io
import hashlib
import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
from datetime import datetime

from fastapi.responses import Response
from pydantic import ValidationError

from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.acl import (
    AudioAclRepositoryImpl,
    EvaluationConfigAclRepositoryImpl,
    PlaybackConfigAclRepositoryImpl,
    TagConfigAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
)
from shared.infrastructure.storage import Storage
from shared.utils.query_utils import now_cst
from api_gateway.infrastructure.grpc_proxies import algorithm_query_service as _algo_query_svc
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.application.services.testcase.testcase_export_job import (
    ExportExecutionError,
    ExportJobErrorCode,
)
from api_gateway.schemas.testcase import (
    TestCaseExportItem,
    TestCaseExportJsonData,
    TestCaseExportRequest,
)
from shared.constants.testcase_transfer import (
    AUDIOS_DIR,
    MANIFEST_FILENAME,
    PACKAGE_FORMAT,
    PACKAGE_VERSION,
    REFERENCE_PARAMS_DIR,
    TESTCASES_FILENAME,
    TestCaseExportFormat,
)
from shared.utils import testcase_helpers as common

logger = logging.getLogger(__name__)

# 导出产物媒体类型（异步下载端点按同一口径回 Content-Type）
EXPORT_MEDIA_TYPES = {
    TestCaseExportFormat.ZIP.value: 'application/zip',
    TestCaseExportFormat.XLSX.value:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    TestCaseExportFormat.CSV.value: 'text/csv',
    TestCaseExportFormat.JSON.value: 'application/json',
}

# 导出阶段（异步作业的 phase 字段）
EXPORT_PHASE_FETCHING = 'fetching'
EXPORT_PHASE_PACKAGING = 'packaging'
EXPORT_PHASE_UPLOADING = 'uploading'

# 逐条取详情的失败原因（not_found 同时覆盖「无权限」——下游把私有用例伪装成不存在）
MISSING_REASON_NOT_FOUND = 'not_found'
MISSING_REASON_RPC_ERROR = 'rpc_error'

# 音频分块读写的块大小（md5 与流式下载共用口径）
AUDIO_CHUNK_BYTES = 1024 * 1024


class _AudioSourceUnavailableError(Exception):
    """audio_service（ACL）不可用：整包导出失败，不产出半包（INT-2214）。"""


_testcase_acl = TestCaseConfigAclRepositoryImpl()
_tag_acl = TagConfigAclRepositoryImpl()
_audio_acl = AudioAclRepositoryImpl()
_playback_acl = PlaybackConfigAclRepositoryImpl()
_evaluation_acl = EvaluationConfigAclRepositoryImpl()
_storage = Storage()


@dataclass(frozen=True)
class ExportSpec:
    """一次导出的请求规格（同步/异步共用；只含解析后的纯数据）。"""

    ids: List[str] = field(default_factory=list)
    format: str = TestCaseExportFormat.JSON.value
    include_reference_params: bool = True
    include_audios: bool = False
    include_deleted: bool = False
    idempotency_key: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'ids': list(self.ids),
            'format': self.format,
            'include_reference_params': self.include_reference_params,
            'include_audios': self.include_audios,
            'include_deleted': self.include_deleted,
            'idempotency_key': self.idempotency_key,
        }


@dataclass
class ExportProgress:
    """执行进度快照：`processed` 为已尝试条数，`exported` 为成功入导出条数。"""

    phase: str
    total: int
    processed: int = 0
    exported: int = 0
    # [{id, reason}]：单条详情取不到的原因（not_found / rpc_error），不阻断导出
    missing: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ExportArtifact:
    """导出产物：`local_path` 落盘路径（有则调用方负责清理 `temp_dir`）。"""

    filename: str
    format: str
    size: int
    local_path: Optional[str] = None
    temp_dir: Optional[str] = None

    @property
    def media_type(self) -> str:
        return EXPORT_MEDIA_TYPES.get(self.format, 'application/octet-stream')


class TestCaseExportService:
    """测试用例导出服务（仅导出相关逻辑）"""

    # ------------------------------------------------------------------
    # 解析请求（同步 / 异步共用同一份校验）
    # ------------------------------------------------------------------
    @staticmethod
    def parse_request(payload,
                      max_ids: Optional[int] = None
                      ) -> Tuple[Optional[ExportSpec], Optional[tuple]]:
        """把请求体解析成 ExportSpec；校验失败返回 (None, error_response)。

        `max_ids` 只在异步作业入口传入：同步接口保持历史行为，不设条数上限。
        错误文案与状态码与同步导出保持一致（400 + error_response）。
        """
        try:
            req_data = TestCaseExportRequest.model_validate(payload or {})
        except ValidationError as e:
            # 与同步接口一致：模型校验失败沿用 error_response（历史行为）
            return None, error_response(str(e))

        ids = [str(i) for i in (req_data.ids or [])]
        format_type = (req_data.format or TestCaseExportFormat.JSON.value).strip().lower()

        if not ids:
            return None, error_response("未指定要导出的用例ID")
        if format_type not in {fmt.value for fmt in TestCaseExportFormat}:
            return None, error_response(f"不支持的导出格式: {format_type}")
        if max_ids is not None and len(ids) > max_ids:
            return None, error_response("ids 超过上限")

        return ExportSpec(
            ids=ids,
            format=format_type,
            # 与同步口径一致：只有显式传 false 才不含参考参数，只有显式 true 才带音频
            include_reference_params=req_data.include_reference_params is not False,
            include_audios=req_data.include_audios is True,
            # 契约口径（INT-2312）：回收站用例不导出，该字段接收但无效
            include_deleted=bool(req_data.include_deleted),
            idempotency_key=req_data.idempotency_key,
        ), None

    @staticmethod
    def _query_cases_for_export():
        """查询要导出的用例数据（历史入口，供导入导出门面复用）。

        返回 (test_cases, format, include_ref_params, include_audios, err)。
        """
        spec, err = TestCaseExportService.parse_request(request.get_json() or {})
        if err is not None:
            return None, None, None, None, err

        test_cases = TestCaseExportService._fetch_testcases_by_ids(
            spec.ids, spec.include_deleted)
        if not test_cases:
            return None, None, None, None, error_response("未找到指定的测试用例")

        return (test_cases, spec.format, spec.include_reference_params,
                spec.include_audios, None)

    @staticmethod
    def _iter_testcase_details(ids, include_deleted):
        """逐条取详情，产出 (tc_id, tc_or_None, missing_reason_or_None)。

        取数与失败分类的唯一实现：单条失败不再静默丢弃，按原因计入 missing
        （`not_found` 涵盖下游把无权限私有用例伪装成的不存在，不臆造 forbidden）。
        """
        for tc_id in ids:
            try:
                res = _testcase_acl.get_testcase_detail(tc_id)
            except Exception:
                logger.warning(
                    "导出取用例详情失败，按 rpc_error 计入 missing，id=%s",
                    tc_id, exc_info=True)
                yield tc_id, None, MISSING_REASON_RPC_ERROR
                continue

            success = res.get('success') if hasattr(res, 'get') else None
            tc = res.get('data') if hasattr(res, 'get') else None
            if success and tc and (include_deleted or not tc.get('deleted')):
                yield tc_id, tc, None
            else:
                yield tc_id, None, MISSING_REASON_NOT_FOUND

    @staticmethod
    def _fetch_testcases_by_ids(ids, include_deleted):
        """通过 gRPC 逐个获取测试用例详情（丢弃取不到的条目，历史行为）"""
        return [tc for _, tc, _ in
                TestCaseExportService._iter_testcase_details(ids, include_deleted)
                if tc is not None]

    @staticmethod
    def _fetch_export_data(spec, on_progress=None):
        """取详情并构建导出行，返回 (export_data, missing)。

        `missing` 为 [{id, reason}]，不阻断导出；`on_progress` 每条回调一次，
        由调用方负责节流写状态。
        """
        export_data, missing = [], []
        total = len(spec.ids)
        for processed, (tc_id, tc, reason) in enumerate(
                TestCaseExportService._iter_testcase_details(
                    spec.ids, spec.include_deleted), 1):
            if tc is None:
                missing.append({'id': tc_id, 'reason': reason})
            else:
                export_data.append(TestCaseExportService._build_case_row(tc))
            if on_progress is not None:
                on_progress(ExportProgress(
                    phase=EXPORT_PHASE_FETCHING, total=total,
                    processed=processed, exported=len(export_data),
                    missing=missing))
        return export_data, missing

    # ------------------------------------------------------------------
    # 构建导出数据行
    # ------------------------------------------------------------------
    @staticmethod
    def _build_export_rows(test_cases):
        """构建导出数据行（遍历所有用例）"""
        export_data = []
        for tc in test_cases:
            case_data = TestCaseExportService._build_case_row(tc)
            export_data.append(case_data)
        return export_data

    @staticmethod
    def _build_case_row(tc):
        """构建单个用例的导出行"""
        config = tc.get('config') or {}

        # 音频信息
        audios, playback_device_names = TestCaseExportService._collect_case_audios(tc, config)

        # 评分维度
        dimensions_data = common.collect_dimensions(config)
        dimension_names = TestCaseExportService._get_dimension_names(dimensions_data)
        dimension_ids = TestCaseExportService._get_dimension_ids(dimensions_data)

        # 音频详细信息列
        audio_details = TestCaseExportService._format_audio_details(audios)

        # 背景噪声
        noise_name, noise_spl, noise_audio_id = TestCaseExportService._collect_noise_info(config)

        # 标签
        tc_tags = tc.get('tags', []) or []
        tags = [t.get('name') if isinstance(t, dict) else t for t in tc_tags]
        tag_items = [
            {"tag_id": t.get('id'), "tag_name": t.get('name')}
            for t in tc_tags if isinstance(t, dict)
        ]

        return {
            "id": tc.get('id'),
            "name": tc.get('name'),
            "description": tc.get('description'),
            "group": tc.get('group_name'),
            "group_id": tc.get('group_id'),
            "tags": tags,
            "tag_items": tag_items,
            "dimensions": dimension_names,
            "dimension_ids": dimension_ids,
            "playback_devices": list(playback_device_names),
            "audios": audios,
            "audio_details": " ; ".join(audio_details),
            "noise_name": noise_name,
            "noise_spl": noise_spl,
            "noise_audio_id": noise_audio_id,
            "config": config,
            "algorithm_params": tc.get('algorithm_params'),
            "reference_params": tc.get('reference_params'),
            "algorithm_type": tc.get('algorithm_type'),
            "strategy_id": tc.get('strategy_id'),
            "strategy_overrides": tc.get('strategy_overrides'),
            "raw_config": json.dumps(config, ensure_ascii=False),
        }

    @staticmethod
    def _collect_case_audios(tc, config):
        """从 config 中提取音频信息，返回 (audios, playback_device_names)"""
        audios = []
        playback_device_names = set()
        for i, audio_item in enumerate(common.collect_audios(config)):
            audio_id = audio_item.get('audio_id')
            audio_name = TestCaseExportService._resolve_audio_name(audio_id, audio_item.get('audio_name'))

            device_id = common.normalize_optional_int(audio_item.get('playback_device_id'))
            device_name = TestCaseExportService._resolve_device_name(device_id)
            if device_name != "未知设备":
                playback_device_names.add(device_name)

            audios.append({
                "audio_id": audio_id,
                "audio_name": audio_name,
                "spl": audio_item.get('spl'),
                "playback_device_id": device_id,
                "playback_device_name": device_name,
                "play_order": audio_item.get('play_order', i + 1),
            })
        return audios, playback_device_names

    @staticmethod
    def _resolve_audio_name(audio_id, fallback_name):
        """通过 gRPC 获取音频名称"""
        audio_name = fallback_name or "未知音频"
        try:
            res = _audio_acl.get_one(audio_id)
            if res.get('success'):
                rec = res.get('data') or {}
                if rec.get('name'):
                    audio_name = rec.get('name')
        except Exception:
            logger.debug("导出时获取音频名称失败，audio_id=%s", audio_id, exc_info=True)
        return audio_name

    @staticmethod
    def _resolve_device_name(device_id):
        """通过 gRPC 获取播放设备名称"""
        device_name = "未知设备"
        if not device_id:
            return device_name
        try:
            res = _playback_acl.get_one(device_id)
            if res.get('success'):
                rec = res.get('data') or {}
                if rec.get('name'):
                    device_name = rec.get('name')
        except Exception:
            logger.debug("导出时获取播放设备名称失败，device_id=%s", device_id, exc_info=True)
        return device_name

    @staticmethod
    def _get_dimension_names(dim_list):
        """获取评分维度名称列表（通过 gRPC 批量查询）"""
        if not dim_list:
            return []
        d_ids = TestCaseExportService._extract_dim_ids_from_list(dim_list)
        dim_map = TestCaseExportService._fetch_dimension_map(d_ids)
        names = []
        for d_id in d_ids:
            dim = dim_map.get(str(d_id)) or {}
            if dim.get('name'):
                names.append(dim.get('name'))
        return names

    @staticmethod
    def _get_dimension_ids(dim_list):
        """获取评分维度 ID 列表"""
        ids = []
        if not dim_list:
            return ids
        for item in dim_list:
            d_id = None
            if isinstance(item, dict):
                d_id = item.get('id') or item.get('dimension_id') or item.get('dimensionId')
            else:
                d_id = item
            if d_id is None:
                continue
            try:
                ids.append(int(d_id))
            except Exception:
                continue
        return ids

    @staticmethod
    def _extract_dim_ids_from_list(dim_list):
        """从维度列表中提取 ID（兼容 dict / int 两种格式）"""
        d_ids = []
        for item in dim_list:
            d_id = item.get('id') if isinstance(item, dict) else item
            if d_id:
                d_ids.append(d_id)
        return d_ids

    @staticmethod
    def _fetch_dimension_map(d_ids):
        """通过 gRPC 批量获取维度信息，返回 {str(id): dim_obj}"""
        dim_map = {}
        if not d_ids:
            return dim_map
        try:
            res = _evaluation_acl.get_dimension_by_ids(d_ids)
            if res.get('success'):
                dim_map = res.get('data') or {}
        except Exception:
            logger.debug("导出时获取评分维度信息失败，dim_ids=%s", d_ids, exc_info=True)
        return dim_map

    @staticmethod
    def _format_audio_details(audios):
        """格式化音频详细信息列"""
        audio_details = []
        sorted_audios = sorted(audios, key=lambda x: x.get('play_order', 0))
        for i, audio_item in enumerate(sorted_audios):
            order = i + 1
            a_name = audio_item.get('audio_name', '未知音频')
            a_spl = audio_item.get('spl', '-')
            a_device = audio_item.get('playback_device_name', '-')
            audio_details.append(f"[{order}] {a_name}({a_spl}dB, 设备:{a_device})")
        return audio_details

    @staticmethod
    def _collect_noise_info(config):
        """获取背景噪声名称及 SPL（兼容新旧格式）"""
        first_round = config.get('rounds', [{}])[0] if config.get('rounds') else {}
        noise_config = first_round.get('backgroundNoise') or {} if isinstance(first_round, dict) else {}

        noise_name = "无"
        noise_spl = noise_config.get('spl') or noise_config.get('noise_spl', '')
        noise_audio_id = noise_config.get('audio_id')

        if noise_audio_id:
            try:
                res = _audio_acl.get_one(noise_audio_id)
                if res.get('success'):
                    rec = res.get('data') or {}
                    if rec.get('name'):
                        noise_name = rec.get('name')
            except Exception:
                logger.debug("导出时获取噪声音频名称失败，noise_audio_id=%s", noise_audio_id, exc_info=True)

        return noise_name, noise_spl, noise_audio_id

    # ------------------------------------------------------------------
    # 列定义 & 扁平化
    # ------------------------------------------------------------------
    @staticmethod
    def _get_export_columns():
        """返回各 Sheet 的列定义"""
        return {
            'testcases': [
                'ID', 'NAME', 'DESCRIPTION', 'GROUP_NAME', 'GROUP_ID',
                'TRANSLATION_DIRECTION', 'TEST_TYPE', 'NOISE_AUDIO_NAME', 'NOISE_AUDIO_ID',
                'NOISE_SPL', 'ASR_REFERENCE_TEXT', 'TRANSLATION_REFERENCE_TEXT',
                'TAGS', 'REMARKS',
            ],
            'audio_configs': [
                'CASE_ID', 'CASE_NAME', 'AUDIO_ID', 'AUDIO_NAME', 'SPL',
                'PLAYBACK_DEVICE_ID', 'PLAYBACK_DEVICE_NAME', 'PLAY_ORDER',
            ],
            'dimensions': [
                'CASE_ID', 'CASE_NAME', 'DIMENSION_ID', 'DIMENSION_NAME',
                'DIMENSION_DISPLAY_NAME', 'WEIGHT', 'THRESHOLD',
            ],
            'tags': ['TAG_ID', 'TAG_NAME', 'TAG_DESCRIPTION', 'TAG_COLOR'],
            'groups': ['GROUP_ID', 'GROUP_NAME', 'GROUP_DESCRIPTION', 'PARENT_GROUP_NAME'],
            'case_tags': ['CASE_ID', 'CASE_NAME', 'TAG_ID', 'TAG_NAME'],
        }

    @staticmethod
    def _flatten_export_item(item):
        """将单个导出项扁平化为表格行"""
        config_data = item.get('config', {})
        ref_col = item.get('reference_params')
        if ref_col:
            asr_ref_text = _algo_query_svc.get_reference_text(ref_col, 'asr_reference_text')
            tran_ref_text = _algo_query_svc.get_reference_text(ref_col, 'translation_reference_text')
        else:
            asr_ref_text = _algo_query_svc.get_reference_text(config_data, 'asr_reference_text')
            tran_ref_text = _algo_query_svc.get_reference_text(config_data, 'translation_reference_text')

        return {
            "ID": item['id'],
            "NAME": item['name'],
            "DESCRIPTION": item['description'],
            "GROUP_NAME": item['group'],
            "GROUP_ID": item.get('group_id') or "",
            "NOISE_AUDIO_NAME": item['noise_name'],
            "NOISE_AUDIO_ID": item.get('noise_audio_id') or "",
            "NOISE_SPL": item['noise_spl'],
            "ASR_REFERENCE_TEXT": asr_ref_text,
            "TRANSLATION_REFERENCE_TEXT": tran_ref_text,
            "TAGS": ", ".join(item['tags']) if item['tags'] else "",
            "REMARKS": "",
        }

    @staticmethod
    def _build_audio_config_row(item, audio):
        """构建单个音频配置行"""
        return {
            "CASE_ID": item['id'],
            "CASE_NAME": item['name'],
            "AUDIO_ID": audio.get('audio_id') or "",
            "AUDIO_NAME": audio.get('audio_name', ''),
            "SPL": audio.get('spl', ''),
            "PLAYBACK_DEVICE_ID": audio.get('playback_device_id') or "",
            "PLAYBACK_DEVICE_NAME": audio.get('playback_device_name', ''),
            "PLAY_ORDER": audio.get('play_order', 0),
        }

    @staticmethod
    def _build_dimension_row(item, dim_id, dim_obj):
        """构建单个维度行"""
        dim_name = dim_obj.get('name') if dim_obj else str(dim_id)
        return {
            "CASE_ID": item['id'],
            "CASE_NAME": item['name'],
            "DIMENSION_ID": dim_id,
            "DIMENSION_NAME": dim_name,
            "DIMENSION_DISPLAY_NAME": dim_name,
            "WEIGHT": dim_obj.get('weight') if dim_obj else 50,
            "THRESHOLD": 80,
        }

    @staticmethod
    def _build_case_tag_row(item, tag_item):
        """构建单个用例-标签关联行"""
        return {
            "CASE_ID": item['id'],
            "CASE_NAME": item['name'],
            "TAG_ID": tag_item.get("tag_id") or "",
            "TAG_NAME": tag_item.get("tag_name") or "",
        }

    @staticmethod
    def _flatten_all_export_data(export_data):
        """将所有导出数据扁平化为各 Sheet 的行列表"""
        flattened_data = []
        audio_configs = []
        dimensions_data_list = []
        groups = []
        case_tags = []

        for item in export_data:
            flattened_data.append(TestCaseExportService._flatten_export_item(item))

            for audio in item.get('audios', []):
                audio_configs.append(TestCaseExportService._build_audio_config_row(item, audio))

            all_dim_ids = item.get('dimension_ids', []) or []
            dim_map = TestCaseExportService._fetch_dimension_map(all_dim_ids)
            for dim_id in all_dim_ids:
                dim_obj = dim_map.get(str(dim_id)) or {}
                dimensions_data_list.append(TestCaseExportService._build_dimension_row(item, dim_id, dim_obj))

            if item.get('group_id') or item.get('group'):
                groups.append({"group_id": item.get('group_id'), "group_name": item.get('group')})

            for tag_item in item.get('tag_items', []) or []:
                case_tags.append(TestCaseExportService._build_case_tag_row(item, tag_item))

        return flattened_data, audio_configs, dimensions_data_list, groups, case_tags

    # ------------------------------------------------------------------
    # Excel Sheet 创建
    # ------------------------------------------------------------------
    @staticmethod
    def _format_cell_value(val):
        """格式化单元格值（NaN → None）"""
        if val is None or (hasattr(pd, "isna") and pd.isna(val)):
            return None
        return val

    @staticmethod
    def _create_excel_sheet(writer, data_rows, columns, sheet_name):
        """创建一个 Excel Sheet（自动处理空数据和列对齐）"""
        df = pd.DataFrame(data_rows)
        if df.empty:
            df = pd.DataFrame(columns=columns)
        else:
            df = df.reindex(columns=columns)
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    @staticmethod
    def _build_tags_rows(export_data):
        """构建 Tags Sheet 的行数据"""
        tag_names = set()
        for item in export_data:
            for t in item.get('tags', []):
                if t:
                    tag_names.add(t)

        tags_rows = []
        if not tag_names:
            return tags_rows

        tag_by_name = TestCaseExportService._fetch_tag_map_by_names()
        for name in sorted(tag_names):
            tag_obj = tag_by_name.get(name) or {}
            tags_rows.append({
                "TAG_ID": tag_obj.get('id') if tag_obj else "",
                "TAG_NAME": name,
                "TAG_DESCRIPTION": tag_obj.get('description') if tag_obj else "",
                "TAG_COLOR": tag_obj.get('color') if tag_obj else "",
            })
        return tags_rows

    @staticmethod
    def _fetch_tag_map_by_names():
        """通过 gRPC 获取标签列表，返回 {name: tag_obj}"""
        tag_by_name = {}
        try:
            res = _tag_acl.list_tags(page=1, per_page=500, keyword='')
            if res.get('success'):
                for t in (res.get('data') or {}).get('items', []):
                    if t.get('name'):
                        tag_by_name[t.get('name')] = t
        except Exception:
            logger.debug("导出 Excel 时获取标签列表失败", exc_info=True)
        return tag_by_name

    @staticmethod
    def _build_groups_rows(groups):
        """构建 Groups Sheet 的行数据"""
        unique_groups = {}
        for g in groups:
            g_id = g.get("group_id")
            g_name = g.get("group_name")
            if g_id:
                unique_groups[g_id] = g_name
            elif g_name and g_name not in unique_groups.values():
                unique_groups[g_name] = g_name

        group_rows = []
        if not unique_groups:
            return group_rows

        group_by_id = TestCaseExportService._fetch_groups_map(unique_groups)
        for group_key, group_name in sorted(unique_groups.items(), key=lambda x: str(x[0])):
            group_obj = group_by_id.get(group_key)
            if not group_obj and group_name:
                group_obj = next((g for g in group_by_id.values() if g.get('name') == group_name), None)
            resolved_id = group_obj['id'] if group_obj else (group_key if group_key and group_key != group_name else "")
            group_rows.append({
                "GROUP_ID": resolved_id,
                "GROUP_NAME": group_obj['name'] if group_obj else group_name,
                "GROUP_DESCRIPTION": group_obj.get('description', '') if group_obj else "",
                "PARENT_GROUP_NAME": "",
            })
        return group_rows

    @staticmethod
    def _fetch_groups_map(unique_groups):
        """通过 gRPC 按 id/name 批量查询 TestCaseGroup"""
        group_by_id = {}
        try:
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            id_keys = [k for k in unique_groups.keys() if k]
            if id_keys:
                resp = task_data_service.get_testcase_groups_by_ids(id_keys)
                for g in resp.get('items', []):
                    group_by_id[g['id']] = g
            missing_names = [v for k, v in unique_groups.items() if k not in group_by_id]
            if missing_names:
                resp = task_data_service.get_testcase_groups_by_names(missing_names)
                for g in resp.get('items', []):
                    group_by_id[g['id']] = g
        except Exception:
            group_by_id = {}
        return group_by_id

    @staticmethod
    def _write_all_excel_sheets(writer, cols, flattened, audio, dims, tags, groups, case_tags):
        """写入所有 Excel Sheet"""
        TestCaseExportService._create_excel_sheet(writer, flattened, cols['testcases'], 'TestCases')
        TestCaseExportService._create_excel_sheet(writer, audio, cols['audio_configs'], 'AudioConfigs')
        TestCaseExportService._create_excel_sheet(writer, dims, cols['dimensions'], 'Dimensions')
        TestCaseExportService._create_excel_sheet(writer, tags, cols['tags'], 'Tags')
        TestCaseExportService._create_excel_sheet(writer, groups, cols['groups'], 'Groups')
        TestCaseExportService._create_excel_sheet(writer, case_tags, cols['case_tags'], 'CaseTags')

    # ------------------------------------------------------------------
    # 打包核心（同步 / 异步共用）：只往注入的 sink 写，不假设内存缓冲
    # ------------------------------------------------------------------
    @staticmethod
    def _build_export_filename(format_type):
        """导出文件名，口径与同步接口一致：testcases_export_<yyyyMMdd_HHmmss>.<ext>"""
        return (f"testcases_export_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}")

    @staticmethod
    def _pack(spec, export_data, missing_case_ids, sink):
        """按 spec.format 把导出行写入 sink（文件对象 / BytesIO 均可）。"""
        if spec.format == TestCaseExportFormat.ZIP.value:
            TestCaseExportService._pack_zip(
                spec, export_data, missing_case_ids, sink)
        elif spec.format == TestCaseExportFormat.CSV.value:
            TestCaseExportService._pack_csv(export_data, sink)
        elif spec.format == TestCaseExportFormat.XLSX.value:
            TestCaseExportService._pack_excel(export_data, sink)
        elif spec.format == TestCaseExportFormat.JSON.value:
            TestCaseExportService._pack_json(export_data, sink)
        else:
            raise ExportExecutionError(
                ExportJobErrorCode.INTERNAL_ERROR,
                f"不支持的导出格式: {spec.format}")

    @staticmethod
    def _pack_csv(export_data, sink):
        """生成 CSV（薄编排层）"""
        flattened_data, _, _, _, _ = \
            TestCaseExportService._flatten_all_export_data(export_data)
        df = pd.DataFrame(flattened_data)
        df.to_csv(sink, index=False, encoding='utf-8-sig')

    @staticmethod
    def _pack_excel(export_data, sink):
        """生成 Excel（薄编排层）"""
        flattened_data, audio_configs, dimensions_data_list, groups, case_tags = \
            TestCaseExportService._flatten_all_export_data(export_data)

        cols = TestCaseExportService._get_export_columns()
        tags_rows = TestCaseExportService._build_tags_rows(export_data)
        group_rows = TestCaseExportService._build_groups_rows(groups)

        with pd.ExcelWriter(sink, engine='openpyxl') as writer:
            TestCaseExportService._write_all_excel_sheets(
                writer, cols, flattened_data, audio_configs,
                dimensions_data_list, tags_rows, group_rows, case_tags,
            )

    @staticmethod
    def _pack_json(export_data, sink):
        """生成可下载的 .json 文档（不带 success_response 信封，INT-2312）。

        用 json.dump 直接写到 sink（同步 BytesIO / 异步二进制文件句柄），
        不先 dumps 成整串；sink 是二进制流，故套一层文本包装器流式写 UTF-8。
        """
        document = {
            "test_cases": export_data,
            "exported_at": now_cst().isoformat(),
            "total_count": len(export_data),
        }
        text_sink = io.TextIOWrapper(sink, encoding='utf-8', write_through=True)
        try:
            json.dump(document, text_sink, ensure_ascii=False, default=str)
            text_sink.flush()
        finally:
            # 只解绑，不关闭调用方提供的底层 sink
            text_sink.detach()

    @staticmethod
    def _pack_zip(spec, export_data, missing_case_ids, sink):
        """生成 ZIP 数据包：manifest + testcases.json + 可选参考参数文件 / 音频附件。

        include_audios=True 时按用例引用全口径（播放音频 + 干扰人 + 各级背景噪音）
        收集音频，把可读到的二进制打进 `audios/{audio_id}.{ext}`，manifest 带
        清单（id/name/file/md5/size/format）与缺失计数（INT-2214）。

        INT-2312 内存纪律：音频逐条 `storage.load_file` 落临时文件 → `zf.write`
        → 立即删除，任意时刻只有一个音频文件在盘上、不把二进制累积进列表；
        整包也只写进 sink（同步 BytesIO / 异步临时文件句柄）。

        失败分类：
        - audio_service ACL 查询失败（依赖不可用）→ 抛 `_AudioSourceUnavailableError`，
          调用方按整包失败处理，不产出半包；
        - id 查到但二进制读不到 / 库里不存在 → 计入 missing，不阻断导出。
        """
        exported_at = now_cst().isoformat()
        audios, missing_audio_ids = [], []
        if spec.include_audios:
            audios, missing_audio_ids = \
                TestCaseExportService._collect_audio_package_entries(export_data)

        audio_tmp_dir = None
        packed_audios = []
        try:
            if audios:
                audio_tmp_dir = tempfile.mkdtemp(prefix='testcase_export_audio_')
            with zipfile.ZipFile(sink, 'w', zipfile.ZIP_DEFLATED) as zf:
                ref_file_count = 0
                if spec.include_reference_params:
                    ref_files = TestCaseExportService._collect_reference_param_files(export_data)
                    for zip_path, content in ref_files:
                        zf.writestr(zip_path, content)
                    ref_file_count = len(ref_files)

                for entry in audios:
                    packed = TestCaseExportService._write_audio_entry(
                        zf, entry, audio_tmp_dir)
                    if packed is None:
                        missing_audio_ids.append(entry['id'])
                    else:
                        packed_audios.append(packed)

                manifest = {
                    "format": PACKAGE_FORMAT,
                    "version": PACKAGE_VERSION,
                    "exported_at": exported_at,
                    "total_count": len(export_data),
                    "options": {
                        "include_reference_params": bool(spec.include_reference_params),
                        "include_audios": bool(spec.include_audios),
                    },
                    "reference_param_file_count": ref_file_count,
                    "audio_file_count": len(packed_audios),
                    "missing_audio_count": len(missing_audio_ids),
                    "missing_audio_ids": list(missing_audio_ids),
                    # 逐条详情取不到、未进包的用例（INT-2312 部分失败回报）
                    "missing_case_ids": list(missing_case_ids or []),
                    "audios": packed_audios,
                }
                zf.writestr(
                    MANIFEST_FILENAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )

                package_doc = {
                    "version": PACKAGE_VERSION,
                    "exported_at": exported_at,
                    "total_count": len(export_data),
                    "test_cases": export_data,
                }
                zf.writestr(
                    TESTCASES_FILENAME,
                    json.dumps(package_doc, ensure_ascii=False, indent=2, default=str),
                )
        finally:
            if audio_tmp_dir:
                shutil.rmtree(audio_tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 同步导出响应适配（历史入口：返回 Response / error tuple，响应不变）
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_csv_export(export_data):
        """生成 CSV 格式导出（薄编排层）"""
        sink = io.BytesIO()
        TestCaseExportService._pack_csv(export_data, sink)
        filename = TestCaseExportService._build_export_filename(
            TestCaseExportFormat.CSV.value)
        # 内存字节流下载用 Response（FileResponse 仅接受磁盘路径）
        return Response(
            content=sink.getvalue(),
            media_type=EXPORT_MEDIA_TYPES[TestCaseExportFormat.CSV.value],
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @staticmethod
    def _generate_excel_export(export_data):
        """生成 Excel 格式导出（薄编排层）"""
        sink = io.BytesIO()
        TestCaseExportService._pack_excel(export_data, sink)
        filename = TestCaseExportService._build_export_filename(
            TestCaseExportFormat.XLSX.value)
        return Response(
            content=sink.getvalue(),
            media_type=EXPORT_MEDIA_TYPES[TestCaseExportFormat.XLSX.value],
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @staticmethod
    def _generate_zip_export(export_data, include_reference_params=True,
                             include_audios=False):
        """生成 ZIP 数据包（同步适配；异步作业走 execute_export）。"""
        spec = ExportSpec(
            format=TestCaseExportFormat.ZIP.value,
            include_reference_params=bool(include_reference_params),
            include_audios=bool(include_audios),
        )
        sink = io.BytesIO()
        try:
            TestCaseExportService._pack_zip(spec, export_data, [], sink)
        except _AudioSourceUnavailableError as e:
            logger.error("ZIP 导出中止：音频服务不可用，%s", e)
            return error_response(
                f"音频服务不可用，导出中止（未生成数据包）: {e}",
                code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                http_code=503,
            )

        filename = TestCaseExportService._build_export_filename(
            TestCaseExportFormat.ZIP.value)
        return Response(
            content=sink.getvalue(),
            media_type=EXPORT_MEDIA_TYPES[TestCaseExportFormat.ZIP.value],
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @staticmethod
    def _collect_audio_package_entries(export_data):
        """收集用例引用音频的元数据，返回 (entries, missing_ids)。

        音频元数据一次批量查 audio_service（`GetAudiosByIds`），失败抛
        `_AudioSourceUnavailableError`（调用方整包失败）；库里查不到只计入
        missing，不阻断导出。

        INT-2312：这里只收元数据（不含二进制），二进制在 `_write_audio_entry`
        里逐条落临时文件后写入包内，避免把所有音频整包读进内存。
        """
        audio_ids = []
        for item in export_data or []:
            for audio_id in common.collect_case_audio_ids(item.get('config') or {}):
                if audio_id not in audio_ids:
                    audio_ids.append(audio_id)
        if not audio_ids:
            return [], []

        try:
            res = _audio_acl.get_by_ids({'ids': audio_ids})
        except Exception as e:
            raise _AudioSourceUnavailableError(str(e))
        # ACL 仓储返回 CommandResultDTO（兼容 dict-like .get）
        success = res.get('success') if hasattr(res, 'get') else None
        if not success:
            message = res.get('message') if hasattr(res, 'get') else None
            raise _AudioSourceUnavailableError(message or '按ID查询音频失败')
        records = res.get('data')
        if not isinstance(records, list):
            raise _AudioSourceUnavailableError('按ID查询音频返回的数据不是列表')

        record_map = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            record_id = common.normalize_optional_int(record.get('id'))
            if record_id is not None:
                record_map[record_id] = record

        entries, missing = [], []
        for audio_id in audio_ids:
            entry = TestCaseExportService._build_audio_package_entry(
                audio_id, record_map.get(audio_id))
            if entry is None:
                missing.append(audio_id)
            else:
                entries.append(entry)
        return entries, missing

    @staticmethod
    def _manifest_audio_entry(entry):
        """组装 manifest.audios[] 单条：固定字段 + 可空的 `source_md5`。

        `md5` 是包内文件的字节 md5（登记用）；`source_md5` 是源库 `audios.md5`
        （原始上传字节 md5，导入端复用查找用，INT-2314）。源记录无 md5 时
        省略该键，老导入端不受影响。
        """
        item = {key: entry[key] for key in
                ('id', 'name', 'file', 'md5', 'size', 'format')}
        item['audio_type'] = str(entry.get('audio_type') or '').strip() or 'dry'
        if entry.get('source_md5'):
            item['source_md5'] = entry['source_md5']
        return item

    @staticmethod
    def _normalize_source_md5(record):
        """源库 `audios.md5` 规整为 32 位小写 hex；空 / 非 hex 返回 None。"""
        if not isinstance(record, dict):
            return None
        value = str(record.get('md5') or '').strip().lower()
        if re.fullmatch(r'[0-9a-f]{32}', value):
            return value
        return None

    def _build_audio_package_entry(audio_id, record):
        """组装单条音频的包内元数据（不含二进制）；查不到 / 无路径返回 None。"""
        if not isinstance(record, dict):
            return None
        file_path = record.get('file_path')
        if not file_path:
            return None

        ext = TestCaseExportService._resolve_audio_extension(record)
        name = (record.get('name') or record.get('original_filename')
                or os.path.basename(str(file_path).split('?', 1)[0]) or None)
        entry = {
            'id': audio_id,
            'name': name,
            'file': f"{AUDIOS_DIR}/{audio_id}.{ext}",
            'format': record.get('format') or ext,
            # 类型原样透传（noise / prompt / mixed），保证导入回导后不丢；源记录缺失回落 dry
            'audio_type': str(record.get('audio_type') or '').strip() or 'dry',
            'file_path': file_path,
        }
        # source_md5：源库 audios.md5（原始上传字节），与包内字节 md5 口径不同，
        # 导入端先用它做复用查找（INT-2314）；源记录无 md5 时不写该键。
        source_md5 = TestCaseExportService._normalize_source_md5(record)
        if source_md5:
            entry['source_md5'] = source_md5
        return entry

    @staticmethod
    def _write_audio_entry(zf, entry, tmp_dir):
        """把单条音频流式写入包内，返回 manifest 条目；读不到返回 None。

        `storage.load_file` 先落临时文件 → 分块算 md5 → `zf.write` 落包 →
        立即删临时文件。md5 按包内实际字节计算，保证 manifest 清单与包内文件
        一致（导入回导按 md5 去重）。
        """
        tmp_path = os.path.join(tmp_dir, f"audio_{entry['id']}.{entry['format']}")
        try:
            _storage.load_file(entry['file_path'], tmp_path)
        except Exception:
            logger.warning(
                "导出音频文件失败，按 missing 处理，audio_id=%s path=%s",
                entry['id'], entry['file_path'], exc_info=True)
            return None

        try:
            md5_digest = TestCaseExportService._file_md5(tmp_path)
            size = os.path.getsize(tmp_path)
            zf.write(tmp_path, entry['file'])
        except Exception:
            logger.warning(
                "导出音频写入数据包失败，按 missing 处理，audio_id=%s",
                entry['id'], exc_info=True)
            return None
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        return TestCaseExportService._manifest_audio_entry({
            'id': entry['id'],
            'name': entry['name'],
            'file': entry['file'],
            'md5': md5_digest,
            'size': size,
            'format': entry['format'],
            'audio_type': entry.get('audio_type'),
            'source_md5': entry.get('source_md5'),
        })

    @staticmethod
    def _file_md5(path):
        """按 1MB 分块计算文件 md5（不整文件读入内存）。"""
        digest = hashlib.md5()
        with open(path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(AUDIO_CHUNK_BYTES), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _resolve_audio_extension(record):
        """音频扩展名：`format` 优先，回落 `file_path` 后缀，兜底 bin。"""
        pattern = re.compile(r'^[a-z0-9]{1,10}$')
        fmt = str(record.get('format') or '').strip().lstrip('.').lower()
        if pattern.match(fmt):
            return fmt
        file_path = str(record.get('file_path') or '').split('?', 1)[0]
        ext = os.path.splitext(file_path)[1].lstrip('.').lower()
        if pattern.match(ext):
            return ext
        return 'bin'

    @staticmethod
    def _collect_reference_param_files(export_data):
        """读取参考参数文件内容并回填包内相对路径，返回 [(zip_path, bytes)]。

        路径以 `reference_params` 独立列为准，缺失时回落到
        `config.rounds[].referenceParamsPath`（兼容老用例）；读取失败仅告警跳过，
        不阻断整个导出。回填的 `reference_param_files` 供导入端按相对路径取内容。
        """
        ref_files = []
        for item in export_data:
            round_paths = TestCaseExportService._collect_round_ref_paths(item)
            packaged = []
            for round_number, ref_path in sorted(round_paths.items()):
                content = TestCaseExportService._load_reference_param_bytes(ref_path)
                if content is None:
                    continue
                zip_path = f"{REFERENCE_PARAMS_DIR}/{item['id']}/round_{int(round_number)}.json"
                ref_files.append((zip_path, content))
                packaged.append({
                    "round_number": int(round_number),
                    "path": zip_path,
                })
            if packaged:
                item['reference_param_files'] = packaged
        return ref_files

    @staticmethod
    def _collect_round_ref_paths(item):
        """汇总用例各轮参考参数路径：独立列优先，config.rounds 兜底"""
        round_paths = {}
        refs = item.get('reference_params')
        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                round_number = ref.get('round_number') or ref.get('roundNumber')
                ref_path = ref.get('reference_params_path') or ref.get('referenceParamsPath')
                if round_number is not None and ref_path:
                    round_paths[int(round_number)] = ref_path

        config = item.get('config') or {}
        for idx, round_item in enumerate(config.get('rounds') or [], 1):
            if not isinstance(round_item, dict):
                continue
            round_number = round_item.get('round_number') or idx
            ref_path = round_item.get('referenceParamsPath') or round_item.get('reference_params_path')
            if ref_path:
                round_paths.setdefault(int(round_number), ref_path)
        return round_paths

    @staticmethod
    def _load_reference_param_bytes(ref_path):
        """按存储路径读取参考参数文件字节流（失败返回 None）"""
        try:
            from shared.infrastructure.storage import storage_load_bytes
            return storage_load_bytes(ref_path)
        except Exception:
            logger.warning("导出参考参数文件失败，path=%s", ref_path, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 导出执行体（同步 / 异步共用）
    # ------------------------------------------------------------------
    @staticmethod
    def execute_export(spec, on_progress: Optional[Callable[[ExportProgress], None]] = None,
                       sink=None) -> ExportArtifact:
        """执行一次导出：取详情 → 构建行 → 打包进 sink，返回产物描述。

        - `sink` 为 None 时自建临时目录与文件，产物路径在 `artifact.local_path`，
          调用方用完后清理 `artifact.temp_dir`（异步作业走这条）；
        - `sink` 由调用方提供（同步 BytesIO / 异步文件句柄），本方法只 flush 不关闭；
        - 条数/取数失败由 `on_progress` 回调上报，`missing` 不阻断导出；
        - 业务失败抛 `ExportExecutionError`（code 见 ExportJobErrorCode）。
        """
        export_data, missing = TestCaseExportService._fetch_export_data(
            spec, on_progress)
        if not export_data:
            raise ExportExecutionError(
                ExportJobErrorCode.NO_DATA, '未找到指定的测试用例')

        filename = TestCaseExportService._build_export_filename(spec.format)
        owns_sink = sink is None
        temp_dir = None
        local_path = None
        if owns_sink:
            temp_dir = tempfile.mkdtemp(prefix='testcase_export_')
            local_path = os.path.join(temp_dir, filename)
            sink = open(local_path, 'wb')

        try:
            if on_progress is not None:
                on_progress(ExportProgress(
                    phase=EXPORT_PHASE_PACKAGING, total=len(spec.ids),
                    processed=len(spec.ids), exported=len(export_data),
                    missing=missing))
            try:
                TestCaseExportService._pack(
                    spec, export_data, [m['id'] for m in missing], sink)
            except _AudioSourceUnavailableError as e:
                logger.error("导出中止：音频服务不可用，%s", e)
                raise ExportExecutionError(
                    ExportJobErrorCode.AUDIO_UNAVAILABLE,
                    f"音频服务不可用，导出中止（未生成数据包）: {e}") from e
            sink.flush()
            size = os.path.getsize(local_path) if owns_sink else sink.tell()
        except BaseException:
            if owns_sink:
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        finally:
            if owns_sink:
                sink.close()

        return ExportArtifact(
            filename=filename, format=spec.format, size=size,
            local_path=local_path, temp_dir=temp_dir)

    # ------------------------------------------------------------------
    # 导出入口（同步）
    # ------------------------------------------------------------------
    @staticmethod
    def _sync_error_response(error: ExportExecutionError):
        """执行体异常 → 同步接口响应：音频依赖不可用仍是 503，其余 400。"""
        if error.code == ExportJobErrorCode.AUDIO_UNAVAILABLE:
            return error_response(
                error.message, code=ErrorCode.EXTERNAL_SERVICE_ERROR, http_code=503)
        return error_response(error.message)

    @staticmethod
    def export_cases():
        """导出测试用例（同步，薄编排层）。

        行为与响应保持历史口径：ZIP/CSV/XLSX 直接回文件流，JSON 回成功信封。
        """
        try:
            spec, err = TestCaseExportService.parse_request(request.get_json() or {})
            if err is not None:
                return err

            if spec.format == TestCaseExportFormat.JSON.value:
                # 同步 JSON 是 API 信封（历史契约），异步作业才产出 .json 文件
                test_cases = TestCaseExportService._fetch_testcases_by_ids(
                    spec.ids, spec.include_deleted)
                if not test_cases:
                    return error_response("未找到指定的测试用例")
                return TestCaseExportService._export_as_json(
                    TestCaseExportService._build_export_rows(test_cases))

            sink = io.BytesIO()
            artifact = TestCaseExportService.execute_export(spec, sink=sink)
            return Response(
                content=sink.getvalue(),
                media_type=artifact.media_type,
                headers={"Content-Disposition":
                         f"attachment; filename={artifact.filename}"},
            )

        except ExportExecutionError as e:
            return TestCaseExportService._sync_error_response(e)
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def _export_as_json(export_data):
        """以 JSON 格式导出"""
        export_result = {
            "test_cases": export_data,
            "exported_at": now_cst().isoformat(),
            "total_count": len(export_data),
        }
        return success_response(
            TestCaseExportJsonData(
                test_cases=[TestCaseExportItem(**item) for item in export_result["test_cases"]],
                exported_at=export_result["exported_at"],
                total_count=export_result["total_count"],
            )
        )
