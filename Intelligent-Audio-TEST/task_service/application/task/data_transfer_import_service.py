# -*- coding: utf-8 -*-
"""任务数据导入应用服务（M4 导入执行编排）

分段提交 + 补偿回滚（跨服务无单事务，架构红线禁止直写他服务表）：
  1. task_service 单事务写入自身 8 表（ID 重映射 + 外键改写 + 批次主键登记）
  2. gRPC evaluation_service.ImportDimensions（单事务 + 自登记批次）
  3. gRPC report_service.ImportReports（单事务 + 自登记批次）
  4. 文件经存储抽象回写（放最后：DB 全部成功后才动文件）
  5. 更新 result_data_path（task_id 重映射的行，独立小事务）
  6. source_map 登记（INT-1760：A 原始 id → 本地 id，一次事务 upsert；
     失败返回 partial 不补偿——数据是对的，快照留批次登记供重放）

任一段失败：按逆序补偿（清文件 → 报表回滚 → 维度回滚 → task 段回滚）；
补偿自身失败必须显式报错要求人工介入（批次登记保留 TTL 7 天），不得静默。
"""
import uuid
from typing import Dict, List, Optional, Tuple

from shared.constants.data_transfer import (
    CASE_CONSISTENCY_FAILED_CODE,
    CASE_CONSISTENCY_LIST_CAP,
    CASE_CONSISTENCY_REJECT_MESSAGE,
    DEFAULT_DOC_VERSION_SCOPE,
    DEFAULT_TRANSFER_INTENT,
    FkMappingKey,
    ImportProgressStep,
    INCREMENTAL_FINGERPRINT_CODE,
    INCREMENTAL_ID_MISSING_CODE,
    INCREMENTAL_INVALID_PACKAGE_CODE,
    INCREMENTAL_REPORT_TABLES,
    INCREMENTAL_TASK_FORBIDDEN_CODE,
    INCREMENTAL_TASK_NOT_FOUND_CODE,
    REPORT_STUDIO_TABLES,
    RESTORE_SKIP_CONSISTENCY_WARNING,
    TransferIntent,
    TransferTable,
    fk_rules_of,
)
from shared.utils.data_transfer import conflicted_ids as _conflicted_ids
from shared.utils.data_transfer import parse_storage_path, remap_task_id_in_key
from shared.utils.data_transfer_batch import transfer_batch_registry
from shared.utils.log_handler import log_not_emit
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
from task_service.domain.services.data_transfer import (
    build_dimension_id_mapping,
    case_set_hash,
    filter_merge_relations,
    package_report_ids,
    plan_source_map_entries,
    plan_task_segment,
    rewrite_fk_rows,
    validate_incremental_package,
)
from task_service.infrastructure.acl.evaluation_transfer_acl import (
    TransferMergeError,
    evaluation_transfer_acl_repository,
)
from task_service.infrastructure.acl.report_transfer_acl import (
    ReportPackageImportError,
    TransferReplaceError,
    report_transfer_acl_repository,
)
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
    read_dimensions_snapshot,
    read_manifest,
    ref_params_entries,
)
from task_service.application.task.import_progress_reporter import ImportProgressReporter
from task_service.domain.services.data_transfer.manifest import (
    ManifestError,
    validate_manifest,
    validate_report_package_manifest,
)

_MODULE_NAME = 'data_transfer_import'

_REPORT_TABLES = (TransferTable.TEST_REPORTS, TransferTable.REPORT_SUMMARIES,
                  TransferTable.REPORT_SUMMARY_META, TransferTable.REPORT_RAW_DATA,
                  TransferTable.REPORT_CASES, TransferTable.REPORT_METRIC_STATS,
                  TransferTable.REPORT_COMPARISON_MATRIX)

_CONFLICT_PREVIEW_CAP = 500

# 远端应用服务在"DB 已提交但批次登记失败"时返回的专用错误前缀（审计问题 1③）：
# 编排层据此把该段并入人工介入清单，防止孤儿数据静默残留
_COMMITTED_WITHOUT_REGISTRY_MARKER = '已提交但批次登记失败'

# source_map 批次登记里的服务字段名（与 tables 主键登记同一 HASH 字段，INT-1760）
_SOURCE_MAP_OWNER = 'task_service'


class SourceMapRegistrationError(RuntimeError):
    """source_map 登记失败（数据段已全部提交）

    按 D0 A3 第 3 条：远端/本地数据都是对的，**不回滚**，返回 partial 状态
    （code 500 + sourceMapPending），映射快照已写进批次登记供重放。
    """

    def __init__(self, message: str, entries: List[dict], snapshot_saved: bool):
        super().__init__(message)
        self.entries = entries or []
        self.snapshot_saved = snapshot_saved


class IncrementalValidationError(ValueError):
    """增量导入前置校验失败（携带 HTTP 语义业务码与回执明细，未写任何数据）"""

    def __init__(self, message: str, code: int = 400, data: Optional[dict] = None):
        super().__init__(message)
        self.code = int(code or 400)
        self.data = data or {}


def _remaps_only(mapping: Dict[int, int]) -> Dict[int, int]:
    """只保留真正的重映射条目（远端 rewrite 语义 mapping.get(old, old) 下，
    映射到自身的条目冗余，剔除以减小 gRPC payload）"""
    return {k: v for k, v in (mapping or {}).items() if k != v}


class DataTransferImportService:
    """导入编排（预检 / 执行 / 批次回滚）"""

    # ---------- 预检（M3） ----------

    def preview_import(self, zip_path: str, options: Optional[dict] = None) -> dict:
        """解析 ZIP 并返回预检结果（manifest 摘要 + stats + conflicts + warnings
        + caseConsistency）。

        用例一致性在预检阶段**只报告不阻断**（D0 裁定 A10-3）：前端据
        `data.caseConsistency.complete` 决定是否允许执行导入。
        """
        try:
            required, intent = self._resolve_policy(options)
        except ValueError as e:
            return {'success': False, 'message': str(e), 'code': 400, 'data': None}
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

        warnings = self._build_warnings(rows_by_table, required)
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
                'intent': intent,
                'caseConsistency': self._case_consistency(rows_by_table, required),
                'warnings': warnings,
            },
        }

    @staticmethod
    def _resolve_policy(options: Optional[dict]) -> Tuple[bool, str]:
        """解析用例一致性策略 → (required, intent)（D0 裁定 A10-1/2）

        - 全局 `DATA_TRANSFER_CASE_CONSISTENCY_REQUIRED` 是总闸；
        - 请求级 `require_case_consistency` **只能放宽到 false**，全局 false 时
          传 true 不得反向收紧（防前端提权）；
        - `intent='restore'`（历史结果查看/备份恢复）默认不校验，显式传
          `require_case_consistency=true` 时仍按总闸校验。

        Raises: ValueError 当 intent 非法（调用方映射 400）。
        """
        from shared.infrastructure.config import BaseConfig
        opts = options or {}
        intent = str(opts.get('intent') or DEFAULT_TRANSFER_INTENT).strip().lower()
        if intent not in {i.value for i in TransferIntent}:
            raise ValueError(f'不支持的导入意图 intent={intent}（仅支持 migrate/restore）')
        required = bool(BaseConfig.DATA_TRANSFER_CASE_CONSISTENCY_REQUIRED)
        request_flag = opts.get('require_case_consistency')
        if request_flag is False:
            required = False
        elif request_flag is None and intent == TransferIntent.RESTORE.value:
            required = False
        return required, intent

    def _case_consistency(self, rows_by_table: Dict[str, List[dict]],
                          required: bool) -> dict:
        """用例一致性校验回执（预检与执行共用，INT-1759）

        引用来源只有 `task_case_relations.test_case_id`（`collect_external_references`），
        结果/报告行不带用例引用，不产生误报。

        `missingCaseIds` = 目标库缺失 ∪ 已软删 ∪ 私有且非 owner（不可用即缺失），
        另给 `invisibleCaseIds` 供前端区分"真的没有"与"有但无权用"。
        """
        from task_service.domain.services.data_transfer import collect_external_references
        refs = collect_external_references(rows_by_table)
        availability = transfer_repository.fetch_case_availability(refs['test_case_ids'])
        unavailable = sorted(availability['missing'] | availability['invisible'])
        return {
            'required': required,
            'complete': not unavailable,
            'missingCaseIds': unavailable[:CASE_CONSISTENCY_LIST_CAP],
            'invisibleCaseIds': sorted(availability['invisible'])[:CASE_CONSISTENCY_LIST_CAP],
            'missingCount': len(unavailable),
            'truncated': len(unavailable) > CASE_CONSISTENCY_LIST_CAP,
        }

    def _build_warnings(self, rows_by_table: Dict[str, List[dict]],
                        required: bool) -> List[str]:
        """外部配置引用缺失 warning（外部实体不迁移不重映射）

        「未校验用例一致性」提示按解析后的 `required` 判定（INT-1870）：restore
        显式要求校验并已执行时不得再写该文案，避免给出与实际校验状态相反的结论。
        """
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
        if not required:
            warnings.append(RESTORE_SKIP_CONSISTENCY_WARNING)
        return warnings

    # ---------- 执行导入（M4 核心） ----------

    def execute_import(self, zip_path: str, options: Optional[dict] = None) -> dict:
        """执行导入：分段提交 + 失败逆序补偿。返回导入统计（含 remappedIds）。

        用例一致性硬校验在**段 1 任何写库动作之前**执行（INT-1759）：
        拒绝时直接返回 422 + 缺失清单，不登记批次、不写 DB、不动文件。
        """
        try:
            required, intent = self._resolve_policy(options)
        except ValueError as e:
            return {'success': False, 'message': str(e), 'code': 400, 'data': None}
        batch_id = uuid.uuid4().hex
        reporter = ImportProgressReporter(batch_id)
        files_tracker: List[tuple] = []
        mappings: Dict[str, Dict[int, int]] = {}
        inserted_pks: Dict[str, List[int]] = {}
        rows_by_table: Dict[str, List[dict]] = {}
        source_map_inserted: List[dict] = []

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

            # ===== 用例一致性硬校验（INT-1759：早于批次登记与段 1 写入）=====
            if required:
                consistency = self._case_consistency(rows_by_table, required=True)
                if not consistency['complete']:
                    sample = '、'.join(consistency['missingCaseIds'][:10])
                    more = '…' if consistency['missingCount'] > len(consistency['missingCaseIds']) else ''
                    message = (CASE_CONSISTENCY_REJECT_MESSAGE.format(
                        count=consistency['missingCount']) + f'：{sample}{more}')
                    log_not_emit('WARNING', _MODULE_NAME,
                                 f'{message} batch={batch_id}', category='system')
                    reporter.report(ImportProgressStep.ERROR, message)
                    return {
                        'success': False,
                        'message': message,
                        'code': CASE_CONSISTENCY_FAILED_CODE,
                        'data': dict(consistency, intent=intent),
                    }

            existing_ids = transfer_repository.fetch_existing_ids()
            plan = plan_task_segment(rows_by_table, existing_ids)
            conflicts_by_table = {name: p.conflicted_old_ids for name, p in plan.tables.items()}
            dims_rows = rows_by_table.get(TransferTable.TEST_RESULT_DIMENSIONS.value) or []
            report_tables_rows = {t.value: rows_by_table.get(t.value) or []
                                  for t in _REPORT_TABLES}
            # plan 覆盖全部 16 表（含经 gRPC 转交的维度/报告段），总行数一次计足
            reporter.set_total_rows(plan.total_rows())

            # ===== 段 1：task_service 8 表（单事务，含容器关系表）=====
            reporter.report(ImportProgressStep.WRITING_DB, '开始写入任务数据')

            def _rewrite_fn(table: str, rows: List[dict],
                           mappings: Dict[str, Dict[int, int]]) -> List[dict]:
                return rewrite_fk_rows(
                    rows, fk_rules_of(TransferTable(table)), mappings)

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

            # ===== 段 6：source_map 登记（INT-1760 / D0 A3：编排层唯一写入方，
            #      放在全部数据段成功之后的一次事务 upsert，失败走 partial 不补偿）=====
            source_map_inserted = self._register_source_maps(
                manifest, rows_by_table, mappings, batch_id)

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

        except SourceMapRegistrationError as e:
            # D0 A3 第 3 条：数据段已全部提交，远端数据是对的 —— **不回滚**，
            # 返回 partial（code 500 + sourceMapPending + batchId），映射快照已
            # 写进批次登记，失败后可人工/脚本重放登记（禁止静默）
            log_not_emit('ERROR', _MODULE_NAME,
                         f'导入完成但 source_map 登记失败 batch={batch_id}: {e}',
                         category='system', exc_info=True)
            message = str(e)
            reporter.report(ImportProgressStep.ERROR, message)
            return {
                'success': False,
                'message': message,
                'code': 500,
                'data': {
                    'partial': True,
                    'sourceMapPending': True,
                    'batchId': batch_id,
                    'entryCount': len(e.entries),
                    'snapshotSaved': e.snapshot_saved,
                    'compensationErrors': [],
                },
            }
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'导入失败 batch={batch_id}: {e}', category='system', exc_info=True)
            compensation_errors = self._compensate(
                files_tracker, inserted_pks, batch_id, source_map_inserted)
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

    # ---------- 增量导入（链路 2，INT-1761 / D0 裁定 A2/A5/A7） ----------

    def import_incremental(self, zip_path: str, options: Optional[dict] = None) -> dict:
        """增量包合并导入：维度覆盖集合并 → 报告原地替换（合并回 A 原任务）。

        与整包导入的差异：
        - 不建任务 / 不写结果 / 不动文件，包内 id 已是 A 原始 id，不做重映射；
        - 只有维度 id 需要翻译（按维度定义链，A2-4）；
        - 失败按逆序补偿（报告段 → 维度段），依赖 D4 的旧值快照恢复原值。

        Returns: 回执统计（含 mergedDimensions / replacedReportId / warnings /
            batchId / rollbackAvailable）；失败时 code 为 HTTP 语义码。
        """
        batch_id = uuid.uuid4().hex
        reporter = ImportProgressReporter(batch_id)
        try:
            return self._run_incremental_import(zip_path, batch_id, reporter)
        except IncrementalValidationError as e:
            # 前置校验失败：未写任何数据，不补偿
            log_not_emit('WARNING', _MODULE_NAME,
                         f'增量导入校验失败 batch={batch_id} code={e.code}: {e}',
                         category='system')
            reporter.report(ImportProgressStep.ERROR, str(e))
            return {'success': False, 'message': str(e), 'code': e.code, 'data': e.data}
        except (TransferMergeError, TransferReplaceError) as e:
            # 远端段已自己回滚（单事务）；补偿仍无条件执行，兜住「远端已提交但
            # 回执丢失」等窗口，并显式区分是否给了业务码
            log_not_emit('ERROR', _MODULE_NAME,
                         f'增量导入失败 batch={batch_id} code={e.code}: {e}',
                         category='system', exc_info=True)
            errors = self._compensate_incremental(batch_id)
            message = str(e)
            if errors:
                message += ('；补偿回滚部分失败，需人工介入核查'
                            f'（batch_id={batch_id}，登记保留 7 天）: ' + '；'.join(errors))
            data = dict(e.data or {})
            data.setdefault('batchId', batch_id)
            data['compensationErrors'] = errors
            reporter.report(ImportProgressStep.ERROR, message)
            return {'success': False, 'message': message, 'code': e.code, 'data': data}
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'增量导入异常 batch={batch_id}: {e}', category='system',
                         exc_info=True)
            errors = self._compensate_incremental(batch_id)
            message = f'增量导入失败: {e}'
            if errors:
                message += ('；补偿回滚部分失败，需人工介入核查'
                            f'（batch_id={batch_id}，登记保留 7 天）: ' + '；'.join(errors))
            reporter.report(ImportProgressStep.ERROR, message)
            return {'success': False, 'message': message, 'code': 500,
                    'data': {'batchId': batch_id, 'compensationErrors': errors}}

    def _run_incremental_import(self, zip_path: str, batch_id: str,
                                reporter: ImportProgressReporter) -> dict:
        """增量导入主体（校验 → 段 1 维度合并 → 段 2 报告替换）。

        Raises: IncrementalValidationError（前置校验）/ TransferMergeError /
            TransferReplaceError（远端段失败），由 import_incremental 统一处置。
        """
        # ===== 段 0：解析与结构校验 =====
        reporter.report(ImportProgressStep.PARSING, '解析增量包')
        manifest = validate_manifest(read_manifest(zip_path))
        rows_by_table = read_db_tables(zip_path)
        structure_errors = validate_incremental_package(manifest, rows_by_table)
        if structure_errors:
            raise IncrementalValidationError('；'.join(structure_errors),
                                             INCREMENTAL_INVALID_PACKAGE_CODE,
                                             {'errors': structure_errors})
        source_task = manifest.get('sourceTask') or {}
        task_id = int(source_task['id'])

        # ===== 定位 A 原任务 + 可见性（A7）=====
        identity = transfer_repository.fetch_task_identity(task_id)
        if identity is None or identity.get('deleted'):
            raise IncrementalValidationError(
                f'源任务不存在或已删除（sourceTaskId={task_id}）',
                INCREMENTAL_TASK_NOT_FOUND_CODE, {'sourceTaskId': task_id})
        from shared.infrastructure.user_context import (
            get_current_user_id, get_current_user_is_admin,
        )
        from task_service.infrastructure.persistence.task_repository import task_repository
        if not task_repository.filter_visible_task_ids(
                [task_id], user_id=get_current_user_id(),
                is_admin=get_current_user_is_admin()):
            raise IncrementalValidationError(
                f'无权写入该任务（sourceTaskId={task_id}）',
                INCREMENTAL_TASK_FORBIDDEN_CODE, {'sourceTaskId': task_id})

        warnings: List[str] = []
        # ===== 指纹校验（A7）：用例集哈希不符即拒绝；任务名只做二次提示 =====
        expected_hash = str(source_task.get('caseSetHash') or '')
        actual_hash = case_set_hash(transfer_repository.fetch_task_case_ids(task_id))
        if expected_hash and expected_hash != actual_hash:
            raise IncrementalValidationError(
                f'源任务与增量包不匹配，拒绝合并（用例集指纹不符，sourceTaskId={task_id}）',
                INCREMENTAL_FINGERPRINT_CODE,
                {'expected': expected_hash, 'actual': actual_hash,
                 'sourceTaskId': task_id})
        package_name = str(source_task.get('name') or '')
        if package_name and identity.get('name') and package_name != identity.get('name'):
            warnings.append(
                f'任务名与包内不一致（A 库 {identity.get("name")!r} / 包内 {package_name!r}），'
                '按任务 id 合并')

        dim_rows = [row for row in (rows_by_table.get(
            TransferTable.TEST_RESULT_DIMENSIONS.value) or []) if isinstance(row, dict)]
        report_tables = {table.value: rows_by_table.get(table.value) or []
                         for table in INCREMENTAL_REPORT_TABLES}

        # ===== A 侧反向 id 校验（A2-3）：禁止把 B 的本地 id 当 A id 写入 =====
        package_result_ids = sorted({int(row['test_result_id']) for row in dim_rows
                                     if row.get('test_result_id') is not None})
        if package_result_ids:
            existing_ids = transfer_repository.fetch_existing_result_ids(package_result_ids)
            missing_ids = [rid for rid in package_result_ids if rid not in existing_ids]
            if missing_ids:
                raise IncrementalValidationError(
                    f'包内 {len(missing_ids)} 个 test_result_id 在目标库不存在: '
                    f'{missing_ids[:20]}', INCREMENTAL_ID_MISSING_CODE,
                    {'missingIds': missing_ids, 'sourceTaskId': task_id})

        # ===== 维度 id 翻译（A2-4）：按 (name, 父链, task_type_code) 映射到 A =====
        dimension_id_mapping: Dict[int, int] = {}
        if dim_rows:
            package_defs = read_dimensions_snapshot(zip_path)
            if not package_defs:
                raise IncrementalValidationError(
                    '增量包缺少 meta/dimensions.json（维度定义快照），无法翻译维度 id',
                    INCREMENTAL_INVALID_PACKAGE_CODE, {'sourceTaskId': task_id})
            target_defs = evaluation_transfer_acl_repository.list_dimension_defs()
            dimension_id_mapping, unmatched, mapping_warnings = build_dimension_id_mapping(
                package_defs, target_defs)
            warnings.extend(mapping_warnings)
            if unmatched:
                warnings.append(
                    f'目标库匹配不到 {len(unmatched)} 个维度定义，相关维度行已跳过: '
                    f'{unmatched[:20]}')
            # **本地过滤**：未命中的维度行绝不交给远端——远端在映射为空时按
            # 「包内已是 A 维度 id」处理，直写 B 的 dimension_id 会污染 A 的评分
            kept_rows = [row for row in dim_rows
                         if int(row['dimension_id']) in dimension_id_mapping]
            if len(kept_rows) != len(dim_rows):
                warnings.append(
                    f'跳过 {len(dim_rows) - len(kept_rows)} 行未命中维度映射的评分'
                    f'（共 {len(dim_rows)} 行）')
            dim_rows = kept_rows

        # ===== 段 1：维度覆盖集合并（evaluation_service 单事务 + 旧值快照）=====
        dimension_stats: Dict = {}
        if dim_rows:
            reporter.report(ImportProgressStep.MERGING_DIMENSIONS, '合并维度评分')
            dimension_stats = evaluation_transfer_acl_repository.merge_dimensions(
                dim_rows, dimension_id_mapping, batch_id)
            # 批次登记（7 天 TTL）：D4 快照已按 batch_id 落各自库，这里只保留可回滚指针
            transfer_batch_registry.record(batch_id, 'evaluation_service', {})

        # ===== 段 2：报告原地替换（report_service 单事务 + 旧值快照）=====
        report_stats: Dict = {}
        if any(report_tables.values()):
            reporter.report(ImportProgressStep.REPLACING_REPORTS, '替换平台报告')
            package_ids = package_report_ids(report_tables)
            # 只有「唯一且已翻译为 A 原始 id」的包内报告才当目标；多份 / 无 id 时
            # 交给远端按「任务下最新 task 型报告」或新建定位（A5-2）
            target_report_id = package_ids[0] if len(package_ids) == 1 else None
            report_stats = report_transfer_acl_repository.replace_reports(
                report_tables, task_id, target_report_id, batch_id)
            transfer_batch_registry.record(batch_id, 'report_service', {})
            warnings.extend(report_stats.get('warnings') or [])

        skipped_dimensions = sorted(set(dimension_stats.get('skipped_dimensions') or []))
        if skipped_dimensions:
            warnings.append(
                f'远端跳过 {len(skipped_dimensions)} 个未命中映射的维度: '
                f'{skipped_dimensions[:20]}')

        stats = {
            'taskId': task_id,
            'mergedDimensions': int(dimension_stats.get('imported') or 0),
            'deletedDimensions': int(dimension_stats.get('deleted') or 0),
            'skippedDimensions': skipped_dimensions,
            'insertedReports': len(report_stats.get('inserted_report_ids') or []),
            'replacedReportId': report_stats.get('report_id'),
            'targetResolvedBy': report_stats.get('target_resolved_by'),
            'warnings': warnings,
            'batchId': batch_id,
            # 合并段有快照即可回滚（批次登记保留 7 天）
            'rollbackAvailable': bool(dimension_stats or report_stats),
        }
        reporter.report(ImportProgressStep.DONE,
                        f"增量回导完成：维度 {stats['mergedDimensions']} 行，"
                        f"报告 {stats['insertedReports']} 份", '')
        self._publish_incremental_event(task_id, batch_id, stats)
        log_not_emit('INFO', _MODULE_NAME,
                     f'增量导入完成 batch={batch_id} stats={stats}', category='system')
        return {'success': True, 'message': '增量回导完成', 'data': stats}

    def _compensate_incremental(self, batch_id: str) -> List[str]:
        """增量导入失败补偿（逆序：报告段 → 维度段）。返回补偿失败清单。

        两个回滚 RPC 在「该段未提交」时远端按 no-op 返回 success，故无条件调用，
        不依赖本地对「提交了几段」的判断（与整包补偿同口径）。
        全部成功才销毁批次登记；失败时登记保留 7 天供人工回滚。
        """
        errors: List[str] = []
        try:
            report_transfer_acl_repository.rollback_report_replacement(batch_id)
            transfer_batch_registry.remove_service(batch_id, 'report_service')
        except Exception as e:
            errors.append(f'报告替换段回滚失败: {e}')
        try:
            evaluation_transfer_acl_repository.rollback_dimension_merge(batch_id)
            transfer_batch_registry.remove_service(batch_id, 'evaluation_service')
        except Exception as e:
            errors.append(f'维度合并段回滚失败: {e}')
        if not errors:
            transfer_batch_registry.delete(batch_id)
        return errors

    @staticmethod
    def _publish_incremental_event(task_id: int, batch_id: str, stats: dict) -> None:
        """增量回导成功发布 TASK_EVENTS / task_imported（mode=incremental 区分链路）"""
        payload = {'task_ids': [int(task_id)], 'batch_id': batch_id,
                   'mode': 'incremental',
                   'merged_dimensions': stats.get('mergedDimensions', 0),
                   'replaced_report_id': stats.get('replacedReportId')}
        EventBus().publish(EventChannel.TASK_EVENTS, EventType.TASK_IMPORTED, payload)

    # ---------- 补偿（逆序：文件 → 报表 → 维度 → task 段）----------

    def _compensate(self, files_tracker: List[tuple],
                    inserted_pks: Dict[str, List[int]],
                    batch_id: str,
                    source_map_inserted: List[dict] = None) -> List[str]:
        """按逆序回滚已提交段。返回补偿失败清单（非空即需人工介入）。

        问题 1 修复：远端段回滚**无条件**调用——批次未登记时远端本就 no-op
        返回 success，不存在"响应丢失/登记失败导致跳过补偿"的静默窗口；
        仅当全部回滚成功才销毁批次登记。
        问题 2 修复：task 段直接用编排方内存中的 inserted_pks 回滚，
        不依赖 Redis 读登记（登记恰可能因本次故障不可用）。
        INT-1760：source_map 只回删**本批次新增**的条目（覆盖的旧行无快照，
        删掉等于丢历史映射），避免孤儿映射。
        """
        errors: List[str] = []
        if source_map_inserted:
            try:
                transfer_repository.delete_source_maps(source_map_inserted)
            except Exception as e:
                errors.append(f'source_map 回删失败: {e}')
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
        # INT-1760：映射按批次快照回删（任务行删掉后映射即孤儿）
        source_map_entries = transfer_batch_registry.load_source_map(
            batch_id, _SOURCE_MAP_OWNER)
        if source_map_entries:
            try:
                deleted['source_map'] = transfer_repository.delete_source_maps(
                    source_map_entries)
            except Exception as e:
                errors.append(f'source_map 回滚失败: {e}')
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

    def _register_source_maps(self, manifest: dict,
                              rows_by_table: Dict[str, List[dict]],
                              mappings: Dict[str, Dict[int, int]],
                              batch_id: str) -> List[dict]:
        """登记 A 原始 id → 本地 id 映射（INT-1760 / D0 A3）。

        时序：全部数据段成功后一次事务 upsert；不在各子步骤里分散登记。
        先写 Redis 快照再写库——登记失败时快照是重放的唯一依据。
        Returns: 本批次**新增**的条目（补偿只回删这些；覆盖的旧行不动）。
        Raises: SourceMapRegistrationError（编排层转 partial，不补偿）。
        """
        server_info = manifest.get('serverInfo') or {}
        source_server = str(server_info.get('source') or '')
        entries, warnings = plan_source_map_entries(source_server, rows_by_table, mappings)
        for warning in warnings:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'source_map 跳行 batch={batch_id}: {warning}', category='system')
        if not entries:
            return []

        snapshot_saved = True
        try:
            transfer_batch_registry.record_source_map(batch_id, _SOURCE_MAP_OWNER, entries)
        except Exception as e:
            snapshot_saved = False
            log_not_emit('ERROR', _MODULE_NAME,
                         'source_map 快照写入批次登记失败 '
                         f'batch={batch_id}（DB 登记继续，人工回滚将缺少快照）: {e}',
                         category='system', exc_info=True)
        try:
            result = transfer_repository.upsert_source_maps(entries)
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'source_map 登记失败 batch={batch_id} entries={len(entries)}: {e}',
                         category='system', exc_info=True)
            raise SourceMapRegistrationError(
                f'导入数据已提交，但 source_map 登记失败（{len(entries)} 条映射待重放，'
                f'batch_id={batch_id}）: {e}', entries, snapshot_saved) from e
        log_not_emit('INFO', _MODULE_NAME,
                     f'source_map 登记完成 batch={batch_id} '
                     f'inserted={result["insertedCount"]} updated={result["updatedCount"]}',
                     category='system')
        return result['inserted']

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
            new_result_id = results_mapping.get(old_result_id, old_result_id)
            _category, key = parse_storage_path(old_path)
            if not key:
                continue
            key_head = key.split('/', 1)[0]
            # INT-656：cherry-pick 容器导出内联——内联结果行 task_id 已重写为引用它的
            # 容器任务，存储 key 首段仍是源任务 id；文件按容器路径回写，即使任务 id
            # 未重映射（fresh 导入）也须把 result_data_path 更新到实际落盘位置
            if key_head.isdigit() and str(old_task_id) != key_head:
                new_key = remap_task_id_in_key(key, new_task_id)
                stored_path = written_paths.get(new_key)
                if not stored_path:
                    continue
                changes.append((new_result_id, stored_path))
                continue
            if new_task_id == old_task_id:
                continue  # 任务 ID 未变，key 不变
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

    # ==================== 报告包导入（INT-1764 D6：链路 3a + 3b/3c） ====================

    def import_report_package(self, zip_path: str,
                              options: Optional[dict] = None) -> dict:
        """导入报告包：定位 A 原任务 → report_service 原地替换 + Studio 拓扑序落库。

        Returns:
            {'success', 'message', 'data': 回执, 'code'}；失败码同 D0 §5.4 口径
            （400 包非法 / 403 无权写入 / 404 原任务不存在 / 409 报告冲突 / 500 补偿失败）。
        """
        options = options or {}
        try:
            manifest = read_manifest(zip_path)
        except ValueError as e:
            return {'success': False, 'code': 400, 'message': str(e)}
        try:
            manifest = validate_report_package_manifest(manifest)
        except ManifestError as e:
            return {'success': False, 'code': 400, 'message': str(e)}

        source_task_id = int(manifest['sourceTask']['id'])
        scope = (manifest.get('options') or {}).get('docVersionScope') \
            or DEFAULT_DOC_VERSION_SCOPE

        # 包内报告行必须属于同一任务（与 manifest 的 sourceTask.localTaskId 对齐）
        try:
            rows_by_table = read_db_tables(zip_path)
        except ValueError as e:
            return {'success': False, 'code': 400, 'message': str(e)}
        package_task_ids = {int(row['task_id'])
                            for row in (rows_by_table.get(TransferTable.TEST_REPORTS.value) or [])
                            if row.get('task_id') is not None}
        if len(package_task_ids) > 1:
            return {'success': False, 'code': 400,
                    'message': f'报告包内含多个任务: {sorted(package_task_ids)}',
                    'data': {'taskIds': sorted(package_task_ids)}}
        local_task_id = (manifest.get('sourceTask') or {}).get('localTaskId')
        if package_task_ids and local_task_id is not None \
                and int(local_task_id) not in package_task_ids:
            return {'success': False, 'code': 400,
                    'message': f'包内报告 task_id {sorted(package_task_ids)} '
                               f'与 manifest.sourceTask.localTaskId {local_task_id} 不一致'}

        # 定位 A 原任务：不存在 / 已软删 → 404；私有且非 owner → 403
        existence = transfer_repository.fetch_task_existence([source_task_id])
        if source_task_id not in existence or existence[source_task_id]:
            return {'success': False, 'code': 404,
                    'message': f'原任务 {source_task_id} 不存在或已删除',
                    'data': {'sourceTaskId': source_task_id}}
        from shared.infrastructure.user_context import (
            get_current_user_id, get_current_user_is_admin)
        from task_service.infrastructure.persistence.task_repository import task_repository
        visible = task_repository.filter_visible_task_ids(
            [source_task_id], user_id=get_current_user_id(),
            is_admin=get_current_user_is_admin())
        if not visible:
            return {'success': False, 'code': 403,
                    'message': f'无权写入任务 {source_task_id}',
                    'data': {'sourceTaskId': source_task_id}}

        batch_id = str(options.get('batch_id') or uuid.uuid4().hex)
        studio_tables = {table: rows_by_table.get(table) or []
                         for table in REPORT_STUDIO_TABLES}
        report_tables = {table.value: rows_by_table.get(table.value) or []
                         for table in _REPORT_TABLES}
        try:
            receipt = report_transfer_acl_repository.import_report_package(
                source_task_id, report_tables, studio_tables, batch_id, scope,
                options.get('target_report_id'))
        except ReportPackageImportError as e:
            return {'success': False, 'code': e.code or 500,
                    'message': str(e), 'data': e.data}
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'报告包导入失败 task={source_task_id}: {e}',
                         category='system', exc_info=True)
            return {'success': False, 'code': 500,
                    'message': f'报告包导入失败: {e}',
                    'data': {'batch_id': batch_id, 'sourceTaskId': source_task_id}}

        log_not_emit('INFO', _MODULE_NAME,
                     f'报告包导入完成 task={source_task_id} report={receipt.get("reportId")} '
                     f'batch={batch_id}', category='system')
        return {'success': True, 'message': '导入成功', 'data': receipt}


data_transfer_import_service = DataTransferImportService()
