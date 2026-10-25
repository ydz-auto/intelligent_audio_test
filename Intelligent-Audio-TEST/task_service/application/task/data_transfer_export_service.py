# -*- coding: utf-8 -*-
"""任务数据导出应用服务（M1 导出引擎编排）

流程：校验入参 → 清理过期临时 ZIP → 读 task_service 段 8 表 → 收集用例引用 →
gRPC 拉维度评分（evaluation_service）与报告 7 表（report_service）→
经存储抽象收集文件 → 流式打包 ZIP 落盘 DATA_TRANSFER_TMP_DIR/export/。
ZIP 不走 gRPC，由网关 FileResponse 直接从共享盘返回下载。
"""
import os
import time
import uuid
from typing import Dict, List

from shared.constants.data_transfer import (
    DEFAULT_INCLUDE_AUDIOS,
    DEFAULT_INCLUDE_REF_PARAMS,
    DEFAULT_INCREMENTAL_INCLUDE,
    EXPORT_TEMP_MAX_AGE_SECONDS,
    INCREMENTAL_NO_SOURCE_MAP_MESSAGE,
    INCREMENTAL_SINGLE_TASK_MESSAGE,
    INCREMENTAL_UNMAPPED_CODE,
    INCREMENTAL_UNMAPPED_RESULT_MESSAGE,
    IncrementalInclude,
    TransferTable,
)
from shared.infrastructure.config import BaseConfig
from shared.utils.data_transfer_server import resolve_transfer_server_id
from shared.utils.log_handler import log_not_emit
from task_service.domain.services.data_transfer import (
    build_incremental_manifest,
    build_manifest,
    case_set_hash,
    collect_external_references,
    collect_raw_object_refs,
    translate_dimension_rows,
    translate_report_tables,
)
from task_service.infrastructure.acl.evaluation_transfer_acl import evaluation_transfer_acl_repository
from task_service.infrastructure.acl.report_transfer_acl import report_transfer_acl_repository
from task_service.infrastructure.persistence.transfer_repository import transfer_repository
from task_service.infrastructure.transfer.file_transfer import (
    iter_audio_entries,
    iter_ref_params_entries,
    iter_result_file_entries,
)
from task_service.infrastructure.transfer.raw_payload_store import (
    RawObjectCollector,
    RawObjectError,
    iter_raw_object_entries,
)
from task_service.infrastructure.transfer.zip_io import build_zip

_MODULE_NAME = 'data_transfer_export'


def _export_tmp_dir() -> str:
    return os.path.join(BaseConfig.DATA_TRANSFER_TMP_DIR, 'export')


def _resolve_include(options: Dict) -> List[str]:
    """解析增量包的 include 段（取值 dimensions / reports，缺省两段全带）。

    Raises: ValueError（未知段名或显式空列表）——调用方映射 400。
    """
    raw = options.get('include')
    if raw is None:
        return list(DEFAULT_INCREMENTAL_INCLUDE)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        raise ValueError('include 必须是字符串数组')
    valid = {item.value for item in IncrementalInclude}
    requested = [str(item).strip().lower() for item in raw if str(item).strip()]
    unknown = sorted(set(requested) - valid)
    if unknown:
        raise ValueError(f'include 含未知段 {unknown}（支持: {sorted(valid)}）')
    if not requested:
        raise ValueError('include 不能为空')
    # 固定按枚举顺序输出，避免请求顺序影响 manifest 内容与缓存判断
    return [item.value for item in IncrementalInclude if item.value in set(requested)]



def _sweep_expired_exports() -> int:
    """清理超过 1 小时的导出临时 ZIP（每次导出时顺带执行）。返回清理数"""
    removed = 0
    try:
        now = time.time()
        for name in os.listdir(_export_tmp_dir()):
            path = os.path.join(_export_tmp_dir(), name)
            if os.path.isfile(path) and now - os.path.getmtime(path) > EXPORT_TEMP_MAX_AGE_SECONDS:
                os.remove(path)
                removed += 1
    except FileNotFoundError:
        os.makedirs(_export_tmp_dir(), exist_ok=True)
    except Exception as e:
        log_not_emit('WARNING', _MODULE_NAME, f'清理过期导出 ZIP 失败: {e}', category='system')
    return removed


class _FileStatsCollector:
    """包装文件条目迭代器，边流式写包边统计条数与总字节数（manifest 延迟生成用）"""

    def __init__(self, entries):
        self._entries = entries
        self.file_count = 0
        self.total_size = 0

    def __iter__(self):
        for name, data in self._entries:
            self.file_count += 1
            self.total_size += len(data)
            yield name, data


class DataTransferExportService:
    """导出编排"""

    def export_tasks(self, task_ids: List[int], options: Dict = None) -> dict:
        """导出任务数据为 ZIP。

        Returns: {'success', 'message', 'data': {'zip_path', 'manifest', 'file_count', 'total_file_size'}}
        """
        options = options or {}
        include_ref_params = bool(options.get(
            'include_ref_params', options.get('includeRefParams', DEFAULT_INCLUDE_REF_PARAMS)))
        include_audios = bool(options.get(
            'include_audios', options.get('includeAudios', DEFAULT_INCLUDE_AUDIOS)))

        clean_ids = sorted({int(tid) for tid in (task_ids or [])})
        if not clean_ids:
            return {'success': False, 'message': 'task_ids 不能为空', 'code': 400}

        # INT-423：导出逐行可见性过滤——私有非 owner 任务跳过（不整批放行）
        from shared.infrastructure.user_context import get_current_user_id, get_current_user_is_admin
        from task_service.infrastructure.persistence.task_repository import task_repository
        clean_ids = task_repository.filter_visible_task_ids(
            clean_ids, user_id=get_current_user_id(),
            is_admin=get_current_user_is_admin())
        if not clean_ids:
            return {'success': False, 'message': '没有可导出的任务', 'code': 404}

        _sweep_expired_exports()

        # 1) task_service 段 8 表（含 cherry-pick 容器关系表与内联结果，INT-656）
        rows_by_table = transfer_repository.fetch_export_rows(clean_ids)
        exported_task_rows = rows_by_table.get(TransferTable.TEST_TASKS.value) or []
        found_ids = {row['id'] for row in exported_task_rows}
        missing = [tid for tid in clean_ids if tid not in found_ids]
        if missing:
            return {'success': False, 'message': f'任务不存在或已删除: {missing}', 'code': 404}
        if not exported_task_rows:
            return {'success': False, 'message': '没有可导出的任务', 'code': 404}

        # 2) 用例引用（参考参数 / 音频）
        refs = collect_external_references(rows_by_table)
        case_configs = transfer_repository.fetch_case_configs(refs['test_case_ids'])
        result_rows = rows_by_table.get(TransferTable.TEST_RESULTS.value) or []
        result_ids = [row['id'] for row in result_rows if row.get('id') is not None]

        # 3) 跨服务只读导出：维度评分（evaluation_service）+ 报告 7 表（report_service）
        dimensions_data = evaluation_transfer_acl_repository.export_dimensions_for_tasks(result_ids)
        dimension_rows = dimensions_data.get('dimensions') or []
        dimension_defs = dimensions_data.get('dimension_defs') or []
        report_tables = report_transfer_acl_repository.export_reports_for_tasks(clean_ids)
        report_rows = report_tables.get(TransferTable.TEST_REPORTS.value) or []

        # 4) 文件收集（存储抽象读取，逐文件流式产出）
        entries_iter = iter_result_file_entries(result_rows)
        if include_ref_params:
            ref_lists = [cfg.get('reference_params') for cfg in case_configs.values()]
            entries_iter = _chain(entries_iter, iter_ref_params_entries(ref_lists))
        if include_audios:
            audio_infos = self._collect_audio_infos(case_configs)
            entries_iter = _chain(entries_iter, iter_audio_entries(audio_infos))
        # 4.5) 原始报文对象（INT-1811）：维度行上的 uri 按内容寻址去重打包。
        #      导出读不到对象即整包失败（不得跳过：行里有 uri、包里没对象 =
        #      对端一库悬空指针）。原始报文不计入 fileCount（单独在 rawObjects 段）
        raw_refs, raw_errors = collect_raw_object_refs(dimension_rows)
        if raw_errors:
            return {'success': False,
                    'message': '原始报文对象无法定位（导出中止，避免产生悬空指针）: '
                               + '；'.join(raw_errors[:5]),
                    'code': 500}
        raw_collector = RawObjectCollector(iter_raw_object_entries(raw_refs))
        stats_collector = _FileStatsCollector(entries_iter)

        # 5) manifest（fileCount/totalFileSize 由 stats_collector 延迟填充）
        def _manifest_provider():
            return build_manifest(
                task_rows=exported_task_rows,
                result_rows=result_rows,
                dimension_count=len(dimension_rows),
                report_count=len(report_rows),
                file_count=stats_collector.file_count,
                total_file_size=stats_collector.total_size,
                include_ref_params=include_ref_params,
                include_audios=include_audios,
                # INT-1760 / D0 A4：写稳定服务标识（配置项），导入侧以它作
                # source_map.source_server；不再依赖会随容器重建变化的 hostname
                source=resolve_transfer_server_id(),
                # INT-1811：包内原始报文对象清单（与 files/raw/ 条目一一对应）
                raw_objects=raw_collector.summary(),
            )

        db_tables = {table.value: rows_by_table.get(table.value, []) for table in TransferTable}
        for table, rows in report_tables.items():
            if table in db_tables:
                db_tables[table] = rows
        db_tables[TransferTable.TEST_RESULT_DIMENSIONS.value] = dimension_rows
        zip_name = f"task_export_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(_export_tmp_dir(), zip_name)
        try:
            build_zip(zip_path, db_tables, _manifest_provider,
                      _chain(stats_collector, raw_collector),
                      dimensions_snapshot=dimension_defs)
        except RawObjectError as e:
            _discard_zip(zip_path)
            log_not_emit('ERROR', _MODULE_NAME,
                         f'导出中止（原始报文对象不可用）: {e}', category='system')
            return {'success': False, 'message': f'导出失败: {e}', 'code': 500}

        manifest = _manifest_provider()
        log_not_emit('INFO', _MODULE_NAME,
                     f'导出完成: tasks={clean_ids} zip={zip_name} '
                     f'files={stats_collector.file_count} '
                     f'rawObjects={raw_collector.count}', category='system')
        return {
            'success': True,
            'message': '导出成功',
            'data': {
                'zip_path': zip_path,
                'manifest': manifest,
                'file_count': stats_collector.file_count,
                'total_file_size': stats_collector.total_size,
                'raw_object_count': raw_collector.count,
                'raw_object_bytes': raw_collector.total_bytes,
            },
        }

    # ---------- 增量导出（链路 2，INT-1761 / D0 裁定 A1-A2） ----------

    def export_incremental(self, task_ids: List[int], options: Dict = None) -> dict:
        """导出增量包（新评估 + 新报告，id 经 source_map 翻译回 A 原始 id）。

        与整包导出的差异：
        - 版本 1.1 + `sourceTask{id,caseCount,caseSetHash}`（A1 / A7）；
        - 只含 `test_result_dimensions` + 报告 7 表，不含任务 / 结果 / 文件（A2-1）；
        - **导出侧硬闸**：任一维度行的 result id 在 source_map 里没有映射
          （= B 侧重执行新产生的结果）→ 整包拒绝 409 + `unmappedResultIds`
          （A2-2），绝不产出指向 A 不存在结果的包。

        Returns: {'success', 'message', 'data': {'zip_path', 'manifest', ...}}
        """
        options = options or {}
        try:
            include = _resolve_include(options)
        except ValueError as e:
            return {'success': False, 'message': str(e), 'code': 400}

        clean_ids = sorted({int(tid) for tid in (task_ids or []) if tid is not None})
        if not clean_ids:
            return {'success': False, 'message': 'task_ids 不能为空', 'code': 400}
        if len(clean_ids) > 1:
            # A 侧增量导入只支持单任务（A7）；导出先拒绝，避免产出没人能导的包
            return {'success': False, 'message': INCREMENTAL_SINGLE_TASK_MESSAGE,
                    'code': 400, 'data': {'taskIds': clean_ids}}

        # 可见性口径与整包导出一致（私有非 owner 任务不导出）
        from shared.infrastructure.user_context import (
            get_current_user_id, get_current_user_is_admin,
        )
        from task_service.infrastructure.persistence.task_repository import task_repository
        clean_ids = task_repository.filter_visible_task_ids(
            clean_ids, user_id=get_current_user_id(),
            is_admin=get_current_user_is_admin())
        if not clean_ids:
            return {'success': False, 'message': '没有可导出的任务', 'code': 404}
        local_task_id = clean_ids[0]

        # 1) 反查源任务：B 本地 id → (source_server, A 原始 task_id)
        refs = transfer_repository.fetch_source_task_refs([local_task_id])
        if not refs:
            return {'success': False, 'message': INCREMENTAL_NO_SOURCE_MAP_MESSAGE,
                    'code': 400, 'data': {'taskId': local_task_id}}
        source_servers = sorted({ref['source_server'] for ref in refs})
        if len(source_servers) > 1:
            return {'success': False,
                    'message': '该任务存在多个源服务映射，无法确定 id 翻译基准',
                    'code': INCREMENTAL_UNMAPPED_CODE,
                    'data': {'taskId': local_task_id, 'sourceServers': source_servers}}
        source_server = source_servers[0]
        source_task_id = int(refs[0]['source_id'])

        rows_by_table = transfer_repository.fetch_export_rows(clean_ids)
        task_rows = rows_by_table.get(TransferTable.TEST_TASKS.value) or []
        if not task_rows:
            return {'success': False, 'message': f'任务不存在或已删除: {clean_ids}', 'code': 404}
        task_row = task_rows[0]
        result_rows = rows_by_table.get(TransferTable.TEST_RESULTS.value) or []
        # 只取本任务自己的结果：整包导出的 fetch_export_rows 会把 cherry-pick 容器
        # 内联的外部任务结果一并带回，那些结果不属于本任务、也不在增量搬运范围
        local_result_ids = [row['id'] for row in result_rows
                            if row.get('id') is not None
                            and row.get('task_id') == local_task_id]
        case_ids = [row.get('test_case_id')
                    for row in rows_by_table.get(TransferTable.TASK_CASE_RELATIONS.value) or []]

        # 2) 维度段：result id 翻译回 A 原始 id（dimension_id 保留 B 值）
        dimension_rows: List[dict] = []
        dimension_defs: List[dict] = []
        if IncrementalInclude.DIMENSIONS.value in include:
            dimensions_data = evaluation_transfer_acl_repository.export_dimensions_for_tasks(
                local_result_ids)
            raw_rows = dimensions_data.get('dimensions') or []
            dimension_defs = dimensions_data.get('dimension_defs') or []
            result_map = transfer_repository.fetch_source_ids_by_local_ids(
                source_server, 'test_results', local_result_ids)
            dimension_rows, unmapped = translate_dimension_rows(raw_rows, result_map)
            if unmapped:
                log_not_emit('WARNING', _MODULE_NAME,
                             f'增量导出硬闸：{len(unmapped)} 个结果在 source_map 无映射 '
                             f'task={local_task_id} unmapped={unmapped[:20]}',
                             category='system')
                return {'success': False,
                        'message': INCREMENTAL_UNMAPPED_RESULT_MESSAGE,
                        'code': INCREMENTAL_UNMAPPED_CODE,
                        'data': {'unmappedResultIds': unmapped,
                                 'unmappedResultCount': len(unmapped)}}

        # 3) 报告段：task_id 必须能翻译；报告 id 有映射才写 A id（A5-2）
        report_tables: Dict[str, List[dict]] = {}
        if IncrementalInclude.REPORTS.value in include:
            raw_tables = report_transfer_acl_repository.export_reports_for_tasks(clean_ids)
            report_ids = [row.get('id') for row in raw_tables.get(
                TransferTable.TEST_REPORTS.value) or [] if row.get('id') is not None]
            report_map = transfer_repository.fetch_source_ids_by_local_ids(
                source_server, 'test_reports', report_ids)
            report_tables, unmapped_tasks = translate_report_tables(
                raw_tables, {local_task_id: source_task_id}, report_map)
            if unmapped_tasks:
                log_not_emit('WARNING', _MODULE_NAME,
                             f'增量导出：报告 task_id 无映射 task={local_task_id} '
                             f'unmapped={unmapped_tasks[:20]}', category='system')
                return {'success': False,
                        'message': '包内报告无法翻译回源任务（B 侧任务未整包导入过 A 的数据）',
                        'code': INCREMENTAL_UNMAPPED_CODE,
                        'data': {'unmappedTaskIds': unmapped_tasks}}

        # 4) 打包（无结果/音频文件条目；但维度行引用的原始报文对象必须随包携带，
        #    INT-1811：只搬行不搬对象 = 对端一库悬空指针）
        db_tables: Dict[str, List[dict]] = {}
        if IncrementalInclude.DIMENSIONS.value in include:
            db_tables[TransferTable.TEST_RESULT_DIMENSIONS.value] = dimension_rows
        if IncrementalInclude.REPORTS.value in include:
            db_tables.update(report_tables)

        raw_refs, raw_errors = collect_raw_object_refs(dimension_rows)
        if raw_errors:
            return {'success': False,
                    'message': '原始报文对象无法定位（导出中止，避免产生悬空指针）: '
                               + '；'.join(raw_errors[:5]),
                    'code': 500}
        raw_collector = RawObjectCollector(iter_raw_object_entries(raw_refs))

        # manifest 延迟生成：rawObjects 清单在对象条目写完后才完整（与整包同口径）
        def _manifest_provider():
            return build_incremental_manifest(
                source_task={
                    'id': source_task_id,
                    'name': task_row.get('name'),
                    'caseCount': len(case_ids),
                    'caseSetHash': case_set_hash(case_ids),
                },
                task_rows=[{
                    'id': source_task_id,
                    'name': task_row.get('name'),
                    'status': task_row.get('status'),
                    'resultCount': len(local_result_ids),
                }],
                dimension_count=len(dimension_rows),
                report_count=len(report_tables.get(TransferTable.TEST_REPORTS.value) or []),
                entities=include,
                # serverInfo.source 写 B 自己的稳定标识（A 导入侧仅作诊断，不参与合并）
                source=resolve_transfer_server_id(),
                options={'include': include},
                raw_objects=raw_collector.summary(),
            )
        _sweep_expired_exports()
        zip_name = (f"incremental_{time.strftime('%Y%m%d%H%M%S')}_"
                    f'{uuid.uuid4().hex[:8]}.zip')
        zip_path = os.path.join(_export_tmp_dir(), zip_name)
        try:
            build_zip(zip_path, db_tables, _manifest_provider, raw_collector,
                      dimensions_snapshot=dimension_defs)
        except RawObjectError as e:
            _discard_zip(zip_path)
            log_not_emit('ERROR', _MODULE_NAME,
                         f'增量导出中止（原始报文对象不可用）: {e}', category='system')
            return {'success': False, 'message': f'增量导出失败: {e}', 'code': 500}
        manifest = _manifest_provider()

        log_not_emit('INFO', _MODULE_NAME,
                     f'增量导出完成: localTask={local_task_id} sourceTask={source_task_id} '
                     f'include={include} dims={len(dimension_rows)} '
                     f'reports={len(report_tables.get(TransferTable.TEST_REPORTS.value) or [])} '
                     f'rawObjects={raw_collector.count} zip={zip_name}', category='system')
        return {
            'success': True,
            'message': '增量导出成功',
            'data': {
                'zip_path': zip_path,
                'manifest': manifest,
                'sourceTaskId': source_task_id,
                'dimensionCount': len(dimension_rows),
                'reportCount': len(report_tables.get(TransferTable.TEST_REPORTS.value) or []),
                'rawObjectCount': raw_collector.count,
                'rawObjectBytes': raw_collector.total_bytes,
            },
        }

    @staticmethod
    def _collect_audio_infos(case_configs: Dict[str, dict]) -> List[dict]:
        """从用例配置收集音频 ID 并经 audio_service ACL 批量查询音频信息"""
        from shared.utils.testcase_helpers import collect_audios
        from task_service.infrastructure.acl.audio_acl_repository import audio_acl_repository

        audio_ids = set()
        for cfg in case_configs.values():
            for item in collect_audios(cfg.get('config') or {}):
                audio_id = item.get('audio_id')
                if audio_id:
                    audio_ids.add(audio_id)
        if not audio_ids:
            return []
        audio_map = audio_acl_repository.list_audios_by_ids(audio_ids)
        return [info for info in audio_map.values() if info]


def _chain(first, second):
    yield from first
    yield from second


def _discard_zip(zip_path: str) -> None:
    """导出中途失败时删掉半成品 ZIP（不留坏包给下载）"""
    try:
        if os.path.isfile(zip_path):
            os.remove(zip_path)
    except OSError as e:
        log_not_emit('WARNING', _MODULE_NAME,
                     f'清理半成品导出 ZIP 失败: {zip_path}: {e}', category='system')


data_transfer_export_service = DataTransferExportService()
