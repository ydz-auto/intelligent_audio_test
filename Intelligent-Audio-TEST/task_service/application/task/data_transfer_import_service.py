# -*- coding: utf-8 -*-
"""任务数据导入应用服务（M4 导入执行编排）

分段提交 + 补偿回滚（跨服务无单事务，架构红线禁止直写他服务表）：
  1. task_service 单事务写入自身 7 表（ID 重映射 + 外键改写 + 批次主键登记）
  2. gRPC evaluation_service.ImportDimensions（单事务 + 自登记批次）
  3. gRPC report_service.ImportReports（单事务 + 自登记批次）
  4. 文件经存储抽象回写（放最后：DB 全部成功后才动文件）
  5. 更新 result_data_path（task_id 重映射的行，独立小事务）

任一段失败：按逆序补偿（清文件 → 报表回滚 → 维度回滚 → task 段回滚）；
补偿自身失败必须显式报错要求人工介入（批次登记保留 TTL 7 天），不得静默。
"""
import uuid
from typing import Dict, List

from shared.constants.data_transfer import (
    FkMappingKey,
    ImportProgressStep,
    TransferTable,
    fk_rules_of,
)
from shared.utils.data_transfer import conflicted_ids as _conflicted_ids
from shared.utils.data_transfer import parse_storage_path, remap_task_id_in_key
from shared.utils.data_transfer_batch import transfer_batch_registry
from shared.utils.log_handler import log_not_emit
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
from task_service.domain.services.data_transfer import (
    filter_merge_relations,
    plan_task_segment,
    rewrite_fk_rows,
)
from task_service.infrastructure.acl.evaluation_transfer_acl import evaluation_transfer_acl_repository
from task_service.infrastructure.acl.report_transfer_acl import report_transfer_acl_repository
from task_service.infrastructure.persistence.transfer_repository import transfer_repository
from task_service.infrastructure.transfer.file_transfer import (
    delete_written_files,
    write_audio_files,
    write_case_result_files,
    write_ref_param_files,
)
from task_service.infrastructure.transfer.zip_io import (
    audios_entries,
    case_results_entries,
    read_db_tables,
    read_manifest,
    ref_params_entries,
)
from task_service.application.task.import_progress_reporter import ImportProgressReporter
from task_service.domain.services.data_transfer.manifest import validate_manifest

_MODULE_NAME = 'data_transfer_import'

_REPORT_TABLES = (TransferTable.TEST_REPORTS, TransferTable.REPORT_SUMMARIES,
                  TransferTable.REPORT_SUMMARY_META, TransferTable.REPORT_RAW_DATA,
                  TransferTable.REPORT_CASES, TransferTable.REPORT_METRIC_STATS,
                  TransferTable.REPORT_COMPARISON_MATRIX)

_CONFLICT_PREVIEW_CAP = 500

# 远端应用服务在"DB 已提交但批次登记失败"时返回的专用错误前缀（审计问题 1③）：
# 编排层据此把该段并入人工介入清单，防止孤儿数据静默残留
_COMMITTED_WITHOUT_REGISTRY_MARKER = '已提交但批次登记失败'


def _remaps_only(mapping: Dict[int, int]) -> Dict[int, int]:
    """只保留真正的重映射条目（远端 rewrite 语义 mapping.get(old, old) 下，
    映射到自身的条目冗余，剔除以减小 gRPC payload）"""
    return {k: v for k, v in (mapping or {}).items() if k != v}


class DataTransferImportService:
    """导入编排（预检 / 执行 / 批次回滚）"""

    # ---------- 预检（M3） ----------

    def preview_import(self, zip_path: str) -> dict:
        """解析 ZIP 并返回预检结果（manifest 摘要 + stats + conflicts + warnings）。"""
        manifest = validate_manifest(read_manifest(zip_path))
        rows_by_table = read_db_tables(zip_path)

        existing = transfer_repository.fetch_existing_ids()
        task_rows = rows_by_table.get(TransferTable.TEST_TASKS.value) or []
        result_rows = rows_by_table.get(TransferTable.TEST_RESULTS.value) or []

        existing_task_ids = existing.get(TransferTable.TEST_TASKS.value) or set()
        conflict_task_ids = _conflicted_ids(task_rows, existing_task_ids)
        conflict_task_names = transfer_repository.fetch_task_names(conflict_task_ids)

        existing_result_ids = existing.get(TransferTable.TEST_RESULTS.value) or set()
        conflict_result_ids = _conflicted_ids(result_rows, existing_result_ids)

        conflicts = (
            [{'table': TransferTable.TEST_TASKS.value, 'id': tid,
              'existingName': conflict_task_names.get(tid, '')}
             for tid in conflict_task_ids]
            + [{'table': TransferTable.TEST_RESULTS.value, 'id': rid, 'existingName': ''}
               for rid in conflict_result_ids[:_CONFLICT_PREVIEW_CAP]]
        )
        if len(conflict_result_ids) > _CONFLICT_PREVIEW_CAP:
            conflicts.append({
                'table': TransferTable.TEST_RESULTS.value,
                'id': f'...（共 {len(conflict_result_ids)} 条冲突，已截断）',
                'existingName': '',
            })

        warnings = self._build_warnings(rows_by_table)
        stats = dict(manifest.get('stats') or {})
        stats['tableRows'] = {name: len(rows) for name, rows in rows_by_table.items() if rows}

        return {
            'success': True,
            'message': '预检完成',
            'data': {
                'manifest': {
                    'version': manifest.get('version'),
                    'exportedAt': manifest.get('exportedAt'),
                    'serverInfo': manifest.get('serverInfo') or {},
                    'tasks': manifest.get('tasks') or [],
                    'options': manifest.get('options') or {},
                },
                'stats': stats,
                'conflicts': conflicts,
                'warnings': warnings,
            },
        }

    def _build_warnings(self, rows_by_table: Dict[str, List[dict]]) -> List[str]:
        """外部配置引用缺失 warning（外部实体不迁移不重映射）"""
        from task_service.domain.services.data_transfer import collect_external_references
        warnings: List[str] = []
        refs = collect_external_references(rows_by_table)

        existing_case_ids = transfer_repository.fetch_existing_case_ids(refs['test_case_ids'])
        missing_cases = [cid for cid in refs['test_case_ids'] if str(cid) not in existing_case_ids]
        if missing_cases:
            warnings.append(
                f'目标库缺少 {len(missing_cases)} 个测试用例（{missing_cases[:10]}），'
                f'导入后该任务无法重新执行，结果/报告查看不受影响')

        if refs['device_ids']:
            from task_service.infrastructure.acl.device_acl_repository import device_acl_repository
            devices = device_acl_repository.get_device_statuses(
                [int(d) for d in refs['device_ids'] if str(d).isdigit()])
            if devices:
                existing_device_ids = {str(d.get('id')) for d in devices}
                missing_devices = [d for d in refs['device_ids'] if d not in existing_device_ids]
                if missing_devices:
                    warnings.append(
                        f'目标库缺少 {len(missing_devices)} 个设备（{missing_devices[:10]}），'
                        f'重新执行前需补建设备')
        if refs['api_ids']:
            try:
                from task_service.infrastructure.acl.algorithm_acl_repository import algorithm_acl_repository
                api_params = algorithm_acl_repository.list_api_params()
                existing_api_ids = {str(p.get('id') if isinstance(p, dict) else getattr(p, 'id', None))
                                    for p in (api_params or [])}
                missing_apis = [a for a in refs['api_ids'] if a not in existing_api_ids]
                if missing_apis:
                    warnings.append(
                        f'目标库缺少 {len(missing_apis)} 个被测 API 配置（{missing_apis[:10]}），'
                        f'重新执行前需补建')
            except Exception as e:
                log_not_emit('WARNING', _MODULE_NAME,
                             f'校验 API 引用失败（跳过该 warning）: {e}', category='system')
        return warnings

    # ---------- 执行导入（M4 核心） ----------

    def execute_import(self, zip_path: str) -> dict:
        """执行导入：分段提交 + 失败逆序补偿。返回导入统计（含 remappedIds）。"""
        batch_id = uuid.uuid4().hex
        reporter = ImportProgressReporter(batch_id)
        files_tracker: List[tuple] = []
        mappings: Dict[str, Dict[int, int]] = {}
        inserted_pks: Dict[str, List[int]] = {}
        rows_by_table: Dict[str, List[dict]] = {}

        try:
            # ===== 段 0：解析（ZIP 条目已由 zip_io 做路径安全校验，防 zip-slip）=====
            reporter.report(ImportProgressStep.PARSING, '解析导出包')
            manifest = validate_manifest(read_manifest(zip_path))
            rows_by_table = read_db_tables(zip_path)
            export_task_ids = {row.get('id') for row in rows_by_table.get(
                TransferTable.TEST_TASKS.value, []) if row.get('id') is not None}
            rows_by_table[TransferTable.TASK_MERGE_RELATIONS.value] = filter_merge_relations(
                rows_by_table.get(TransferTable.TASK_MERGE_RELATIONS.value, []),
                export_task_ids)

            existing_ids = transfer_repository.fetch_existing_ids()
            plan = plan_task_segment(rows_by_table, existing_ids)
            conflicts_by_table = {name: p.conflicted_old_ids for name, p in plan.tables.items()}
            dims_rows = rows_by_table.get(TransferTable.TEST_RESULT_DIMENSIONS.value) or []
            report_tables_rows = {t.value: rows_by_table.get(t.value) or []
                                  for t in _REPORT_TABLES}
            # plan 覆盖全部 15 表（含经 gRPC 转交的维度/报告段），总行数一次计足
            reporter.set_total_rows(plan.total_rows())

            # ===== 段 1：task_service 7 表（单事务）=====
            reporter.report(ImportProgressStep.WRITING_DB, '开始写入任务数据')

            def _rewrite_fn(table: str, rows: List[dict], task_map: Dict[int, int]) -> List[dict]:
                return rewrite_fk_rows(
                    rows, fk_rules_of(TransferTable(table)), {FkMappingKey.TASKS: task_map})

            mappings, inserted_pks = transfer_repository.import_task_segment(
                {name: p.rows for name, p in plan.tables.items()},
                conflicts_by_table,
                _rewrite_fn,
                progress_fn=lambda table, n: reporter.table_progress(table, n),
            )
            transfer_batch_registry.record(batch_id, 'task_service', inserted_pks)

            # ===== 段 2：维度评分（evaluation_service 单事务）=====
            if dims_rows:
                reporter.table_progress(TransferTable.TEST_RESULT_DIMENSIONS.value,
                                        plan.total_rows(), '正在写入维度评分')
                eval_result = evaluation_transfer_acl_repository.import_dimensions(
                    dims_rows, _remaps_only(mappings['test_results']), batch_id)
                mappings[FkMappingKey.TEST_RESULT_DIMENSIONS.value] = {
                    int(k): v for k, v in (eval_result.get('id_mapping') or {}).items()}

            # ===== 段 3：报告 7 表（report_service 单事务）=====
            if any(report_tables_rows.values()):
                reporter.table_progress(TransferTable.TEST_REPORTS.value,
                                        plan.total_rows(), '正在写入报告数据')
                report_result = report_transfer_acl_repository.import_reports(
                    report_tables_rows, _remaps_only(mappings['tasks']), batch_id)
                mappings[FkMappingKey.TEST_REPORTS.value] = {
                    int(k): v for k, v in (report_result.get('id_mapping') or {}).items()}

            # ===== 段 4：文件回写存储（最后动文件；失败走补偿）=====
            reporter.report(ImportProgressStep.EXTRACTING_FILES, '回写结果与参考参数文件')
            write_case_result_files(
                case_results_entries(zip_path), mappings['tasks'], files_tracker)
            write_ref_param_files(ref_params_entries(zip_path), files_tracker)
            write_audio_files(audios_entries(zip_path), files_tracker)

            # ===== 段 5：更新 result_data_path（独立小事务）=====
            reporter.report(ImportProgressStep.UPDATING_PATHS, '更新文件路径')
            self._update_result_paths(rows_by_table, mappings, files_tracker, reporter)

            # ===== 完成 =====
            stats = self._build_stats(plan, dims_rows, report_tables_rows,
                                      files_tracker, mappings)
            reporter.report(ImportProgressStep.DONE,
                            f"导入完成：任务 {stats['importedTasks']} 个，"
                            f"结果 {stats['importedResults']} 条", '')
            self._publish_imported_event(mappings, batch_id, stats)
            log_not_emit('INFO', _MODULE_NAME,
                         f'导入完成 batch={batch_id} stats={stats}', category='system')
            transfer_batch_registry.delete(batch_id)
            return {'success': True, 'message': '导入成功', 'data': stats}

        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'导入失败 batch={batch_id}: {e}', category='system', exc_info=True)
            compensation_errors = self._compensate(files_tracker, inserted_pks, batch_id)
            # 远端段"已提交但批次登记失败"：远端存在无登记孤儿行，自动补偿够不着，
            # 必须并入人工介入清单（规格架构决策 3"不得静默"）
            if _COMMITTED_WITHOUT_REGISTRY_MARKER in str(e):
                compensation_errors.append(
                    '远端段已提交但批次登记失败，远端存在无登记孤儿行需人工清理'
                    f'（batch_id={batch_id}）')
            message = f'导入失败: {e}'
            if compensation_errors:
                message += ('；补偿回滚部分失败，需人工介入核查'
                            f'（batch_id={batch_id}，登记保留 7 天）: '
                            + '；'.join(compensation_errors))
            reporter.report(ImportProgressStep.ERROR, message)
            return {
                'success': False,
                'message': message,
                'code': 500,
                'data': {'batch_id': batch_id,
                         'compensation_errors': compensation_errors},
            }

    # ---------- 补偿（逆序：文件 → 报表 → 维度 → task 段）----------

    def _compensate(self, files_tracker: List[tuple],
                    inserted_pks: Dict[str, List[int]],
                    batch_id: str) -> List[str]:
        """按逆序回滚已提交段。返回补偿失败清单（非空即需人工介入）。

        问题 1 修复：远端段回滚**无条件**调用——批次未登记时远端本就 no-op
        返回 success，不存在"响应丢失/登记失败导致跳过补偿"的静默窗口；
        仅当全部回滚成功才销毁批次登记。
        问题 2 修复：task 段直接用编排方内存中的 inserted_pks 回滚，
        不依赖 Redis 读登记（登记恰可能因本次故障不可用）。
        """
        errors: List[str] = []
        if files_tracker:
            cleanup_failures = delete_written_files(files_tracker)
            errors.extend(f'文件清理失败: {f}' for f in cleanup_failures)
        # 远端段：无条件回滚（未登记 = no-op）
        try:
            report_transfer_acl_repository.rollback_report_import(batch_id)
        except Exception as e:
            errors.append(f'报表段回滚失败: {e}')
        try:
            evaluation_transfer_acl_repository.rollback_dimension_import(batch_id)
        except Exception as e:
            errors.append(f'维度评分段回滚失败: {e}')
        # task 段：内存主键回滚（非空 ⇔ 该段已提交）
        if any(inserted_pks.values()):
            try:
                transfer_repository.rollback_task_segment(inserted_pks)
                transfer_batch_registry.remove_service(batch_id, 'task_service')
            except Exception as e:
                errors.append(f'任务段回滚失败: {e}')
        if not errors:
            transfer_batch_registry.delete(batch_id)
        return errors

    # ---------- 批次回滚（RollbackImport RPC / 人工介入兜底入口）----------

    def rollback_import(self, batch_id: str) -> dict:
        """按批次登记回滚全部服务段（不区分提交段，按登记数据删除）。"""
        if not batch_id:
            return {'success': False, 'message': 'batch_id 不能为空', 'code': 400}
        errors: List[str] = []
        deleted: Dict[str, dict] = {}

        task_pks = transfer_batch_registry.load_service(batch_id, 'task_service')
        if task_pks:
            try:
                deleted['task_service'] = transfer_repository.rollback_task_segment(task_pks)
            except Exception as e:
                errors.append(f'task_service 回滚失败: {e}')
        try:
            deleted['evaluation_service'] = evaluation_transfer_acl_repository.rollback_dimension_import(batch_id)
        except Exception as e:
            errors.append(f'evaluation_service 回滚失败: {e}')
        try:
            deleted['report_service'] = report_transfer_acl_repository.rollback_report_import(batch_id)
        except Exception as e:
            errors.append(f'report_service 回滚失败: {e}')

        if errors:
            return {'success': False,
                    'message': f'批次回滚部分失败，需人工介入（batch_id={batch_id}）: '
                               + '；'.join(errors),
                    'code': 500,
                    'data': {'batch_id': batch_id, 'deleted': deleted}}
        transfer_batch_registry.delete(batch_id)
        return {'success': True, 'message': '批次回滚完成',
                'data': {'batch_id': batch_id, 'deleted': deleted}}

    # ---------- 内部工具 ----------

    def _update_result_paths(self, rows_by_table: Dict[str, List[dict]],
                             mappings: Dict[str, Dict[int, int]],
                             files_tracker: List[tuple],
                             reporter: ImportProgressReporter) -> None:
        """把 task_id 被重映射的结果行 result_data_path 更新为实际回写路径"""
        results_rows = rows_by_table.get(TransferTable.TEST_RESULTS.value) or []
        tasks_mapping = mappings.get('tasks') or {}
        results_mapping = mappings.get('test_results') or {}
        written_paths = {key: stored for key, stored in files_tracker}

        changes: List[tuple] = []
        for row in results_rows:
            old_path = row.get('result_data_path')
            old_task_id = row.get('task_id')
            old_result_id = row.get('id')
            if not old_path or old_task_id is None or old_result_id is None:
                continue
            new_task_id = tasks_mapping.get(old_task_id, old_task_id)
            if new_task_id == old_task_id:
                continue  # 任务 ID 未变，key 不变
            new_result_id = results_mapping.get(old_result_id, old_result_id)
            _category, key = parse_storage_path(old_path)
            if not key:
                continue
            new_key = remap_task_id_in_key(key, new_task_id)
            stored_path = written_paths.get(new_key)
            if not stored_path:
                continue  # 该结果文件未在包内，路径保持原值
            changes.append((new_result_id, stored_path))
        transfer_repository.update_result_data_paths(changes)

    @staticmethod
    def _build_stats(plan, dims_rows: List[dict], report_tables_rows: Dict[str, List[dict]],
                     files_tracker: List[tuple],
                     mappings: Dict[str, Dict[int, int]]) -> dict:
        tasks_mapping = mappings.get('tasks') or {}
        results_mapping = mappings.get('test_results') or {}

        def _remapped(mapping: Dict[int, int]) -> dict:
            return {str(k): v for k, v in mapping.items() if k != v}

        remapped_ids = {
            'tasks': _remapped(tasks_mapping),
            'test_results': _remapped(results_mapping),
        }
        dims_mapping = mappings.get(FkMappingKey.TEST_RESULT_DIMENSIONS.value) or {}
        reports_mapping = mappings.get(FkMappingKey.TEST_REPORTS.value) or {}
        if dims_mapping:
            remapped_ids['test_result_dimensions'] = _remapped(dims_mapping)
        if reports_mapping:
            remapped_ids['test_reports'] = _remapped(reports_mapping)
        # 仅冲突时返回 remappedIds
        if not any(remapped_ids.values()):
            remapped_ids = {}

        return {
            'importedTasks': plan.get(TransferTable.TEST_TASKS).row_count,
            'importedResults': plan.get(TransferTable.TEST_RESULTS).row_count,
            'importedDimensions': len(dims_rows),
            'importedReports': len(report_tables_rows.get(TransferTable.TEST_REPORTS.value) or []),
            'importedFiles': len(files_tracker),
            'remappedIds': remapped_ids,
        }

    @staticmethod
    def _publish_imported_event(mappings, batch_id: str, stats: dict) -> None:
        """导入成功发布 TASK_EVENTS / task_imported 事件"""
        new_task_ids = sorted(mappings.get('tasks', {}).values())
        payload = {'task_ids': new_task_ids, 'batch_id': batch_id,
                   'imported_tasks': stats.get('importedTasks', 0),
                   'imported_results': stats.get('importedResults', 0)}
        EventBus().publish(EventChannel.TASK_EVENTS, EventType.TASK_IMPORTED, payload)


data_transfer_import_service = DataTransferImportService()
