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
    """导出包 manifest 版本（version 不符直接拒绝导入，不做跨版本迁移）

    - 1.0：整包导出（/export），原始报文以内联 JSON 落在 db 行里
    - 1.1：增量包（/export-incremental）与报告包，多 sourceTask / entities 段
      （INT-1761 / D0 裁定 A1：导入侧同时接受 1.0 与 1.1，不因版本号误拒历史包）
    - 1.2：包内携带原始报文对象（`files/raw/...` + manifest.rawObjects，
      INT-1811 / A1）。整包与增量包都产出 1.2；导入侧仍接受 1.0 / 1.1
      （1.0 的内联 JSON 在导入时现场物化，1.1 缺对象时按行降级并在回执里列警告）
    """
    V1_0 = '1.0'
    V1_1 = '1.1'
    V1_2 = '1.2'


SUPPORTED_MANIFEST_VERSIONS = {
    ManifestVersion.V1_0.value,
    ManifestVersion.V1_1.value,
    ManifestVersion.V1_2.value,
}

# 增量包 / 报告包产出 1.2（整包导出同产 1.2：包结构一致，都带原始报文对象）
INCREMENTAL_MANIFEST_VERSION = ManifestVersion.V1_2.value
# 整包导出版本（INT-1811 起由 1.0 升到 1.2）
FULL_MANIFEST_VERSION = ManifestVersion.V1_2.value
# 包内带原始报文对象的最低版本：>= 该版本的包对象必须齐全（缺对象按坏包拒绝）
RAW_OBJECTS_MANIFEST_VERSION = ManifestVersion.V1_2.value


def _version_tuple(version) -> tuple:
    """'1.2' → (1, 2)；非法版本返回空元组（由 validate_manifest 统一拒绝）"""
    parts = str(version or '').split('.')
    try:
        return tuple(int(part) for part in parts)
    except (TypeError, ValueError):
        return ()


def manifest_requires_raw_objects(version) -> bool:
    """包版本是否声明「原始报文对象齐全」——1.2 起缺对象按坏包拒绝；
    1.0 / 1.1 历史包没有对象段，导入侧按行降级（见 raw_payload_store）。"""
    parsed = _version_tuple(version)
    return bool(parsed) and parsed >= _version_tuple(RAW_OBJECTS_MANIFEST_VERSION)


class IncrementalInclude(str, Enum):
    """增量包可选段（POST /export-incremental 的 include 取值）"""
    DIMENSIONS = 'dimensions'
    REPORTS = 'reports'


# 增量包默认包含两段（与设计文档 §5.2 请求示例一致）
DEFAULT_INCREMENTAL_INCLUDE = (IncrementalInclude.DIMENSIONS.value,
                               IncrementalInclude.REPORTS.value)


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


# ===== 增量包（链路 2，INT-1761 / D0 裁定 A1-A2）=====
# 增量包只含维度评分 + 报告 7 表（不含任务 / 结果 / 用例 / 文件本体）：
# 包内 id 已是 A 原始 id，导入不做重映射（维度 id 除外，按名称链翻译）
INCREMENTAL_DIMENSION_TABLES = (TransferTable.TEST_RESULT_DIMENSIONS,)
INCREMENTAL_REPORT_TABLES = (
    TransferTable.TEST_REPORTS,
    TransferTable.REPORT_SUMMARIES,
    TransferTable.REPORT_SUMMARY_META,
    TransferTable.REPORT_RAW_DATA,
    TransferTable.REPORT_CASES,
    TransferTable.REPORT_METRIC_STATS,
    TransferTable.REPORT_COMPARISON_MATRIX,
)

# 增量导出 / 导入失败码（同时作为 HTTP 状态码，走 TaskConfigResponse.code）
INCREMENTAL_UNMAPPED_CODE = 409          # 导出侧存在未映射结果行（B 侧重执行产生）
INCREMENTAL_ID_MISSING_CODE = 409        # 包内 id 在目标库不存在
INCREMENTAL_FINGERPRINT_CODE = 409       # 指纹不符（任务与包不匹配）
INCREMENTAL_INVALID_PACKAGE_CODE = 400   # 包结构 / 多任务 / id 不一致
INCREMENTAL_TASK_NOT_FOUND_CODE = 404    # A 库任务不存在或已软删
INCREMENTAL_TASK_FORBIDDEN_CODE = 403    # 私有任务且非 owner

INCREMENTAL_UNMAPPED_RESULT_MESSAGE = (
    'B 侧存在 A 未登记的结果行（重新执行产生），增量回导 v1 不支持，'
    '请改用整包导出或先在 B 侧回退')
INCREMENTAL_NO_SOURCE_MAP_MESSAGE = (
    'B 未整包导入过 A 的数据，请先走链路 1（整包导入）再导出增量')
INCREMENTAL_SINGLE_TASK_MESSAGE = '增量包只支持单任务'
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
    # 增量回导（INT-1761）：两个跨服务合并段
    MERGING_DIMENSIONS = 'merging_dimensions'
    REPLACING_REPORTS = 'replacing_reports'
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
# 原始报文对象（INT-1811）：包内路径 = `FILES_DIR` + 存储 key（key 首段
# `shared.utils.raw_payload.RAW_KEY_ROOT`），即
# `files/raw/{resp|req}/{sha[:2]}/{sha}.json.gz`。内容寻址 → 同对象天然只出现一次；
# 导入侧按 key 原样回写（免 id 重映射）。
FILES_DIR = 'files'
# manifest 里的对象清单段（与包内 files/raw/ 条目一一对应）
RAW_OBJECTS_MANIFEST_KEY = 'rawObjects'

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
