"""测试用例导出 Service。

从 TestCaseImportExportService 拆分，负责所有导出相关逻辑：
- 查询导出数据
- 构建 Excel/CSV/JSON 导出文件
- 列定义、单元格格式化、Sheet 创建等辅助方法
"""
import json
import io
import logging
import pandas as pd
from datetime import datetime

from fastapi.responses import FileResponse
from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.acl import (
    AudioAclRepositoryImpl,
    EvaluationConfigAclRepositoryImpl,
    PlaybackConfigAclRepositoryImpl,
    TagConfigAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
)
from shared.utils.query_utils import now_cst
from api_gateway.infrastructure.grpc_proxies import algorithm_query_service as _algo_query_svc
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.testcase import (
    TestCaseExportItem,
    TestCaseExportJsonData,
    TestCaseExportRequest,
)
from shared.utils import testcase_helpers as common

logger = logging.getLogger(__name__)

_testcase_acl = TestCaseConfigAclRepositoryImpl()
_tag_acl = TagConfigAclRepositoryImpl()
_audio_acl = AudioAclRepositoryImpl()
_playback_acl = PlaybackConfigAclRepositoryImpl()
_evaluation_acl = EvaluationConfigAclRepositoryImpl()


class TestCaseExportService:
    """测试用例导出服务（仅导出相关逻辑）"""

    # ------------------------------------------------------------------
    # 查询要导出的用例数据
    # ------------------------------------------------------------------
    @staticmethod
    def _query_cases_for_export():
        """查询要导出的用例数据"""
        req_data = TestCaseExportRequest.model_validate(request.get_json() or {})

        ids = req_data.ids
        format_type = req_data.format
        include_deleted = req_data.include_deleted

        if not ids:
            return None, None, error_response("未指定要导出的用例ID")

        test_cases = TestCaseExportService._fetch_testcases_by_ids(ids, include_deleted)
        if not test_cases:
            return None, None, error_response("未找到指定的测试用例")

        return test_cases, format_type, None

    @staticmethod
    def _fetch_testcases_by_ids(ids, include_deleted):
        """通过 gRPC 逐个获取测试用例详情"""
        test_cases = []
        for tc_id in ids:
            try:
                res = _testcase_acl.get_testcase_detail(tc_id)
                if res.get('success'):
                    tc = res.get('data')
                    if tc and (include_deleted or not tc.get('deleted')):
                        test_cases.append(tc)
            except Exception:
                continue
        return test_cases

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
            "test_type": tc.get('test_type'),
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
            "reference_params": tc.get('reference_params'),
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
                "test_type": tc.get('test_type', 'api') or 'api',
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
            "TEST_TYPE": item.get('test_type') or "",
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
    # CSV 导出
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_csv_export(export_data):
        """生成 CSV 格式导出（薄编排层）"""
        flattened_data, _, _, _, _ = TestCaseExportService._flatten_all_export_data(export_data)

        df = pd.DataFrame(flattened_data)
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')

        download_name = f"testcases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output.seek(0)
        return FileResponse(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=download_name,
        )

    # ------------------------------------------------------------------
    # Excel 导出
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_excel_export(export_data):
        """生成 Excel 格式导出（薄编排层）"""
        flattened_data, audio_configs, dimensions_data_list, groups, case_tags = \
            TestCaseExportService._flatten_all_export_data(export_data)

        cols = TestCaseExportService._get_export_columns()
        tags_rows = TestCaseExportService._build_tags_rows(export_data)
        group_rows = TestCaseExportService._build_groups_rows(groups)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            TestCaseExportService._write_all_excel_sheets(
                writer, cols, flattened_data, audio_configs,
                dimensions_data_list, tags_rows, group_rows, case_tags,
            )

        output.seek(0)
        download_name = f"testcases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return FileResponse(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=download_name,
        )

    # ------------------------------------------------------------------
    # 导出入口
    # ------------------------------------------------------------------
    @staticmethod
    def export_cases():
        """导出测试用例（薄编排层）"""
        try:
            test_cases, format_type, err = TestCaseExportService._query_cases_for_export()
            if err is not None:
                return err

            export_data = TestCaseExportService._build_export_rows(test_cases)

            if format_type == 'json':
                return TestCaseExportService._export_as_json(export_data)
            elif format_type == 'csv':
                return TestCaseExportService._generate_csv_export(export_data)
            elif format_type == 'xlsx':
                return TestCaseExportService._generate_excel_export(export_data)
            else:
                return error_response(f"不支持的导出格式: {format_type}")

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
