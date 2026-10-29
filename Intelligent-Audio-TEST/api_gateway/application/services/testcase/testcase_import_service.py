"""测试用例导入 Service。

从 TestCaseImportExportService 拆分，负责所有导入相关逻辑：
- 解析上传文件（JSON / CSV / Excel / ZIP 数据包）
- 验证导入数据
- 按重复策略（覆盖 / 跳过 / 另存副本）创建或更新用例
- 恢复 ZIP 包内的参考参数文件
"""
import json
import io
import logging
import zipfile
import pandas as pd
from datetime import datetime

from fastapi.responses import Response
from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.acl import (
    AudioAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
)
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.testcase import TestCaseImportResult
from shared.constants.testcase_transfer import (
    COPY_NAME_MAX_ATTEMPTS,
    COPY_NAME_SUFFIX,
    DEFAULT_DUPLICATE_STRATEGY,
    DUPLICATE_MATCH_ID,
    DUPLICATE_MATCH_NAME,
    DUPLICATE_STRATEGY_ALIASES,
    MAX_REFERENCE_PARAM_BYTES,
    NAME_LOOKUP_PAGE_SIZE,
    PREVIEW_DUPLICATE_SCAN_LIMIT,
    TESTCASES_FILENAME,
    TestCaseDuplicateStrategy,
)
from shared.utils import testcase_helpers as common

logger = logging.getLogger(__name__)

_testcase_acl = TestCaseConfigAclRepositoryImpl()
_audio_acl = AudioAclRepositoryImpl()


class TestCaseImportService:
    """测试用例导入服务（仅导入相关逻辑）"""

    # ------------------------------------------------------------------
    # 文件格式检测
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_import_format(filename):
        """检测文件类型（返回 'json' / 'csv' / 'xlsx' / 'xls' / 'zip' / None）"""
        file_extension = filename.split('.')[-1].lower()
        if file_extension == 'json':
            return 'json'
        elif file_extension in ('csv', 'xlsx', 'xls'):
            return file_extension
        elif file_extension == 'zip':
            return 'zip'
        return None

    # ------------------------------------------------------------------
    # 解析上传文件（薄编排层）
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_import_file(file):
        """解析上传文件（CSV/Excel/JSON/ZIP），薄编排层"""
        fmt = TestCaseImportService._detect_import_format(file.filename)
        if fmt is None:
            return None, error_response("仅支持 JSON, CSV, Excel 或 ZIP 格式的导入")

        if fmt == 'json':
            return TestCaseImportService._parse_json_file(file), None
        elif fmt == 'csv':
            return TestCaseImportService._parse_csv_rows(file), None
        elif fmt == 'zip':
            try:
                return TestCaseImportService._parse_zip_rows(file), None
            except ValueError as e:
                return None, error_response(str(e))
        else:
            return TestCaseImportService._parse_excel_rows(file), None

    @staticmethod
    def _parse_json_file(file):
        """解析 JSON 文件"""
        file_content = file.read().decode('utf-8')
        data = json.loads(file_content)
        return data.get('test_cases', [])

    @staticmethod
    def _parse_zip_rows(file):
        """解析 ZIP 数据包（manifest + testcases.json + 可选参考参数文件）。

        参考参数文件内容落到各用例的 `reference_params_content`
        （{round_number: 内容}），导入成功后回写。
        包结构非法时抛 ValueError。
        """
        try:
            zf = zipfile.ZipFile(io.BytesIO(file.read()))
        except zipfile.BadZipFile:
            raise ValueError("上传文件不是合法的 ZIP 包")

        with zf:
            names = set(zf.namelist())
            if TESTCASES_FILENAME not in names:
                raise ValueError(f"ZIP 包缺少 {TESTCASES_FILENAME}，不是用例数据包")

            try:
                data = json.loads(zf.read(TESTCASES_FILENAME).decode('utf-8'))
            except Exception as e:
                raise ValueError(f"{TESTCASES_FILENAME} 解析失败: {e}")

            if isinstance(data, dict):
                test_cases = data.get('test_cases') or []
            elif isinstance(data, list):
                test_cases = data
            else:
                raise ValueError(f"{TESTCASES_FILENAME} 格式不正确")

            for case in test_cases:
                if isinstance(case, dict):
                    TestCaseImportService._attach_reference_param_content(case, zf, names)
        return test_cases

    @staticmethod
    def _attach_reference_param_content(case, zf, names):
        """把包内参考参数文件内容读入 case['reference_params_content']"""
        files = case.pop('reference_param_files', None)
        if not isinstance(files, list):
            return
        contents = {}
        for file_item in files:
            if not isinstance(file_item, dict):
                continue
            zip_path = file_item.get('path')
            round_number = file_item.get('round_number') or file_item.get('roundNumber')
            if not zip_path or round_number is None or zip_path not in names:
                continue
            try:
                info = zf.getinfo(zip_path)
                if info.file_size > MAX_REFERENCE_PARAM_BYTES:
                    logger.warning("参考参数文件过大，跳过恢复: %s", zip_path)
                    continue
                contents[int(round_number)] = json.loads(zf.read(zip_path).decode('utf-8'))
            except Exception:
                logger.warning("读取包内参考参数文件失败: %s", zip_path, exc_info=True)
        if contents:
            case['reference_params_content'] = contents

    @staticmethod
    def _parse_csv_rows(file):
        """解析 CSV 文件"""
        df = pd.read_csv(io.BytesIO(file.read()), encoding='utf-8-sig')
        return TestCaseImportService._parse_legacy_format(df)

    @staticmethod
    def _parse_excel_rows(file):
        """解析 Excel 文件（自动判断新格式 / 旧格式）"""
        xl = pd.ExcelFile(io.BytesIO(file.read()))
        sheet_names = xl.sheet_names

        if 'TestCases' in sheet_names:
            return TestCaseImportService._parse_excel_new_format(xl, sheet_names)
        else:
            df = pd.read_excel(xl)
            return TestCaseImportService._parse_legacy_format(df)

    @staticmethod
    def _parse_legacy_format(df):
        """解析旧格式（CSV 或无 TestCases Sheet 的 Excel）"""
        column_map = {
            "ID": "id",
            "用例名称": "name",
            "描述": "description",
            "分组": "group",
            "分组ID": "group_id",
            "标签": "tags_str",
            "raw_config": "raw_config",
        }

        test_cases_data = []
        for _, row in df.iterrows():
            case_item = TestCaseImportService._build_legacy_case_item(row, column_map)
            test_cases_data.append(case_item)
        return test_cases_data

    @staticmethod
    def _build_legacy_case_item(row, column_map):
        """从旧格式行构建 case_item"""
        case_item = {}
        for csv_col, data_key in column_map.items():
            if csv_col in row:
                val = row[csv_col]
                case_item[data_key] = None if pd.isna(val) else val

        if case_item.get('tags_str'):
            case_item['tags'] = [t.strip() for t in str(case_item['tags_str']).split(',') if t.strip()]
        else:
            case_item['tags'] = []

        if case_item.get('raw_config'):
            try:
                case_item['config'] = json.loads(case_item['raw_config'])
            except Exception:
                case_item['config'] = {}

        return case_item

    # ------------------------------------------------------------------
    # Excel 新格式解析
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_excel_new_format(xl, sheet_names):
        """解析新格式 Excel（含 TestCases / AudioConfigs / Dimensions 等 Sheet）"""
        testcases_df = pd.read_excel(xl, sheet_name='TestCases')
        audio_df = pd.read_excel(xl, sheet_name='AudioConfigs') if 'AudioConfigs' in sheet_names else None
        dims_df = pd.read_excel(xl, sheet_name='Dimensions') if 'Dimensions' in sheet_names else None
        case_tags_df = pd.read_excel(xl, sheet_name='CaseTags') if 'CaseTags' in sheet_names else None

        case_tags_by_id, case_tags_by_name = TestCaseImportService._build_case_tag_indexes(case_tags_df)

        test_cases_data = []
        for _, row in testcases_df.iterrows():
            case_item = TestCaseImportService._build_case_from_row(row, case_tags_by_id, case_tags_by_name)
            TestCaseImportService._fill_case_audios(case_item, audio_df)
            TestCaseImportService._fill_case_dimensions(case_item, dims_df)
            test_cases_data.append(case_item)
        return test_cases_data

    @staticmethod
    def _build_case_tag_indexes(case_tags_df):
        """构建 CaseTags 的索引（按 ID 和按名称）"""
        case_tags_by_id = {}
        case_tags_by_name = {}
        if case_tags_df is None or case_tags_df.empty:
            return case_tags_by_id, case_tags_by_name

        for _, ct_row in case_tags_df.iterrows():
            c_id = str(ct_row.get('CASE_ID', '')).strip() if pd.notna(ct_row.get('CASE_ID')) else ''
            c_name = str(ct_row.get('CASE_NAME', '')).strip() if pd.notna(ct_row.get('CASE_NAME')) else ''
            t_id_raw = ct_row.get('TAG_ID')
            t_name = str(ct_row.get('TAG_NAME', '')).strip() if pd.notna(ct_row.get('TAG_NAME')) else ''
            t_id = TestCaseImportService._parse_int_or_none(t_id_raw)

            tag_link = {"tag_id": t_id, "tag_name": t_name}
            if c_id:
                case_tags_by_id.setdefault(c_id, []).append(tag_link)
            if c_name:
                case_tags_by_name.setdefault(c_name, []).append(tag_link)
        return case_tags_by_id, case_tags_by_name

    @staticmethod
    def _parse_int_or_none(val):
        """安全解析整数，失败返回 None"""
        try:
            return int(str(val).strip()) if pd.notna(val) and str(val).strip() else None
        except Exception:
            return None

    @staticmethod
    def _normalize_cell(val):
        """标准化单元格值（NaN → None）"""
        if val is None or (hasattr(pd, "isna") and pd.isna(val)):
            return None
        text = str(val).strip()
        return text if text else None

    @staticmethod
    def _build_case_from_row(row, case_tags_by_id, case_tags_by_name):
        """从 Excel 行构建 case_item（TestCases Sheet）"""
        case_item = {
            'id': str(row.get('ID', '')).strip() if pd.notna(row.get('ID')) else None,
            'name': str(row.get('NAME', '')).strip() if pd.notna(row.get('NAME')) else '',
            'description': str(row.get('DESCRIPTION', '')) if pd.notna(row.get('DESCRIPTION')) else '',
            'group': str(row.get('GROUP_NAME', '')).strip() if pd.notna(row.get('GROUP_NAME')) else '未分类',
            'group_id': TestCaseImportService._normalize_cell(row.get('GROUP_ID')),
            'noise_audio_name': str(row.get('NOISE_AUDIO_NAME', '')) if pd.notna(row.get('NOISE_AUDIO_NAME')) else '',
            'noise_audio_id': TestCaseImportService._normalize_cell(row.get('NOISE_AUDIO_ID')),
            'noise_spl': row.get('NOISE_SPL', 0) if pd.notna(row.get('NOISE_SPL')) else 0,
            'asr_reference_text': str(row.get('ASR_REFERENCE_TEXT', '')) if pd.notna(row.get('ASR_REFERENCE_TEXT')) else '',
            'translation_reference_text': str(row.get('TRANSLATION_REFERENCE_TEXT', '')) if pd.notna(row.get('TRANSLATION_REFERENCE_TEXT')) else '',
            'tags': [t.strip() for t in str(row.get('TAGS', '')).split(',') if t.strip()] if pd.notna(row.get('TAGS')) else [],
            'remarks': str(row.get('REMARKS', '')) if pd.notna(row.get('REMARKS')) else '',
            'audios': [],
            'dimensions': [],
            'config': {},
            'tag_links': [],
        }

        TestCaseImportService._attach_tag_links(case_item, case_tags_by_id, case_tags_by_name)
        return case_item

    @staticmethod
    def _attach_tag_links(case_item, case_tags_by_id, case_tags_by_name):
        """将 CaseTags 关联到 case_item，并覆盖 tags 字段"""
        if case_item['id'] and case_item['id'] in case_tags_by_id:
            case_item['tag_links'] = case_tags_by_id.get(case_item['id'], [])
        elif case_item['name'] and case_item['name'] in case_tags_by_name:
            case_item['tag_links'] = case_tags_by_name.get(case_item['name'], [])

        if case_item['tag_links']:
            names = [tl["tag_name"] for tl in case_item['tag_links'] if tl.get("tag_name")]
            case_item['tags'] = names

    @staticmethod
    def _fill_case_audios(case_item, audio_df):
        """从 AudioConfigs Sheet 填充用例音频"""
        if audio_df is None or audio_df.empty:
            return

        if 'CASE_ID' in audio_df.columns and case_item['id']:
            case_audios = audio_df[audio_df['CASE_ID'].astype(str).str.strip() == case_item['id']]
        else:
            case_audios = audio_df[audio_df['CASE_NAME'] == case_item['name']]

        for _, audio_row in case_audios.iterrows():
            case_item['audios'].append(TestCaseImportService._build_audio_from_row(audio_row))

    @staticmethod
    def _build_audio_from_row(audio_row):
        """从 AudioConfigs 行构建音频配置"""
        audio_id = TestCaseImportService._parse_int_or_none(audio_row.get('AUDIO_ID'))
        playback_device_id = TestCaseImportService._parse_int_or_none(audio_row.get('PLAYBACK_DEVICE_ID'))

        if audio_id is None:
            audio_name = str(audio_row.get('AUDIO_NAME', '')).strip() if pd.notna(audio_row.get('AUDIO_NAME')) else ''
            if audio_name:
                audio_id = TestCaseImportService._find_audio_id_by_name(audio_name)

        return {
            'audio_id': audio_id,
            'audio_name': str(audio_row.get('AUDIO_NAME', '')) if pd.notna(audio_row.get('AUDIO_NAME')) else '',
            'spl': audio_row.get('SPL', 60) if pd.notna(audio_row.get('SPL')) else 60,
            'playback_device_id': playback_device_id,
            'playback_device_name': str(audio_row.get('PLAYBACK_DEVICE_NAME', '')) if pd.notna(audio_row.get('PLAYBACK_DEVICE_NAME')) else '',
            'play_order': audio_row.get('PLAY_ORDER', 0) if pd.notna(audio_row.get('PLAY_ORDER')) else 0,
        }

    @staticmethod
    def _find_audio_id_by_name(audio_name):
        """通过 gRPC 按名称查找音频 ID"""
        try:
            res = _audio_acl.get_all({'page': 1, 'per_page': 1, 'keyword': audio_name})
            if res.get('success'):
                items = (res.get('data') or {}).get('items', [])
                if items and items[0].get('name') == audio_name:
                    return items[0].get('id')
        except Exception:
            logger.debug("导入时按名称查找音频ID失败，audio_name=%s", audio_name, exc_info=True)
        return None

    @staticmethod
    def _fill_case_dimensions(case_item, dims_df):
        """从 Dimensions Sheet 填充用例维度"""
        if dims_df is None or dims_df.empty:
            return

        if 'CASE_ID' in dims_df.columns and case_item['id']:
            case_dims = dims_df[dims_df['CASE_ID'].astype(str).str.strip() == case_item['id']]
        else:
            case_dims = dims_df[dims_df['CASE_NAME'] == case_item['name']]

        for _, dim_row in case_dims.iterrows():
            case_item['dimensions'].append(TestCaseImportService._build_dimension_from_row(dim_row))

    @staticmethod
    def _build_dimension_from_row(dim_row):
        """从 Dimensions 行构建维度配置"""
        dim_id = TestCaseImportService._parse_int_or_none(dim_row.get('DIMENSION_ID'))
        return {
            'id': dim_id,
            'name': str(dim_row.get('DIMENSION_NAME', '')) if pd.notna(dim_row.get('DIMENSION_NAME')) else '',
            'display_name': str(dim_row.get('DIMENSION_DISPLAY_NAME', '')) if pd.notna(dim_row.get('DIMENSION_DISPLAY_NAME')) else '',
            'weight': dim_row.get('WEIGHT', 50) if pd.notna(dim_row.get('WEIGHT')) else 50,
            'threshold': dim_row.get('THRESHOLD', 80) if pd.notna(dim_row.get('THRESHOLD')) else 80,
        }

    # ------------------------------------------------------------------
    # 验证
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_import_data(test_cases_data):
        """验证导入数据"""
        if not test_cases_data:
            return error_response("导入数据为空")
        return None

    @staticmethod
    def _validate_imported_case(case_data):
        """验证单个用例数据，返回错误消息或 None"""
        if not case_data.get('name'):
            return "用例名称不能为空"
        return None

    # ------------------------------------------------------------------
    # 重复处理策略
    # ------------------------------------------------------------------
    @staticmethod
    def _read_duplicate_strategy():
        """读取导入重复策略（表单 on_duplicate / onDuplicate），默认跳过。

        兼容旧表单开关 `overwrite=true`（既有 TestCaseImportRequest 字段）。
        """
        raw = request.form.get('on_duplicate') or request.form.get('onDuplicate')
        if raw is not None and str(raw).strip():
            return DUPLICATE_STRATEGY_ALIASES.get(
                str(raw).strip().lower(), DEFAULT_DUPLICATE_STRATEGY)

        overwrite = request.form.get('overwrite')
        if overwrite is not None and str(overwrite).strip().lower() in ('true', '1', 'yes'):
            return TestCaseDuplicateStrategy.OVERWRITE
        return DEFAULT_DUPLICATE_STRATEGY

    # ------------------------------------------------------------------
    # 从行数据创建用例（薄编排层）
    # ------------------------------------------------------------------
    @staticmethod
    def _create_cases_from_rows(test_cases_data,
                                on_duplicate=DEFAULT_DUPLICATE_STRATEGY):
        """从行数据创建/覆盖/跳过/另存副本用例。

        Returns: (imported, updated, skipped, copied, errors)
        """
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        copied_count = 0
        errors = []

        for idx, case_data in enumerate(test_cases_data):
            try:
                err = TestCaseImportService._validate_imported_case(case_data)
                if err:
                    errors.append(f"第{idx + 1}行: {err}")
                    continue

                group = TestCaseImportService._resolve_or_create_group(case_data)
                existing_tc, _ = TestCaseImportService._find_existing_case(case_data, group)

                if existing_tc and on_duplicate == TestCaseDuplicateStrategy.SKIP:
                    skipped_count += 1
                    continue

                tc_payload = TestCaseImportService._build_case_payload(case_data, group)
                case_id = TestCaseImportService._persist_case(
                    tc_payload, existing_tc, on_duplicate, group)

                if existing_tc and on_duplicate == TestCaseDuplicateStrategy.OVERWRITE:
                    updated_count += 1
                elif existing_tc:
                    copied_count += 1
                else:
                    imported_count += 1

                TestCaseImportService._restore_reference_params(
                    case_id, case_data, errors, idx)

            except Exception as e:
                errors.append(f"第{idx + 1}行: {str(e)}")

        return imported_count, updated_count, skipped_count, copied_count, errors

    @staticmethod
    def _persist_case(tc_payload, existing_tc, on_duplicate, group):
        """按重复策略落库，返回用例 id（覆盖=更新；副本=改名新建）"""
        if existing_tc and on_duplicate == TestCaseDuplicateStrategy.OVERWRITE:
            case_id = existing_tc.get('id')
            res = _testcase_acl.update(case_id, tc_payload)
            if not res.get('success'):
                raise Exception(f"覆盖用例失败: {res.get('message')}")
            return case_id

        if existing_tc:
            # 另存副本：同分组内名称唯一
            tc_payload['name'] = TestCaseImportService._build_copy_name(
                tc_payload['name'], group)

        res = _testcase_acl.create(tc_payload)
        if not res.get('success'):
            raise Exception(f"创建用例失败: {res.get('message')}")
        return (res.get('data') or {}).get('id')

    @staticmethod
    def _build_copy_name(base_name, group):
        """生成同分组内唯一的副本名称（name_copy / name_copy2 …）"""
        group_id = group.get('id') if group else None
        candidate = f"{base_name}{COPY_NAME_SUFFIX}"
        for i in range(2, COPY_NAME_MAX_ATTEMPTS + 1):
            if not TestCaseImportService._find_case_by_name(candidate, group_id):
                return candidate
            candidate = f"{base_name}{COPY_NAME_SUFFIX}{i}"
        return f"{base_name}{COPY_NAME_SUFFIX}{datetime.now().strftime('%H%M%S')}"

    @staticmethod
    def _resolve_or_create_group(case_data):
        """确定分组 — 通过 gRPC 查/建 TestCaseGroup"""
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
                group = task_data_service.create_testcase_group(
                    name=group_name,
                    group_id=group_id if group_id else None,
                )
        except Exception:
            group = None
        return group

    @staticmethod
    def _lookup_group(case_data):
        """只查不建分组（预览重复项用，避免预览产生副作用）"""
        group = None
        group_id = case_data.get('group_id')
        group_name = case_data.get('group', '未分类')

        try:
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            if group_id:
                group = task_data_service.get_testcase_group_by_id(group_id)
            if not group and group_name:
                group = task_data_service.get_testcase_group_by_name(group_name)
        except Exception:
            group = None
        return group

    @staticmethod
    def _find_existing_case(case_data, group=None):
        """检测重复用例：ID 命中优先，其次同分组同名。

        Returns: (existing_case_or_None, 'id' | 'name' | None)
        """
        tc_id = case_data.get('id')
        if tc_id:
            res = _testcase_acl.get_testcase_detail(tc_id)
            if res.get('success') and res.get('data'):
                return res.get('data'), DUPLICATE_MATCH_ID

        name = (case_data.get('name') or '').strip()
        group_id = group.get('id') if group else None
        if not name or not group_id:
            # 分组尚不存在（导入时会新建）→ 组内不可能已有同名用例
            return None, None

        existing = TestCaseImportService._find_case_by_name(name, group_id)
        if existing:
            return existing, DUPLICATE_MATCH_NAME
        return None, None

    @staticmethod
    def _find_case_by_name(name, group_id):
        """同分组内按名称精确查找用例（关键字模糊查询后本地精确比对）"""
        if not name or not group_id:
            return None
        try:
            res = _testcase_acl.list_testcases(
                page=1, per_page=NAME_LOOKUP_PAGE_SIZE,
                keyword=name, group_id=group_id)
        except Exception:
            logger.debug("导入重复检测查询失败，name=%s", name, exc_info=True)
            return None
        if not res.get('success'):
            return None

        for item in (res.get('data') or {}).get('items', []) or []:
            if (str(item.get('name') or '').strip() == name
                    and str(item.get('group_id')) == str(group_id)):
                return item
        return None

    @staticmethod
    def _restore_reference_params(case_id, case_data, errors, idx):
        """把 ZIP 包内参考参数文件内容回写到新用例（逐轮）"""
        contents = case_data.get('reference_params_content') or {}
        if not case_id or not contents:
            return
        for round_number, content in contents.items():
            try:
                res = _testcase_acl.update_ref_params(
                    case_id, int(round_number), {'referenceParams': content})
                if not res.get('success'):
                    errors.append(
                        f"第{idx + 1}行: 第{round_number}轮参考参数恢复失败: "
                        f"{res.get('message')}")
            except Exception as e:
                errors.append(
                    f"第{idx + 1}行: 第{round_number}轮参考参数恢复异常: {e}")

    @staticmethod
    def _build_case_payload(case_data, group):
        """构建用例创建/更新的 payload"""
        config = case_data.get('config') or {}
        merged_config = config.copy() if isinstance(config, dict) else {}

        # 扁平格式（Excel/CSV 老格式）才需要把音频/维度/噪声合并进 config；
        # ZIP/JSON 的 config 已含 rounds 结构，直接原样使用，避免把轮次音频打平。
        if not common.has_rounds(merged_config):
            TestCaseImportService._merge_noise_config(merged_config, case_data)
            TestCaseImportService._merge_audios_config(merged_config, case_data)
            TestCaseImportService._merge_dimensions_config(merged_config, case_data)
            merged_config = common.convert_flat_config_to_rounds(merged_config)

        payload = {
            'name': case_data['name'],
            'description': case_data.get('description'),
            'group_id': group.get('id') if group else None,
            'config': merged_config,
        }

        tag_names = TestCaseImportService._collect_tag_names(case_data)
        if tag_names:
            payload['tags'] = tag_names
        if case_data.get('algorithm_params'):
            payload['algorithm_params'] = case_data['algorithm_params']
        if case_data.get('algorithm_type'):
            payload['algorithm_type'] = case_data['algorithm_type']
        # 评估策略引用（strategy_id/overrides）不随包迁移：跨环境策略 id 不存在
        # 会导致写入失败，config 中已带物化后的维度/噪声结果。
        return payload

    @staticmethod
    def _merge_noise_config(merged_config, case_data):
        """合并噪声配置"""
        noise_audio_name = (case_data.get('noise_audio_name') or '').strip()
        if noise_audio_name == "无":
            noise_audio_name = ""
        noise_spl = case_data.get('noise_spl', 0) or 0
        noise_audio_id = case_data.get('noise_audio_id')
        resolved_noise_id = TestCaseImportService._parse_int_or_none(noise_audio_id)

        if resolved_noise_id is None and noise_audio_name:
            resolved_noise_id = TestCaseImportService._find_audio_id_by_name(noise_audio_name)

        if resolved_noise_id is not None or noise_spl:
            bg_noise_cfg = {}
            if resolved_noise_id is not None:
                bg_noise_cfg['audio_id'] = resolved_noise_id
            if noise_spl:
                bg_noise_cfg['spl'] = noise_spl
            if bg_noise_cfg:
                merged_config['background_noise'] = bg_noise_cfg

    @staticmethod
    def _merge_audios_config(merged_config, case_data):
        """合并音频配置"""
        if 'audios' not in case_data or not case_data['audios']:
            return
        standard_audios = []
        for audio_item in case_data['audios']:
            standard_audios.append({
                'audio_id': audio_item.get('audio_id'),
                'spl': audio_item.get('spl'),
                'playback_device_id': common.normalize_optional_int(audio_item.get('playback_device_id')),
                'play_order': audio_item.get('play_order', 1),
            })
        merged_config['audios'] = standard_audios

    @staticmethod
    def _merge_dimensions_config(merged_config, case_data):
        """合并维度配置（扁平数组格式）"""
        if 'dimensions' not in case_data or not case_data['dimensions']:
            return
        dimensions_data = case_data['dimensions']
        if isinstance(dimensions_data, list):
            dimension_ids = [d.get('id') if isinstance(d, dict) else d for d in dimensions_data]
            merged_config['dimensions'] = dimension_ids

    @staticmethod
    def _collect_tag_names(case_data):
        """收集标签名（CaseTags 关联优先，其次 TAGS 列），去重保序"""
        names = []
        for tag_link in case_data.get('tag_links') or []:
            name = (tag_link.get('tag_name') or '').strip()
            if name and name not in names:
                names.append(name)
        for tag in case_data.get('tags') or []:
            name = tag.get('name') if isinstance(tag, dict) else str(tag)
            name = (name or '').strip()
            if name and name not in names:
                names.append(name)
        return names

    # ------------------------------------------------------------------
    # 生成导入结果报告
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_import_report(imported_count, updated_count, skipped_count,
                                copied_count, errors):
        """生成导入结果报告"""
        message = (
            f"成功导入 {imported_count} 个用例，覆盖 {updated_count} 个，"
            f"跳过重复 {skipped_count} 个，另存副本 {copied_count} 个"
        )
        if errors:
            message += f"，{len(errors)} 个失败: {'; '.join(str(e) for e in errors[:5])}"
            if len(errors) > 5:
                message += f" ... (共{len(errors)}个错误)"

        return success_response(
            TestCaseImportResult(
                imported_count=imported_count,
                updated_count=updated_count,
                skipped_count=skipped_count,
                copied_count=copied_count,
                errors=errors,
            ),
            message,
        )

    # ------------------------------------------------------------------
    # 导入入口
    # ------------------------------------------------------------------
    @staticmethod
    def import_cases():
        """导入测试用例（薄编排层）"""
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")

            file = request.files['file']
            if file.filename == '':
                return error_response("未选择文件")

            test_cases_data, err = TestCaseImportService._parse_import_file(file)
            if err is not None:
                return err

            err = TestCaseImportService._validate_import_data(test_cases_data)
            if err is not None:
                return err

            on_duplicate = TestCaseImportService._read_duplicate_strategy()
            imported_count, updated_count, skipped_count, copied_count, errors = \
                TestCaseImportService._create_cases_from_rows(test_cases_data, on_duplicate)
            return TestCaseImportService._generate_import_report(
                imported_count, updated_count, skipped_count, copied_count, errors)

        except json.JSONDecodeError as e:
            return error_response(f"JSON解析错误: {str(e)}")
        except Exception as e:
            return error_response(str(e))

    # ------------------------------------------------------------------
    # 预览导入
    # ------------------------------------------------------------------
    @staticmethod
    def preview_import():
        """预览导入文件内容"""
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")

            file = request.files['file']
            if file.filename == '':
                return error_response("未选择文件")

            fmt = TestCaseImportService._detect_import_format(file.filename)
            if fmt is None:
                return error_response("仅支持 JSON, CSV, Excel 或 ZIP 格式")

            preview_result = TestCaseImportService._build_preview_result(file, fmt)
            return success_response(data=preview_result)

        except Exception as e:
            return error_response(f"预览失败: {str(e)}")

    @staticmethod
    def _build_preview_result(file, fmt):
        """构建预览结果（含重复用例检测，便于前端选择覆盖/跳过）"""
        preview_result = {
            'totalRows': 0,
            'testCases': [],
            'audioConfigs': [],
            'dimensions': [],
            'tags': [],
            'groups': [],
            'errors': [],
            'duplicates': [],
            'duplicateCount': 0,
            'duplicateStrategyDefault': DEFAULT_DUPLICATE_STRATEGY.value,
        }

        if fmt in ('xlsx', 'xls'):
            TestCaseImportService._fill_excel_preview(file, preview_result)
        elif fmt == 'json':
            TestCaseImportService._fill_json_preview(file, preview_result)
        elif fmt == 'csv':
            TestCaseImportService._fill_csv_preview(file, preview_result)
        elif fmt == 'zip':
            TestCaseImportService._fill_zip_preview(file, preview_result)

        TestCaseImportService._detect_preview_duplicates(preview_result)
        return preview_result

    @staticmethod
    def _detect_preview_duplicates(preview_result):
        """逐行检测重复用例并回填 duplicates/duplicateCount（只读，不建分组）。"""
        duplicates = []
        rows = preview_result.get('testCases') or []
        scan_rows = rows[:PREVIEW_DUPLICATE_SCAN_LIMIT]
        for idx, row in enumerate(scan_rows):
            case_data = TestCaseImportService._normalize_preview_case(row)
            if not case_data.get('id') and not case_data.get('name'):
                continue
            try:
                group = TestCaseImportService._lookup_group(case_data)
                existing, matched_by = TestCaseImportService._find_existing_case(
                    case_data, group)
            except Exception:
                logger.debug("预览重复检测失败，row=%s", idx + 1, exc_info=True)
                continue
            if not existing:
                continue
            duplicates.append({
                'row': idx + 1,
                'name': case_data.get('name'),
                'id': case_data.get('id'),
                'existingId': existing.get('id'),
                'existingName': existing.get('name'),
                'matchedBy': matched_by,
            })
        preview_result['duplicates'] = duplicates
        preview_result['duplicateCount'] = len(duplicates)
        preview_result['duplicateScanTruncated'] = len(rows) > len(scan_rows)

    @staticmethod
    def _normalize_preview_case(row):
        """把各格式预览行归一为 {id,name,group,group_id}（Excel 列名大写）"""
        if not isinstance(row, dict):
            return {}

        def pick(*keys):
            for key in keys:
                value = row.get(key)
                if value is None:
                    continue
                try:
                    if pd.isna(value):
                        continue
                except (TypeError, ValueError):
                    pass
                if str(value).strip():
                    return value
            return None

        return {
            'id': pick('id', 'ID'),
            'name': pick('name', 'NAME', '用例名称'),
            'group': pick('group', 'GROUP_NAME', '分组'),
            'group_id': pick('group_id', 'GROUP_ID', '分组ID'),
        }

    @staticmethod
    def _fill_zip_preview(file, preview_result):
        """填充 ZIP 数据包预览结果（不把包内参考参数内容透给前端）"""
        test_cases = TestCaseImportService._parse_zip_rows(file)
        preview_cases = [
            {k: v for k, v in case.items() if k != 'reference_params_content'}
            if isinstance(case, dict) else case
            for case in test_cases
        ]
        preview_result['testCases'] = preview_cases
        preview_result['totalRows'] = len(preview_cases)

    @staticmethod
    def _fill_excel_preview(file, preview_result):
        """填充 Excel 预览结果"""
        xl = pd.ExcelFile(io.BytesIO(file.read()))
        sheet_names = xl.sheet_names

        sheet_map = {
            'TestCases': 'testCases',
            'AudioConfigs': 'audioConfigs',
            'Dimensions': 'dimensions',
            'Tags': 'tags',
            'Groups': 'groups',
        }
        for sheet_name, result_key in sheet_map.items():
            if sheet_name in sheet_names:
                df = pd.read_excel(xl, sheet_name=sheet_name)
                if sheet_name == 'TestCases':
                    preview_result['totalRows'] = len(df)
                df = df.astype(object).where(pd.notna(df), None)
                preview_result[result_key] = df.to_dict('records')

    @staticmethod
    def _fill_json_preview(file, preview_result):
        """填充 JSON 预览结果"""
        file_content = file.read().decode('utf-8')
        data = json.loads(file_content)
        preview_result['testCases'] = data.get('test_cases', [])
        preview_result['totalRows'] = len(preview_result['testCases'])

    @staticmethod
    def _fill_csv_preview(file, preview_result):
        """填充 CSV 预览结果"""
        df = pd.read_csv(io.BytesIO(file.read()), encoding='utf-8-sig')
        preview_result['totalRows'] = len(df)
        df = df.astype(object).where(pd.notna(df), None)
        preview_result['testCases'] = df.to_dict('records')

    # ------------------------------------------------------------------
    # 模板下载
    # ------------------------------------------------------------------
    @staticmethod
    def download_template():
        """下载导入模板"""
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                TestCaseImportService._write_template_sheets(writer)
            output.seek(0)
            # 内存字节流下载用 Response（FileResponse 仅接受磁盘路径，
            # 且其参数名为 media_type/filename 而非 Flask 的 mimetype/download_name）
            return Response(
                content=output.getvalue(),
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={"Content-Disposition": f"attachment; filename=testcase_template_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"},
            )
        except Exception as e:
            return error_response(f"生成模板失败: {str(e)}")

    @staticmethod
    def _write_template_sheets(writer):
        """写入模板的所有 Sheet"""
        TestCaseImportService._write_template_testcases(writer)
        TestCaseImportService._write_template_audio_configs(writer)
        TestCaseImportService._write_template_dimensions(writer)
        TestCaseImportService._write_template_tags(writer)
        TestCaseImportService._write_template_groups(writer)
        TestCaseImportService._write_template_case_tags(writer)

    @staticmethod
    def _write_template_testcases(writer):
        """写入模板 TestCases Sheet"""
        cols = [
            'ID', 'NAME', 'DESCRIPTION', 'GROUP_NAME', 'GROUP_ID',
            'TRANSLATION_DIRECTION', 'TEST_TYPE', 'NOISE_AUDIO_NAME', 'NOISE_AUDIO_ID',
            'NOISE_SPL', 'ASR_REFERENCE_TEXT', 'TRANSLATION_REFERENCE_TEXT',
            'TAGS', 'REMARKS',
        ]
        df = pd.DataFrame(columns=cols)
        df.loc[0] = [
            '', '示例用例名称', '用例详细描述', '示例分组', '',
            '中文->英文', 'api', '', '', '', 'ASR参考文本', '翻译参考文本',
            '标签1,标签2', '备注信息',
        ]
        df.to_excel(writer, sheet_name='TestCases', index=False)

    @staticmethod
    def _write_template_audio_configs(writer):
        """写入模板 AudioConfigs Sheet"""
        cols = [
            'CASE_ID', 'CASE_NAME', 'AUDIO_ID', 'AUDIO_NAME', 'SPL',
            'PLAYBACK_DEVICE_ID', 'PLAYBACK_DEVICE_NAME', 'PLAY_ORDER',
        ]
        df = pd.DataFrame(columns=cols)
        df.loc[0] = ['', '示例用例名称', '', '示例音频.wav', 65, '', '', 1]
        df.loc[1] = ['', '示例用例名称', '', '示例音频2.wav', 70, '', '扬声器', 2]
        df.to_excel(writer, sheet_name='AudioConfigs', index=False)

    @staticmethod
    def _write_template_dimensions(writer):
        """写入模板 Dimensions Sheet"""
        cols = [
            'CASE_ID', 'CASE_NAME', 'DIMENSION_ID', 'DIMENSION_NAME',
            'DIMENSION_DISPLAY_NAME', 'WEIGHT', 'THRESHOLD',
        ]
        df = pd.DataFrame(columns=cols)
        df.loc[0] = ['', '示例用例名称', '', 'BLEU', 'BLEU分数', 60, 85]
        df.loc[1] = ['', '示例用例名称', '', 'METEOR', 'METEOR分数', 40, 75]
        df.loc[2] = ['', '示例用例名称', '', 'WER', '字错误率', 70, 90]
        df.to_excel(writer, sheet_name='Dimensions', index=False)

    @staticmethod
    def _write_template_tags(writer):
        """写入模板 Tags Sheet"""
        cols = ['TAG_ID', 'TAG_NAME', 'TAG_DESCRIPTION', 'TAG_COLOR']
        df = pd.DataFrame(columns=cols)
        df.loc[0] = ['', '语音测试', '语音相关测试用例', '#1677FF']
        df.to_excel(writer, sheet_name='Tags', index=False)

    @staticmethod
    def _write_template_groups(writer):
        """写入模板 Groups Sheet"""
        cols = ['GROUP_ID', 'GROUP_NAME', 'GROUP_DESCRIPTION', 'PARENT_GROUP_NAME']
        df = pd.DataFrame(columns=cols)
        df.loc[0] = ['', '新分组名称', '分组描述', '']
        df.to_excel(writer, sheet_name='Groups', index=False)

    @staticmethod
    def _write_template_case_tags(writer):
        """写入模板 CaseTags Sheet"""
        cols = ['CASE_ID', 'CASE_NAME', 'TAG_ID', 'TAG_NAME']
        df = pd.DataFrame(columns=cols)
        df.loc[0] = ['', '示例用例名称', '', '语音测试']
        df.to_excel(writer, sheet_name='CaseTags', index=False)
