# -*- coding: utf-8 -*-
"""任务数据导入导出领域服务（task_service 域，纯函数层）"""
from task_service.domain.services.data_transfer.id_remapper import (
    ImportPlan,
    TablePlan,
    apply_result_file_key_remapping,
    build_table_mapping,
    collect_external_references,
    filter_merge_relations,
    plan_task_segment,
    rewrite_fk_rows,
)
from task_service.domain.services.data_transfer.incremental import (
    build_dimension_id_mapping,
    case_set_hash,
    package_report_ids,
    translate_dimension_rows,
    translate_report_tables,
    validate_incremental_package,
)
from task_service.domain.services.data_transfer.manifest import (
    ManifestError,
    build_incremental_manifest,
    build_manifest,
    validate_manifest,
)
from task_service.domain.services.data_transfer.raw_objects import (
    RawObjectRef,
    collect_raw_object_refs,
    raw_pointer_columns,
    strip_raw_pointer_columns,
)
from task_service.domain.services.data_transfer.source_map import (
    dedupe_entries,
    plan_source_map_entries,
)

__all__ = [
    'ImportPlan',
    'TablePlan',
    'apply_result_file_key_remapping',
    'build_dimension_id_mapping',
    'build_incremental_manifest',
    'build_table_mapping',
    'build_manifest',
    'case_set_hash',
    'collect_external_references',
    'dedupe_entries',
    'filter_merge_relations',
    'ManifestError',
    'package_report_ids',
    'plan_source_map_entries',
    'plan_task_segment',
    'RawObjectRef',
    'raw_pointer_columns',
    'collect_raw_object_refs',
    'rewrite_fk_rows',
    'strip_raw_pointer_columns',
    'translate_dimension_rows',
    'translate_report_tables',
    'validate_incremental_package',
    'validate_manifest',
]
