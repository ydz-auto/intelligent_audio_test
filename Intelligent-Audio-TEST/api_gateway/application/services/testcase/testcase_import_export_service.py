"""测试用例导入导出 Service。

从 TestCaseController 抽取的导入、导出、模板下载、预览导入方法。
TestCaseGroup 读写已通过 gRPC 客户端完成，不再直连 task_service DB。
"""
import uuid
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
    TaskConfigAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
)
from shared.utils.query_utils import now_cst
from api_gateway.infrastructure.grpc_proxies import algorithm_query_service as _algo_query_svc

from api_gateway.schemas.testcase import (
    TestCaseExportItem,
    TestCaseExportJsonData,
    TestCaseExportRequest,
    TestCaseImportResult,
)
from shared.utils import testcase_helpers as common

logger = logging.getLogger(__name__)

_testcase_acl = TestCaseConfigAclRepositoryImpl()
_task_acl = TaskConfigAclRepositoryImpl()
_tag_acl = TagConfigAclRepositoryImpl()
_audio_acl = AudioAclRepositoryImpl()
_playback_acl = PlaybackConfigAclRepositoryImpl()
_evaluation_acl = EvaluationConfigAclRepositoryImpl()


class TestCaseImportExportService:
    # 查询要导出的用例数据
    @staticmethod
    def _query_cases_for_export():
        req_data = TestCaseExportRequest.model_validate(request.get_json() or {})

        ids = req_data.ids
        format_type = req_data.format
        include_deleted = req_data.include_deleted

        if not ids:
            return None, None, error_response("未指定要导出的用例ID")

        # 通过 gRPC 批量获取测试用例（替代直连 task_service PO）
        # 使用 list_testcases 的 keyword 参数无法按 ID 过滤，这里逐个取详情
        test_cases = []
        for tc_id in ids:
            try:
                res = _testcase_acl.get_testcase_detail(tc_id)
                if res.get('success'):
                    tc = res.get('data')
                    if tc:
                        if include_deleted or not tc.get('deleted'):
                            test_cases.append(tc)
            except Exception:
                continue

        if not test_cases:
            return None, None, error_response("未找到指定的测试用例")

        return test_cases, format_type, None

    # 构建导出数据行
    @staticmethod
    def _build_export_rows(test_cases):
        export_data = []
        for tc in test_cases:
            # 通过 gRPC 获取的 TestCase 已为 dict，无需 refresh_reference_texts
            config = tc.get('config') or {}

            # 从config中提取音频信息
            audios = []
            playback_device_names = set()
            for i, audio_item in enumerate(common.collect_audios(config)):
                audio_id = audio_item.get('audio_id')
                audio_name = audio_item.get('audio_name') or "未知音频"
                # 通过 gRPC 获取音频名称（替代直连 audio_service PO）
                try:
                    res = _audio_acl.get_one(audio_id)
                    if res.get('success'):
                        rec = res.get('data') or {}
                        if rec.get('name'):
                            audio_name = rec.get('name')
                except Exception:
                    logger.debug("导出时获取音频名称失败，audio_id=%s", audio_id, exc_info=True)

                device_id = common.normalize_optional_int(audio_item.get('playback_device_id'))
                device_name = "未知设备"
                if device_id:
                    # 通过 gRPC 获取播放设备名称（替代直连 device_service PO）
                    try:
                        res = _playback_acl.get_one(device_id)
                        if res.get('success'):
                            rec = res.get('data') or {}
                            if rec.get('name'):
                                device_name = rec.get('name')
                                playback_device_names.add(device_name)
                    except Exception:
                        logger.debug("导出时获取播放设备名称失败，device_id=%s", device_id, exc_info=True)

                audios.append({
                    "audio_id": audio_id,
                    "audio_name": audio_name,
                    "test_type": tc.get('test_type', 'api') or 'api',
                    "spl": audio_item.get('spl'),
                    "playback_device_id": device_id,
                    "playback_device_name": device_name,
                    "play_order": audio_item.get('play_order', i + 1)
                })

            # 获取评分维度名称（兼容新旧格式）
            dimensions_data = common.collect_dimensions(config)

            def get_dim_names(dim_list):
                names = []
                if not dim_list: return names
                # 收集维度 ID，通过 gRPC 批量获取
                d_ids = []
                for item in dim_list:
                    d_id = None
                    if isinstance(item, dict):
                        d_id = item.get('id')
                    else:
                        d_id = item
                    if d_id:
                        d_ids.append(d_id)
                dim_map = {}
                if d_ids:
                    try:
                        res = _evaluation_acl.get_dimension_by_ids(d_ids)
                        if res.get('success'):
                            dim_map = res.get('data') or {}
                    except Exception:
                        logger.debug("导出时获取评分维度名称失败，dim_ids=%s", d_ids, exc_info=True)
                for d_id in d_ids:
                    dim = dim_map.get(str(d_id)) or {}
                    if dim.get('name'):
                        names.append(dim.get('name'))
                return names

            def get_dim_ids(dim_list):
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

            dimension_names = get_dim_names(dimensions_data)
            dimension_ids = get_dim_ids(dimensions_data)

            # 格式化音频详细信息列
            audio_details = []
            # 按播放顺序排序
            sorted_audios = sorted(audios, key=lambda x: x.get('play_order', 0))
            for i, audio_item in enumerate(sorted_audios):
                order = i + 1 # 导出时序号从1开始
                a_name = audio_item.get('audio_name', '未知音频')
                a_spl = audio_item.get('spl', '-')
                a_device = audio_item.get('playback_device_name', '-')
                audio_details.append(f"[{order}] {a_name}({a_spl}dB, 设备:{a_device})")

            # 获取背景噪声名称及SPL（兼容新旧格式）
            # 获取噪声配置（从 rounds[0].backgroundNoise）
            noise_config = {}
            first_round = config.get('rounds', [{}])[0] if config.get('rounds') else {}
            if isinstance(first_round, dict):
                noise_config = first_round.get('backgroundNoise') or {}
            noise_name = "无"
            noise_spl = noise_config.get('spl') or noise_config.get('noise_spl', '')
            noise_audio_id = noise_config.get('audio_id')

            if noise_audio_id:
                # 通过 gRPC 获取噪声音频名称（替代直连 audio_service PO）
                try:
                    res = _audio_acl.get_one(noise_audio_id)
                    if res.get('success'):
                        rec = res.get('data') or {}
                        if rec.get('name'):
                            noise_name = rec.get('name')
                except Exception:
                    logger.debug("导出时获取噪声音频名称失败，noise_audio_id=%s", noise_audio_id, exc_info=True)

            # 获取标签（tc 为 gRPC 返回的 dict）
            tc_tags = tc.get('tags', []) or []
            tags = [t.get('name') if isinstance(t, dict) else t for t in tc_tags]
            tag_items = [
                {"tag_id": t.get('id'), "tag_name": t.get('name')}
                for t in tc_tags if isinstance(t, dict)
            ]

            case_data = {
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
                "raw_config": json.dumps(config, ensure_ascii=False)
            }
            export_data.append(case_data)
        return export_data

    # 生成CSV格式
    @staticmethod
    def _generate_csv_export(export_data):
        flattened_data = []
        audio_configs = []
        dimensions_data_list = []
        groups = []
        case_tags = []

        for item in export_data:
            config_data = item.get('config', {})
            # 优先从独立列读取，兼容旧 config
            ref_col = item.get('reference_params')
            if ref_col:
                asr_ref_text = _algo_query_svc.get_reference_text(ref_col, 'asr_reference_text')
                tran_ref_text = _algo_query_svc.get_reference_text(ref_col, 'translation_reference_text')
            else:
                asr_ref_text = _algo_query_svc.get_reference_text(config_data, 'asr_reference_text')
                tran_ref_text = _algo_query_svc.get_reference_text(config_data, 'translation_reference_text')
            flat_item = {
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
                "REMARKS": ""
            }
            flattened_data.append(flat_item)

            for audio in item.get('audios', []):
                audio_configs.append({
                    "CASE_ID": item['id'],
                    "CASE_NAME": item['name'],
                    "AUDIO_ID": audio.get('audio_id') or "",
                    "AUDIO_NAME": audio.get('audio_name', ''),
                    "SPL": audio.get('spl', ''),
                    "PLAYBACK_DEVICE_ID": audio.get('playback_device_id') or "",
                    "PLAYBACK_DEVICE_NAME": audio.get('playback_device_name', ''),
                    "PLAY_ORDER": audio.get('play_order', 0)
                })

            # 通过 gRPC 批量获取维度（替代直连 evaluation_service PO）
            all_dim_ids = item.get('dimension_ids', []) or []
            dim_map = {}
            if all_dim_ids:
                try:
                    res = _evaluation_acl.get_dimension_by_ids(all_dim_ids)
                    if res.get('success'):
                        dim_map = res.get('data') or {}
                except Exception:
                    logger.debug("导出时获取评分维度信息失败，dim_ids=%s", all_dim_ids, exc_info=True)
            for dim_id in all_dim_ids:
                dim_obj = dim_map.get(str(dim_id)) or {}
                dim_name = dim_obj.get('name') if dim_obj else str(dim_id)
                dim_display_name = dim_name
                weight = dim_obj.get('weight') if dim_obj else 50
                threshold = 80
                dimensions_data_list.append({
                    "CASE_ID": item['id'],
                    "CASE_NAME": item['name'],
                    "DIMENSION_ID": dim_id,
                    "DIMENSION_NAME": dim_name,
                    "DIMENSION_DISPLAY_NAME": dim_display_name,
                    "WEIGHT": weight,
                    "THRESHOLD": threshold
                })

            if item.get('group_id') or item.get('group'):
                groups.append({"group_id": item.get('group_id'), "group_name": item.get('group')})

            for tag_item in item.get('tag_items', []) or []:
                case_tags.append({
                    "CASE_ID": item['id'],
                    "CASE_NAME": item['name'],
                    "TAG_ID": tag_item.get("tag_id") or "",
                    "TAG_NAME": tag_item.get("tag_name") or ""
                })

        df = pd.DataFrame(flattened_data)
        df.to_csv(io.BytesIO(), index=False, encoding='utf-8-sig')
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        mimetype = 'text/csv'
        download_name = f"testcases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output.seek(0)
        return FileResponse(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )

    # 生成Excel格式
    @staticmethod
    def _generate_excel_export(export_data):
        flattened_data = []
        audio_configs = []
        dimensions_data_list = []
        groups = []
        case_tags = []

        for item in export_data:
            config_data = item.get('config', {})
            # 优先从独立列读取，兼容旧 config
            ref_col = item.get('reference_params')
            if ref_col:
                asr_ref_text = _algo_query_svc.get_reference_text(ref_col, 'asr_reference_text')
                tran_ref_text = _algo_query_svc.get_reference_text(ref_col, 'translation_reference_text')
            else:
                asr_ref_text = _algo_query_svc.get_reference_text(config_data, 'asr_reference_text')
                tran_ref_text = _algo_query_svc.get_reference_text(config_data, 'translation_reference_text')
            flat_item = {
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
                "REMARKS": ""
            }
            flattened_data.append(flat_item)

            for audio in item.get('audios', []):
                audio_configs.append({
                    "CASE_ID": item['id'],
                    "CASE_NAME": item['name'],
                    "AUDIO_ID": audio.get('audio_id') or "",
                    "AUDIO_NAME": audio.get('audio_name', ''),
                    "SPL": audio.get('spl', ''),
                    "PLAYBACK_DEVICE_ID": audio.get('playback_device_id') or "",
                    "PLAYBACK_DEVICE_NAME": audio.get('playback_device_name', ''),
                    "PLAY_ORDER": audio.get('play_order', 0)
                })

            # 通过 gRPC 批量获取维度（替代直连 evaluation_service PO）
            all_dim_ids = item.get('dimension_ids', []) or []
            dim_map = {}
            if all_dim_ids:
                try:
                    res = _evaluation_acl.get_dimension_by_ids(all_dim_ids)
                    if res.get('success'):
                        dim_map = res.get('data') or {}
                except Exception:
                    logger.debug("导出时获取评分维度信息失败，dim_ids=%s", all_dim_ids, exc_info=True)
            for dim_id in all_dim_ids:
                dim_obj = dim_map.get(str(dim_id)) or {}
                dim_name = dim_obj.get('name') if dim_obj else str(dim_id)
                dim_display_name = dim_name
                weight = dim_obj.get('weight') if dim_obj else 50
                threshold = 80
                dimensions_data_list.append({
                    "CASE_ID": item['id'],
                    "CASE_NAME": item['name'],
                    "DIMENSION_ID": dim_id,
                    "DIMENSION_NAME": dim_name,
                    "DIMENSION_DISPLAY_NAME": dim_display_name,
                    "WEIGHT": weight,
                    "THRESHOLD": threshold
                })

            if item.get('group_id') or item.get('group'):
                groups.append({"group_id": item.get('group_id'), "group_name": item.get('group')})

            for tag_item in item.get('tag_items', []) or []:
                case_tags.append({
                    "CASE_ID": item['id'],
                    "CASE_NAME": item['name'],
                    "TAG_ID": tag_item.get("tag_id") or "",
                    "TAG_NAME": tag_item.get("tag_name") or ""
                })

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            testcases_columns = [
                'ID', 'NAME', 'DESCRIPTION', 'GROUP_NAME', 'GROUP_ID',
                'TRANSLATION_DIRECTION', 'TEST_TYPE', 'NOISE_AUDIO_NAME', 'NOISE_AUDIO_ID',
                'NOISE_SPL', 'ASR_REFERENCE_TEXT', 'TRANSLATION_REFERENCE_TEXT',
                'TAGS', 'REMARKS'
            ]
            audio_configs_columns = [
                'CASE_ID', 'CASE_NAME', 'AUDIO_ID', 'AUDIO_NAME', 'SPL',
                'PLAYBACK_DEVICE_ID', 'PLAYBACK_DEVICE_NAME', 'PLAY_ORDER'
            ]
            dimensions_columns = [
                'CASE_ID', 'CASE_NAME', 'DIMENSION_ID', 'DIMENSION_NAME', 'DIMENSION_DISPLAY_NAME', 'WEIGHT', 'THRESHOLD'
            ]
            tags_columns = ['TAG_ID', 'TAG_NAME', 'TAG_DESCRIPTION', 'TAG_COLOR']
            groups_columns = ['GROUP_ID', 'GROUP_NAME', 'GROUP_DESCRIPTION', 'PARENT_GROUP_NAME']
            case_tags_columns = ['CASE_ID', 'CASE_NAME', 'TAG_ID', 'TAG_NAME']

            testcases_df = pd.DataFrame(flattened_data)
            if testcases_df.empty:
                testcases_df = pd.DataFrame(columns=testcases_columns)
            else:
                testcases_df = testcases_df.reindex(columns=testcases_columns)
            testcases_df.to_excel(writer, sheet_name='TestCases', index=False)

            audio_df = pd.DataFrame(audio_configs)
            if audio_df.empty:
                audio_df = pd.DataFrame(columns=audio_configs_columns)
            else:
                audio_df = audio_df.reindex(columns=audio_configs_columns)
            audio_df.to_excel(writer, sheet_name='AudioConfigs', index=False)

            dims_df = pd.DataFrame(dimensions_data_list)
            if dims_df.empty:
                dims_df = pd.DataFrame(columns=dimensions_columns)
            else:
                dims_df = dims_df.reindex(columns=dimensions_columns)
            dims_df.to_excel(writer, sheet_name='Dimensions', index=False)

            tag_names = set()
            for item in export_data:
                for t in item.get('tags', []):
                    if t:
                        tag_names.add(t)

            tags_rows = []
            if tag_names:
                # 通过 gRPC 获取标签（替代直连 task_service PO）
                tag_by_name = {}
                try:
                    res = _tag_acl.list_tags(page=1, per_page=500, keyword='')
                    if res.get('success'):
                        for t in (res.get('data') or {}).get('items', []):
                            if t.get('name'):
                                tag_by_name[t.get('name')] = t
                except Exception:
                    logger.debug("导出 Excel 时获取标签列表失败", exc_info=True)
                for name in sorted(tag_names):
                    tag_obj = tag_by_name.get(name) or {}
                    tags_rows.append({
                        "TAG_ID": tag_obj.get('id') if tag_obj else "",
                        "TAG_NAME": name,
                        "TAG_DESCRIPTION": tag_obj.get('description') if tag_obj else "",
                        "TAG_COLOR": tag_obj.get('color') if tag_obj else ""
                    })

            tags_df = pd.DataFrame(tags_rows)
            if tags_df.empty:
                tags_df = pd.DataFrame(columns=tags_columns)
            else:
                tags_df = tags_df.reindex(columns=tags_columns)
            tags_df.to_excel(writer, sheet_name='Tags', index=False)

            unique_groups = {}
            for g in groups:
                g_id = g.get("group_id")
                g_name = g.get("group_name")
                if g_id:
                    unique_groups[g_id] = g_name
                elif g_name and g_name not in unique_groups.values():
                    unique_groups[g_name] = g_name

            group_rows = []
            if unique_groups:
                # 通过 gRPC 按 id/name 批量查询 TestCaseGroup（替代直连 PO）
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

                for group_key, group_name in sorted(unique_groups.items(), key=lambda x: str(x[0])):
                    group_obj = group_by_id.get(group_key)
                    if not group_obj and group_name:
                        group_obj = next((g for g in group_by_id.values() if g.get('name') == group_name), None)
                    resolved_id = group_obj['id'] if group_obj else (group_key if group_key and group_key != group_name else "")
                    group_rows.append({
                        "GROUP_ID": resolved_id,
                        "GROUP_NAME": group_obj['name'] if group_obj else group_name,
                        "GROUP_DESCRIPTION": group_obj.get('description', '') if group_obj else "",
                        "PARENT_GROUP_NAME": ""
                    })
            groups_df = pd.DataFrame(group_rows)
            if groups_df.empty:
                groups_df = pd.DataFrame(columns=groups_columns)
            else:
                groups_df = groups_df.reindex(columns=groups_columns)
            groups_df.to_excel(writer, sheet_name='Groups', index=False)

            case_tags_df = pd.DataFrame(case_tags)
            if case_tags_df.empty:
                case_tags_df = pd.DataFrame(columns=case_tags_columns)
            else:
                case_tags_df = case_tags_df.reindex(columns=case_tags_columns)
            case_tags_df.to_excel(writer, sheet_name='CaseTags', index=False)

        output.seek(0)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        download_name = f"testcases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return FileResponse(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )

    # 导出测试用例
    @staticmethod
    def export_cases():
        try:
            test_cases, format_type, err = TestCaseImportExportService._query_cases_for_export()
            if err is not None:
                return err

            export_data = TestCaseImportExportService._build_export_rows(test_cases)

            if format_type == 'json':
                export_result = {
                    "test_cases": export_data,
                    "exported_at": now_cst().isoformat(),
                    "total_count": len(export_data)
                }
                return success_response(
                    TestCaseExportJsonData(
                        test_cases=[TestCaseExportItem(**item) for item in export_result["test_cases"]],
                        exported_at=export_result["exported_at"],
                        total_count=export_result["total_count"],
                    )
                )
            elif format_type == 'csv':
                return TestCaseImportExportService._generate_csv_export(export_data)
            elif format_type == 'xlsx':
                return TestCaseImportExportService._generate_excel_export(export_data)
            else:
                return error_response(f"不支持的导出格式: {format_type}")

        except Exception as e:
            return error_response(str(e))

    # 解析上传文件(CSV/Excel)
    @staticmethod
    def _parse_import_file(file):
        def parse_legacy_format(df):
            column_map = {
                "ID": "id",
                "用例名称": "name",
                "描述": "description",
                "分组": "group",
                "分组ID": "group_id",
                "标签": "tags_str",
                "raw_config": "raw_config"
            }

            test_cases_data = []
            for _, row in df.iterrows():
                case_item = {}
                for csv_col, data_key in column_map.items():
                    if csv_col in row:
                        val = row[csv_col]
                        if pd.isna(val):
                            case_item[data_key] = None
                        else:
                            case_item[data_key] = val

                if 'tags_str' in case_item and case_item['tags_str']:
                    case_item['tags'] = [t.strip() for t in str(case_item['tags_str']).split(',') if t.strip()]
                else:
                    case_item['tags'] = []

                if 'raw_config' in case_item and case_item['raw_config']:
                    try:
                        case_item['config'] = json.loads(case_item['raw_config'])
                    except:
                        case_item['config'] = {}

                test_cases_data.append(case_item)

            return test_cases_data

        file_extension = file.filename.split('.')[-1].lower()
        test_cases_data = []

        if file_extension == 'json':
            file_content = file.read().decode('utf-8')
            data = json.loads(file_content)
            test_cases_data = data.get('test_cases', [])
        elif file_extension in ['csv', 'xlsx', 'xls']:
            if file_extension == 'csv':
                df = pd.read_csv(io.BytesIO(file.read()), encoding='utf-8-sig')
                test_cases_data = parse_legacy_format(df)
            else:
                xl = pd.ExcelFile(io.BytesIO(file.read()))
                sheet_names = xl.sheet_names

                if 'TestCases' in sheet_names:
                    test_cases_data = []
                    audio_configs = {}
                    dimensions_by_case = {}

                    testcases_df = pd.read_excel(xl, sheet_name='TestCases')
                    audio_df = pd.read_excel(xl, sheet_name='AudioConfigs') if 'AudioConfigs' in sheet_names else None
                    dims_df = pd.read_excel(xl, sheet_name='Dimensions') if 'Dimensions' in sheet_names else None
                    case_tags_df = pd.read_excel(xl, sheet_name='CaseTags') if 'CaseTags' in sheet_names else None

                    case_tags_by_id = {}
                    case_tags_by_name = {}
                    if case_tags_df is not None and not case_tags_df.empty:
                        for _, ct_row in case_tags_df.iterrows():
                            c_id = str(ct_row.get('CASE_ID', '')).strip() if pd.notna(ct_row.get('CASE_ID')) else ''
                            c_name = str(ct_row.get('CASE_NAME', '')).strip() if pd.notna(ct_row.get('CASE_NAME')) else ''
                            t_id_raw = ct_row.get('TAG_ID')
                            t_name = str(ct_row.get('TAG_NAME', '')).strip() if pd.notna(ct_row.get('TAG_NAME')) else ''
                            t_id = None
                            try:
                                t_id = int(str(t_id_raw).strip()) if pd.notna(t_id_raw) and str(t_id_raw).strip() else None
                            except Exception:
                                t_id = None
                            tag_link = {"tag_id": t_id, "tag_name": t_name}
                            if c_id:
                                case_tags_by_id.setdefault(c_id, []).append(tag_link)
                            if c_name:
                                case_tags_by_name.setdefault(c_name, []).append(tag_link)

                    def normalize_cell(val):
                        if val is None or (hasattr(pd, "isna") and pd.isna(val)):
                            return None
                        text = str(val).strip()
                        return text if text else None

                    for _, row in testcases_df.iterrows():
                        case_item = {
                            'id': str(row.get('ID', '')).strip() if pd.notna(row.get('ID')) else None,
                            'name': str(row.get('NAME', '')).strip() if pd.notna(row.get('NAME')) else '',
                            'description': str(row.get('DESCRIPTION', '')) if pd.notna(row.get('DESCRIPTION')) else '',
                            'group': str(row.get('GROUP_NAME', '')).strip() if pd.notna(row.get('GROUP_NAME')) else '未分类',
                            'group_id': normalize_cell(row.get('GROUP_ID')),
                            'test_type': str(row.get('TEST_TYPE', '')) if pd.notna(row.get('TEST_TYPE')) else 'api',
                            'noise_audio_name': str(row.get('NOISE_AUDIO_NAME', '')) if pd.notna(row.get('NOISE_AUDIO_NAME')) else '',
                            'noise_audio_id': normalize_cell(row.get('NOISE_AUDIO_ID')),
                            'noise_spl': row.get('NOISE_SPL', 0) if pd.notna(row.get('NOISE_SPL')) else 0,
                            'asr_reference_text': str(row.get('ASR_REFERENCE_TEXT', '')) if pd.notna(row.get('ASR_REFERENCE_TEXT')) else '',
                            'translation_reference_text': str(row.get('TRANSLATION_REFERENCE_TEXT', '')) if pd.notna(row.get('TRANSLATION_REFERENCE_TEXT')) else '',
                            'tags': [t.strip() for t in str(row.get('TAGS', '')).split(',') if t.strip()] if pd.notna(row.get('TAGS')) else [],
                            'remarks': str(row.get('REMARKS', '')) if pd.notna(row.get('REMARKS')) else '',
                            'audios': [],
                            'dimensions': [],
                            'config': {},
                            'tag_links': []
                        }

                        if case_item['id'] and case_item['id'] in case_tags_by_id:
                            case_item['tag_links'] = case_tags_by_id.get(case_item['id'], [])
                        elif case_item['name'] and case_item['name'] in case_tags_by_name:
                            case_item['tag_links'] = case_tags_by_name.get(case_item['name'], [])

                        if case_item['tag_links']:
                            names = []
                            for tl in case_item['tag_links']:
                                if tl.get("tag_name"):
                                    names.append(tl["tag_name"])
                            case_item['tags'] = names

                        if audio_df is not None and not audio_df.empty:
                            if 'CASE_ID' in audio_df.columns and case_item['id']:
                                case_audios = audio_df[audio_df['CASE_ID'].astype(str).str.strip() == case_item['id']]
                            else:
                                case_audios = audio_df[audio_df['CASE_NAME'] == case_item['name']]

                            for _, audio_row in case_audios.iterrows():
                                audio_id_val = audio_row.get('AUDIO_ID')
                                playback_device_id_val = audio_row.get('PLAYBACK_DEVICE_ID')
                                try:
                                    audio_id = int(str(audio_id_val).strip()) if pd.notna(audio_id_val) and str(audio_id_val).strip() else None
                                except Exception:
                                    audio_id = None
                                try:
                                    playback_device_id = int(str(playback_device_id_val).strip()) if pd.notna(playback_device_id_val) and str(playback_device_id_val).strip() else None
                                except Exception:
                                    playback_device_id = None

                                if audio_id is None:
                                    audio_name = str(audio_row.get('AUDIO_NAME', '')).strip() if pd.notna(audio_row.get('AUDIO_NAME')) else ''
                                    if audio_name:
                                        # 通过 gRPC 按名称查找音频（替代直连 audio_service PO）
                                        try:
                                            res = _audio_acl.get_all({'page': 1, 'per_page': 1, 'keyword': audio_name})
                                            if res.get('success'):
                                                items = (res.get('data') or {}).get('items', [])
                                                if items and items[0].get('name') == audio_name:
                                                    audio_id = items[0].get('id')
                                        except Exception:
                                            logger.debug("导入时按名称查找音频ID失败，audio_name=%s", audio_name, exc_info=True)

                                case_item['audios'].append({
                                    'audio_id': audio_id,
                                    'audio_name': str(audio_row.get('AUDIO_NAME', '')) if pd.notna(audio_row.get('AUDIO_NAME')) else '',
                                    'spl': audio_row.get('SPL', 60) if pd.notna(audio_row.get('SPL')) else 60,
                                    'playback_device_id': playback_device_id,
                                    'playback_device_name': str(audio_row.get('PLAYBACK_DEVICE_NAME', '')) if pd.notna(audio_row.get('PLAYBACK_DEVICE_NAME')) else '',
                                    'play_order': audio_row.get('PLAY_ORDER', 0) if pd.notna(audio_row.get('PLAY_ORDER')) else 0
                                })

                        if dims_df is not None and not dims_df.empty:
                            if 'CASE_ID' in dims_df.columns and case_item['id']:
                                case_dims = dims_df[dims_df['CASE_ID'].astype(str).str.strip() == case_item['id']]
                            else:
                                case_dims = dims_df[dims_df['CASE_NAME'] == case_item['name']]

                            for _, dim_row in case_dims.iterrows():
                                dim_id_val = dim_row.get('DIMENSION_ID')
                                dim_id = None
                                try:
                                    dim_id = int(str(dim_id_val).strip()) if pd.notna(dim_id_val) and str(dim_id_val).strip() else None
                                except Exception:
                                    dim_id = None
                                case_item['dimensions'].append({
                                    'id': dim_id,
                                    'name': str(dim_row.get('DIMENSION_NAME', '')) if pd.notna(dim_row.get('DIMENSION_NAME')) else '',
                                    'display_name': str(dim_row.get('DIMENSION_DISPLAY_NAME', '')) if pd.notna(dim_row.get('DIMENSION_DISPLAY_NAME')) else '',
                                    'weight': dim_row.get('WEIGHT', 50) if pd.notna(dim_row.get('WEIGHT')) else 50,
                                    'threshold': dim_row.get('THRESHOLD', 80) if pd.notna(dim_row.get('THRESHOLD')) else 80
                                })

                        test_cases_data.append(case_item)
                else:
                    df = pd.read_excel(xl)
                    test_cases_data = parse_legacy_format(df)
        else:
            return None, error_response("仅支持 JSON, CSV 或 Excel 格式的导入")

        return test_cases_data, None

    # 验证导入数据
    @staticmethod
    def _validate_import_data(test_cases_data):
        if not test_cases_data:
            return error_response("导入数据为空")
        return None

    # 从行数据创建用例
    @staticmethod
    def _create_cases_from_rows(test_cases_data):
        imported_count = 0
        updated_count = 0
        errors = []

        for idx, case_data in enumerate(test_cases_data):
            try:
                # 1. 确定分组 — 通过 gRPC 查/建 TestCaseGroup（替代直连 PO）
                group = None
                group_id = case_data.get('group_id')
                group_name = case_data.get('group', '未分类')

                try:
                    from api_gateway.infrastructure.grpc_proxies import task_data_service
                    if group_id:
                        group = task_data_service.get_testcase_group_by_id(group_id)

                    if not group:
                        group = task_data_service.get_testcase_group_by_name(group_name)

                    if not group:
                        new_group = task_data_service.create_testcase_group(
                            name=group_name,
                            group_id=group_id if group_id else None,
                        )
                        group = new_group
                except Exception:
                    group = None

                # 2. 检查是更新还是创建
                tc_id = case_data.get('id')
                existing_tc = None
                if tc_id:
                    # 通过 gRPC 获取用例（替代直连 task_service PO）
                    res = _testcase_acl.get_testcase_detail(tc_id)
                    if res.get('success'):
                        existing_tc = res.get('data')
                    if not existing_tc:
                        raise Exception(f"UPDATE失败：未找到ID对应的用例: {tc_id}")

                # 3. 准备配置
                config = case_data.get('config', {})
                merged_config = config.copy() if config else {}

                noise_audio_name = (case_data.get('noise_audio_name') or '').strip()
                if noise_audio_name == "无":
                    noise_audio_name = ""
                noise_spl = case_data.get('noise_spl', 0) or 0
                noise_audio_id = case_data.get('noise_audio_id')
                resolved_noise_id = None
                if noise_audio_id:
                    try:
                        resolved_noise_id = int(str(noise_audio_id).strip())
                    except Exception:
                        resolved_noise_id = None

                if resolved_noise_id is None and noise_audio_name:
                    # 通过 gRPC 按名称查找音频（替代直连 audio_service PO）
                    try:
                        res = _audio_acl.get_all({'page': 1, 'per_page': 1, 'keyword': noise_audio_name})
                        if res.get('success'):
                            items = (res.get('data') or {}).get('items', [])
                            if items and items[0].get('name') == noise_audio_name:
                                resolved_noise_id = items[0].get('id')
                    except Exception:
                        logger.debug("导入时按名称查找噪声音频ID失败，noise_audio_name=%s", noise_audio_name, exc_info=True)

                if resolved_noise_id is not None or noise_spl:
                    bg_noise_cfg = {}
                    if resolved_noise_id is not None:
                        bg_noise_cfg['audio_id'] = resolved_noise_id
                    if noise_spl:
                        bg_noise_cfg['spl'] = noise_spl
                    if bg_noise_cfg:
                        merged_config['background_noise'] = bg_noise_cfg

                # 处理音频数据
                if 'audios' in case_data and case_data['audios']:
                    audios_data = case_data['audios']
                    standard_audios = []
                    for audio_item in audios_data:
                        standard_audios.append({
                            'audio_id': audio_item.get('audio_id'),
                            'spl': audio_item.get('spl'),
                            'playback_device_id': common.normalize_optional_int(audio_item.get('playback_device_id')),
                            'play_order': audio_item.get('play_order', 1)
                        })
                    merged_config['audios'] = standard_audios

                # 处理维度数据（扁平数组格式）
                if 'dimensions' in case_data and case_data['dimensions']:
                    dimensions_data = case_data['dimensions']
                    if isinstance(dimensions_data, list):
                        dimension_ids = [d.get('id') if isinstance(d, dict) else d for d in dimensions_data]
                        merged_config['dimensions'] = dimension_ids

                # 转换为 rounds 格式（已有 rounds 的不做转换）
                if not common.has_rounds(merged_config):
                    merged_config = common.convert_flat_config_to_rounds(merged_config)

                # 4. 执行创建或更新（通过 gRPC 调用 task_service）
                tc_payload = {
                    'name': case_data['name'],
                    'description': case_data.get('description'),
                    'group_id': group.get('id') if group else None,
                    'test_type': case_data.get('test_type', 'api'),
                    'config': merged_config,
                }

                # 收集标签数据（稍后通过 gRPC 设置）
                collected_tags = []

                # 5. 处理标签
                tag_links = case_data.get('tag_links') or []
                if tag_links:
                    for tag_link in tag_links:
                        tag_id = tag_link.get('tag_id')
                        tag_name = (tag_link.get('tag_name') or '').strip()
                        collected_tags.append({'tag_id': tag_id, 'tag_name': tag_name})
                else:
                    tags_data = case_data.get('tags', [])
                    for tag_name in tags_data:
                        collected_tags.append({'tag_id': None, 'tag_name': tag_name})

                if existing_tc:
                    # 更新（通过 gRPC）
                    res = _testcase_acl.update(tc_id, tc_payload)
                    if not res.get('success'):
                        raise Exception(f"更新用例失败: {res.get('message')}")
                    updated_count += 1
                else:
                    # 创建（通过 gRPC）
                    res = _testcase_acl.create(tc_payload)
                    if not res.get('success'):
                        raise Exception(f"创建用例失败: {res.get('message')}")
                    imported_count += 1

            except Exception as e:
                errors.append(f"第{idx+1}行: {str(e)}")

        return imported_count, updated_count, errors

    # 生成导入结果报告
    @staticmethod
    def _generate_import_report(imported_count, updated_count, errors):
        message = f"成功导入 {imported_count} 个用例，更新 {updated_count} 个用例"
        if errors:
            message += f"，{len(errors)} 个失败: {'; '.join(errors[:5])}"
            if len(errors) > 5:
                message += f" ... (共{len(errors)}个错误)"

        return success_response(TestCaseImportResult(imported_count=imported_count, errors=errors), message)

    @staticmethod
    def import_cases():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")

            file = request.files['file']
            if file.filename == '':
                return error_response("未选择文件")

            test_cases_data, err = TestCaseImportExportService._parse_import_file(file)
            if err is not None:
                return err

            err = TestCaseImportExportService._validate_import_data(test_cases_data)
            if err is not None:
                return err

            imported_count, updated_count, errors = TestCaseImportExportService._create_cases_from_rows(test_cases_data)

            # TestCaseGroup 创建已通过 gRPC 自动提交，无需本地 DB commit

            return TestCaseImportExportService._generate_import_report(imported_count, updated_count, errors)

        except json.JSONDecodeError as e:
            return error_response(f"JSON解析错误: {str(e)}")
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def download_template():
        try:
            output = io.BytesIO()

            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                testcases_df = pd.DataFrame(columns=[
                    'ID', 'NAME', 'DESCRIPTION', 'GROUP_NAME', 'GROUP_ID',
                    'TRANSLATION_DIRECTION', 'TEST_TYPE', 'NOISE_AUDIO_NAME', 'NOISE_AUDIO_ID',
                    'NOISE_SPL', 'ASR_REFERENCE_TEXT', 'TRANSLATION_REFERENCE_TEXT',
                    'TAGS', 'REMARKS'
                ])
                testcases_df.loc[0] = [
                    '', '示例用例名称', '用例详细描述', '示例分组', '',
                    '中文->英文', 'api', '', '', '', 'ASR参考文本', '翻译参考文本',
                    '标签1,标签2', '备注信息'
                ]
                testcases_df.to_excel(writer, sheet_name='TestCases', index=False)

                audio_configs_df = pd.DataFrame(columns=[
                    'CASE_ID', 'CASE_NAME', 'AUDIO_ID', 'AUDIO_NAME', 'SPL',
                    'PLAYBACK_DEVICE_ID', 'PLAYBACK_DEVICE_NAME', 'PLAY_ORDER'
                ])
                audio_configs_df.loc[0] = ['', '示例用例名称', '', '示例音频.wav', 65, '', '', 1]
                audio_configs_df.loc[1] = ['', '示例用例名称', '', '示例音频2.wav', 70, '', '扬声器', 2]
                audio_configs_df.to_excel(writer, sheet_name='AudioConfigs', index=False)

                dims_df = pd.DataFrame(columns=[
                    'CASE_ID', 'CASE_NAME', 'DIMENSION_ID', 'DIMENSION_NAME', 'DIMENSION_DISPLAY_NAME', 'WEIGHT', 'THRESHOLD'
                ])
                dims_df.loc[0] = ['', '示例用例名称', '', 'BLEU', 'BLEU分数', 60, 85]
                dims_df.loc[1] = ['', '示例用例名称', '', 'METEOR', 'METEOR分数', 40, 75]
                dims_df.loc[2] = ['', '示例用例名称', '', 'WER', '字错误率', 70, 90]
                dims_df.to_excel(writer, sheet_name='Dimensions', index=False)

                tags_df = pd.DataFrame(columns=[
                    'TAG_ID', 'TAG_NAME', 'TAG_DESCRIPTION', 'TAG_COLOR'
                ])
                tags_df.loc[0] = ['', '语音测试', '语音相关测试用例', '#1677FF']
                tags_df.to_excel(writer, sheet_name='Tags', index=False)

                groups_df = pd.DataFrame(columns=[
                    'GROUP_ID', 'GROUP_NAME', 'GROUP_DESCRIPTION', 'PARENT_GROUP_NAME'
                ])
                groups_df.loc[0] = ['', '新分组名称', '分组描述', '']
                groups_df.to_excel(writer, sheet_name='Groups', index=False)

                case_tags_df = pd.DataFrame(columns=[
                    'CASE_ID', 'CASE_NAME', 'TAG_ID', 'TAG_NAME'
                ])
                case_tags_df.loc[0] = ['', '示例用例名称', '', '语音测试']
                case_tags_df.to_excel(writer, sheet_name='CaseTags', index=False)

            output.seek(0)
            return FileResponse(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'testcase_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            return error_response(f"生成模板失败: {str(e)}")

    @staticmethod
    def preview_import():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")

            file = request.files['file']
            if file.filename == '':
                return error_response("未选择文件")

            file_extension = file.filename.split('.')[-1].lower()
            preview_result = {
                'totalRows': 0,
                'testCases': [],
                'audioConfigs': [],
                'dimensions': [],
                'tags': [],
                'groups': [],
                'errors': []
            }

            if file_extension in ['xlsx', 'xls']:
                xl = pd.ExcelFile(io.BytesIO(file.read()))
                sheet_names = xl.sheet_names

                if 'TestCases' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='TestCases')
                    preview_result['totalRows'] = len(df)
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['testCases'] = df.to_dict('records')

                if 'AudioConfigs' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='AudioConfigs')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['audioConfigs'] = df.to_dict('records')

                if 'Dimensions' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='Dimensions')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['dimensions'] = df.to_dict('records')

                if 'Tags' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='Tags')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['tags'] = df.to_dict('records')

                if 'Groups' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='Groups')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['groups'] = df.to_dict('records')
            elif file_extension == 'json':
                file_content = file.read().decode('utf-8')
                data = json.loads(file_content)
                preview_result['testCases'] = data.get('test_cases', [])
                preview_result['totalRows'] = len(preview_result['testCases'])
            elif file_extension == 'csv':
                df = pd.read_csv(io.BytesIO(file.read()), encoding='utf-8-sig')
                preview_result['totalRows'] = len(df)
                df = df.astype(object).where(pd.notna(df), None)
                preview_result['testCases'] = df.to_dict('records')
            else:
                return error_response("仅支持 JSON, CSV 或 Excel 格式")

            return success_response(data=preview_result)
        except Exception as e:
            return error_response(f"预览失败: {str(e)}")
