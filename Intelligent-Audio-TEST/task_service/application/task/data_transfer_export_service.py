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
    DEFAULT_DOC_VERSION_SCOPE,
    DEFAULT_INCLUDE_AUDIOS,
    DEFAULT_INCLUDE_REF_PARAMS,
    DOC_VERSION_SCOPES,
    EXPORT_TEMP_MAX_AGE_SECONDS,
    TransferTable,
)
from shared.infrastructure.config import BaseConfig
from shared.utils.data_transfer_server import resolve_transfer_server_id
from shared.utils.log_handler import log_not_emit
from task_service.domain.services.data_transfer import build_manifest, collect_external_references
from task_service.domain.services.data_transfer.manifest import build_report_package_manifest
from task_service.infrastructure.acl.evaluation_transfer_acl import evaluation_transfer_acl_repository
from task_service.infrastructure.acl.report_transfer_acl import report_transfer_acl_repository
from task_service.infrastructure.persistence.transfer_repository import transfer_repository
from task_service.infrastructure.transfer.file_transfer import (
    iter_audio_entries,
    iter_ref_params_entries,
    iter_result_file_entries,
)
from task_service.infrastructure.transfer.zip_io import build_zip

_MODULE_NAME = 'data_transfer_export'


def _export_tmp_dir() -> str:
    return os.path.join(BaseConfig.DATA_TRANSFER_TMP_DIR, 'export')


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
            )

        db_tables = {table.value: rows_by_table.get(table.value, []) for table in TransferTable}
        for table, rows in report_tables.items():
            if table in db_tables:
                db_tables[table] = rows
        db_tables[TransferTable.TEST_RESULT_DIMENSIONS.value] = dimension_rows
        zip_name = f"task_export_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(_export_tmp_dir(), zip_name)
        build_zip(zip_path, db_tables, _manifest_provider, stats_collector,
                  dimensions_snapshot=dimension_defs)

        manifest = _manifest_provider()
        log_not_emit('INFO', _MODULE_NAME,
                     f'导出完成: tasks={clean_ids} zip={zip_name} '
                     f'files={stats_collector.file_count}', category='system')
        return {
            'success': True,
            'message': '导出成功',
            'data': {
                'zip_path': zip_path,
                'manifest': manifest,
                'file_count': stats_collector.file_count,
                'total_file_size': stats_collector.total_size,
            },
        }

    def export_report_package(self, task_ids: List[int], report_ids: List[int] = None,
                              doc_version_scope: str = None) -> dict:
        """导出报告包（链路 3a 平台报告 + 3b/3c Studio 文档）。

        Returns: {'success', 'message', 'data': {'zip_path', 'manifest'}}；失败带 code。
        """
        scope = (doc_version_scope or DEFAULT_DOC_VERSION_SCOPE).strip().lower()
        if scope not in DOC_VERSION_SCOPES:
            return {'success': False, 'code': 400,
                    'message': f'docVersionScope 非法: {doc_version_scope!r}'}
        clean_task_ids = sorted({int(t) for t in (task_ids or [])})
        clean_report_ids = sorted({int(r) for r in (report_ids or [])})
        if not clean_task_ids and not clean_report_ids:
            return {'success': False, 'code': 400, 'message': 'taskId / reportIds 至少提供一个'}

        # INT-423 口径：导出逐行可见性过滤——私有非 owner 任务跳过
        if clean_task_ids:
            from shared.infrastructure.user_context import (
                get_current_user_id, get_current_user_is_admin)
            from task_service.infrastructure.persistence.task_repository import task_repository
            clean_task_ids = task_repository.filter_visible_task_ids(
                clean_task_ids, user_id=get_current_user_id(),
                is_admin=get_current_user_is_admin())
            if not clean_task_ids:
                return {'success': False, 'code': 404, 'message': '没有可导出的任务'}

        package = report_transfer_acl_repository.export_report_package(
            clean_task_ids, clean_report_ids, scope)
        tables = package.get('tables') or {}
        studio = package.get('studio') or {}
        package_report_ids = [int(rid) for rid in (package.get('reportIds') or [])]
        all_task_ids = sorted({int(t) for t in (package.get('taskIds') or clean_task_ids)})
        if not all_task_ids:
            return {'success': False, 'code': 404, 'message': '报告不存在或已删除'}

        task_names = transfer_repository.fetch_task_names(all_task_ids)
        # sourceTask.id：A 侧原任务 id（B 导出时经 source_map 反查；无映射视为同一端）
        local_task_id = all_task_ids[0] if len(all_task_ids) == 1 else None
        source_ids = {}
        if local_task_id is not None:
            source_ids = transfer_repository.fetch_source_ids_by_local_ids(
                resolve_transfer_server_id(), 'tasks', [local_task_id])
        source_task_id = source_ids.get(local_task_id, local_task_id)
        task_name = task_names.get(source_task_id) or task_names.get(local_task_id) or ''

        counts = {}
        for table, rows in tables.items():
            counts[table] = len(rows or [])
        for table, rows in studio.items():
            counts[table] = len(rows or [])
        manifest = build_report_package_manifest(
            source_task_id=source_task_id,
            local_task_id=local_task_id,
            task_name=task_name,
            report_ids=package_report_ids,
            doc_version_scope=scope,
            entities=package.get('entities') or [],
            counts=counts,
            source=resolve_transfer_server_id())

        _sweep_expired_exports()
        db_tables = {table: rows for table, rows in tables.items()}
        db_tables.update({table: rows for table, rows in studio.items()})
        zip_name = f"report_export_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(_export_tmp_dir(), zip_name)
        build_zip(zip_path, db_tables, manifest, iter(()))
        log_not_emit('INFO', _MODULE_NAME,
                     f'报告包导出完成: tasks={all_task_ids} reports={package_report_ids} '
                     f'zip={zip_name}', category='system')
        return {'success': True, 'message': '导出成功',
                'data': {'zip_path': zip_path, 'manifest': manifest}}

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


data_transfer_export_service = DataTransferExportService()
