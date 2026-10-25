# -*- coding: utf-8 -*-
"""任务数据导入导出（Data Transfer）共享常量

16 张表、外键转换规则、ZIP 包结构、进度步骤的唯一配置来源。
设计依据：《任务数据导入导出功能设计文档》4.1/4.2/4.7.2（V9.7.10）+
V9.7.31 微服务适配规格（INT-25）。

表归属（同一 Postgres 库，但服务边界必须遵守）：
- task_service（8 张）：test_tasks / task_case_relations / task_device_relations /
  task_api_relations / task_tags / task_merge_relations / test_results
  / task_cherry_pick_relations（INT-656：cherry-pick 容器任务导出内联——容器自身
  无 test_results 行，导出需内联所选结果并携带专有关系表，导入侧可重建容器）
- evaluation_service（1 张）：test_result_dimensions
- report_service（7 张）：test_reports / report_summaries / report_summary_meta /
  report_raw_data / report_cases / report_metric_stats / report_comparison_matrix
"""
from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class ManifestVersion(str, Enum):
    """导出包 manifest 版本（version 不符直接拒绝导入，不做跨版本迁移）"""
    V1_0 = '1.0'


SUPPORTED_MANIFEST_VERSIONS = {ManifestVersion.V1_0.value}


class TransferTable(str, Enum):
    """导出包内的 16 张表（值 = 表名 = db/ 目录下的 JSON 文件名）"""
    TEST_TASKS = 'test_tasks'
    TASK_CASE_RELATIONS = 'task_case_relations'
    TASK_DEVICE_RELATIONS = 'task_device_relations'
    TASK_API_RELATIONS = 'task_api_relations'
    TASK_TAGS = 'task_tags'
    TASK_MERGE_RELATIONS = 'task_merge_relations'
    TASK_CHERRY_PICK_RELATIONS = 'task_cherry_pick_relations'
    TEST_RESULTS = 'test_results'
    TEST_RESULT_DIMENSIONS = 'test_result_dimensions'
    TEST_REPORTS = 'test_reports'
    REPORT_SUMMARIES = 'report_summaries'
    REPORT_SUMMARY_META = 'report_summary_meta'
    REPORT_RAW_DATA = 'report_raw_data'
    REPORT_CASES = 'report_cases'
    REPORT_METRIC_STATS = 'report_metric_stats'
    REPORT_COMPARISON_MATRIX = 'report_comparison_matrix'


class TransferOwner(str, Enum):
    """表所属微服务（跨服务读写一律 gRPC + ACL，禁止直连他服务表）"""
    TASK_SERVICE = 'task_service'
    EVALUATION_SERVICE = 'evaluation_service'
    REPORT_SERVICE = 'report_service'


# 表 → 所属服务
TABLE_OWNERS = {
    TransferTable.TEST_TASKS: TransferOwner.TASK_SERVICE,
    TransferTable.TASK_CASE_RELATIONS: TransferOwner.TASK_SERVICE,
    TransferTable.TASK_DEVICE_RELATIONS: TransferOwner.TASK_SERVICE,
    TransferTable.TASK_API_RELATIONS: TransferOwner.TASK_SERVICE,
    TransferTable.TASK_TAGS: TransferOwner.TASK_SERVICE,
    TransferTable.TASK_MERGE_RELATIONS: TransferOwner.TASK_SERVICE,
    TransferTable.TASK_CHERRY_PICK_RELATIONS: TransferOwner.TASK_SERVICE,
    TransferTable.TEST_RESULTS: TransferOwner.TASK_SERVICE,
    TransferTable.TEST_RESULT_DIMENSIONS: TransferOwner.EVALUATION_SERVICE,
    TransferTable.TEST_REPORTS: TransferOwner.REPORT_SERVICE,
    TransferTable.REPORT_SUMMARIES: TransferOwner.REPORT_SERVICE,
    TransferTable.REPORT_SUMMARY_META: TransferOwner.REPORT_SERVICE,
    TransferTable.REPORT_RAW_DATA: TransferOwner.REPORT_SERVICE,
    TransferTable.REPORT_CASES: TransferOwner.REPORT_SERVICE,
    TransferTable.REPORT_METRIC_STATS: TransferOwner.REPORT_SERVICE,
    TransferTable.REPORT_COMPARISON_MATRIX: TransferOwner.REPORT_SERVICE,
}


class FkMappingKey(str, Enum):
    """id_mappings 四类 old→new 主键映射（关联表自增主键不映射）"""
    TASKS = 'tasks'
    TEST_RESULTS = 'test_results'
    TEST_RESULT_DIMENSIONS = 'test_result_dimensions'
    TEST_REPORTS = 'test_reports'


class SourceMapEntity(str, Enum):
    """source_map 登记的实体类型（INT-1760 / D0 A4）

    值与 FkMappingKey 一一对应：登记来源就是导入编排层拿到的四类 old→new
    主键映射。关联表的自增主键不登记（无可翻译语义）。
    """
    TASKS = 'tasks'
    TEST_RESULTS = 'test_results'
    TEST_RESULT_DIMENSIONS = 'test_result_dimensions'
    TEST_REPORTS = 'test_reports'

    @classmethod
    def values(cls) -> frozenset:
        return frozenset(item.value for item in cls)


# source_map 持久化表（归属 task_service；INT-1760 §5.3 / D0 A3）
SOURCE_MAP_TABLE = 'data_transfer_source_maps'
# 失败重放快照在批次登记 HASH 的 task_service 字段内的键名（D0 A3 第 3 条）
SOURCE_MAP_BATCH_FIELD = 'source_map'


@dataclass(frozen=True)
class FkRule:
    """外键转换规则（设计文档 4.7.2）：子表.外键列 ← 引用哪个映射"""
    table: TransferTable
    column: str
    mapping: FkMappingKey


# 18 条外键转换规则 —— 全部规则的唯一配置表，禁止散落硬编码。
# 表达式统一为 mapping.get(old_id, old_id)（无冲突记录映射到自身）。
FK_RULES: Tuple[FkRule, ...] = (
    FkRule(TransferTable.TASK_CASE_RELATIONS, 'task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TASK_DEVICE_RELATIONS, 'task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TASK_API_RELATIONS, 'task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TASK_TAGS, 'task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TASK_MERGE_RELATIONS, 'merged_task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TASK_MERGE_RELATIONS, 'source_task_id', FkMappingKey.TASKS),
    # INT-656：cherry-pick 容器关系三外键（容器任务 / 引用结果 / 溯源来源任务）
    FkRule(TransferTable.TASK_CHERRY_PICK_RELATIONS, 'cherry_pick_task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TASK_CHERRY_PICK_RELATIONS, 'result_id', FkMappingKey.TEST_RESULTS),
    FkRule(TransferTable.TASK_CHERRY_PICK_RELATIONS, 'source_task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TEST_RESULTS, 'task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.TEST_RESULT_DIMENSIONS, 'test_result_id', FkMappingKey.TEST_RESULTS),
    FkRule(TransferTable.TEST_REPORTS, 'task_id', FkMappingKey.TASKS),
    FkRule(TransferTable.REPORT_SUMMARIES, 'report_id', FkMappingKey.TEST_REPORTS),
    FkRule(TransferTable.REPORT_SUMMARY_META, 'report_id', FkMappingKey.TEST_REPORTS),
    FkRule(TransferTable.REPORT_RAW_DATA, 'report_id', FkMappingKey.TEST_REPORTS),
    FkRule(TransferTable.REPORT_CASES, 'report_id', FkMappingKey.TEST_REPORTS),
    FkRule(TransferTable.REPORT_METRIC_STATS, 'report_id', FkMappingKey.TEST_REPORTS),
    FkRule(TransferTable.REPORT_COMPARISON_MATRIX, 'report_id', FkMappingKey.TEST_REPORTS),
)


def fk_rules_of(table: TransferTable) -> Tuple[FkRule, ...]:
    """取某张表的外键转换规则"""
    return tuple(rule for rule in FK_RULES if rule.table is table)


class DocVersionScope(str, Enum):
    """报告包内 Report Studio 版本搬运策略（设计文档 §6.3 规则 4）

    - full：默认全带（document + 全部 versions），A 侧版本链可回滚；
    - latest：只带当前版本（文档可编辑，历史版本留在 B）。
    """
    FULL = 'full'
    LATEST = 'latest'


DOC_VERSION_SCOPES = frozenset(item.value for item in DocVersionScope)
DEFAULT_DOC_VERSION_SCOPE = DocVersionScope.FULL.value


class ReportPackageEntity(str, Enum):
    """报告包实体声明（manifest.entities，设计文档 §6.3）

    - platform_report：3a 平台报告 7 表；
    - uploaded_file：3b 上传文档（独立文档库）；
    - agent_summary：3c Agent 分析总结文档。
    值与 `ReportStudioSourceType` 一致（报告包与 Studio 文档来源共用词表）。
    """
    PLATFORM_REPORT = 'platform_report'
    UPLOADED_FILE = 'uploaded_file'
    AGENT_SUMMARY = 'agent_summary'


REPORT_PACKAGE_ENTITIES = tuple(item.value for item in ReportPackageEntity)


class ReportStudioTable(str, Enum):
    """报告包内 Studio 三表（值 = 表名 = db/ 下 JSON 文件名）"""
    DOCUMENTS = 'report_studio_documents'
    DOCUMENT_VERSIONS = 'report_studio_document_versions'
    CHART_SPECS = 'report_studio_chart_specs'


REPORT_STUDIO_TABLES = tuple(item.value for item in ReportStudioTable)

# 报告包 manifest.kind：与任务整包（无 kind 的旧 manifest）区分，导入侧据此路由
REPORT_PACKAGE_MANIFEST_KIND = 'report_package'
# 导入回执 warnings 条数上限（超出以 count 汇总，避免回执过大）
REPORT_PACKAGE_WARNINGS_CAP = 200


class ImportProgressStep(str, Enum):
    """导入进度步骤（socket import_progress 事件 payload.step）"""
    PARSING = 'parsing'
    WRITING_DB = 'writing_db'
    EXTRACTING_FILES = 'extracting_files'
    UPDATING_PATHS = 'updating_paths'
    DONE = 'done'
    ERROR = 'error'


class TransferIntent(str, Enum):
    """导入意图（INT-1759，D0 裁定 A10-2）

    - migrate：任务迁移，引用用例必须在目标库可用（默认）
    - restore：历史结果查看 / 备份恢复，无需重新执行 → 默认不做用例硬校验，
      但预检回执必须写明"未校验用例一致性，导入后无法重新执行"
    """
    MIGRATE = 'migrate'
    RESTORE = 'restore'


DEFAULT_TRANSFER_INTENT = TransferIntent.MIGRATE.value

# ===== 用例一致性硬校验（INT-1759，D0 裁定 A10）=====
# 拒绝导入的业务码（同时作为 HTTP 状态码）
CASE_CONSISTENCY_FAILED_CODE = 422
# 回执里缺失用例 ID 列表上限（超出以 truncated=true + missingCount 表达全量条数）
CASE_CONSISTENCY_LIST_CAP = 500
CASE_CONSISTENCY_REJECT_MESSAGE = '目标库缺少 {count} 个测试用例，拒绝导入'
# restore 意图下不校验用例一致性时的固定告警文案
RESTORE_SKIP_CONSISTENCY_WARNING = 'restore 意图未校验用例一致性，导入后无法重新执行'


# ===== ZIP 包结构（设计文档 4.2，文件名用表名）=====
MANIFEST_NAME = 'manifest.json'
DB_DIR = 'db'
DIMENSIONS_SNAPSHOT_PATH = 'meta/dimensions.json'
FILES_CASE_RESULTS_DIR = 'files/case_results'   # 前缀为导出时 task_id 的相对路径
FILES_REF_PARAMS_DIR = 'files/ref_params'       # {test_case_id}/round_{n}.json
FILES_AUDIOS_DIR = 'files/audios'               # 与 storage audios 类别同 key

# ===== 存储类别（shared/infrastructure/storage 的 category 标识）=====
STORAGE_CATEGORY_CASE_RESULT = 'case_result'
STORAGE_CATEGORY_REF_PARAMS = 'ref_params'
STORAGE_CATEGORY_AUDIOS = 'audios'

# ===== Redis 键 =====
REDIS_PROGRESS_KEY = 'data_transfer:import_progress'      # 进度快照（HASH，供 GET /import/progress 兜底）
REDIS_BATCH_KEY_PREFIX = 'data_transfer:batch:'           # + batch_id：回滚批次主键登记
BATCH_TTL_SECONDS = 7 * 24 * 3600                         # 批次登记保留 7 天，供人工介入补偿
PROGRESS_TTL_SECONDS = 24 * 3600

# 导入进度经 EventBus TASK_EVENTS / import_progress 事件发布（五通道收敛，INT-69）

# ===== 导出选项默认值 =====
DEFAULT_INCLUDE_REF_PARAMS = True
DEFAULT_INCLUDE_AUDIOS = False

# ===== 导出临时 ZIP 清理 =====
EXPORT_TEMP_MAX_AGE_SECONDS = 3600  # 超过 1 小时的导出临时 ZIP 在下次导出时清理
