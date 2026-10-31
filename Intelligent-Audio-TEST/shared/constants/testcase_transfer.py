# -*- coding: utf-8 -*-
"""测试用例导入导出（TestCase Transfer）共享常量。

用例包结构与重复处理策略的唯一配置来源，供网关导出/导入服务共用：

- 包结构：`manifest.json` + `testcases.json` + 可选
  `reference_params/{case_id}/round_{n}.json`
- 导出格式：json / csv / xlsx / zip（zip 为数据包）
- 导入重复策略：skip（默认）/ overwrite / copy
"""
from enum import Enum


class TestCaseExportFormat(str, Enum):
    """用例导出格式（POST /testcases/export 的 format）"""
    JSON = 'json'
    CSV = 'csv'
    XLSX = 'xlsx'
    ZIP = 'zip'


class TestCaseDuplicateStrategy(str, Enum):
    """导入时重复用例处理策略（POST /testcases/import 的 on_duplicate）"""
    SKIP = 'skip'
    OVERWRITE = 'overwrite'
    COPY = 'copy'


DEFAULT_DUPLICATE_STRATEGY = TestCaseDuplicateStrategy.SKIP

# 重复策略别名（兼容前端 camelCase / 中文文案）
DUPLICATE_STRATEGY_ALIASES = {
    'skip': TestCaseDuplicateStrategy.SKIP,
    'ignore': TestCaseDuplicateStrategy.SKIP,
    '跳过': TestCaseDuplicateStrategy.SKIP,
    'overwrite': TestCaseDuplicateStrategy.OVERWRITE,
    'update': TestCaseDuplicateStrategy.OVERWRITE,
    '覆盖': TestCaseDuplicateStrategy.OVERWRITE,
    'copy': TestCaseDuplicateStrategy.COPY,
    'duplicate': TestCaseDuplicateStrategy.COPY,
    '副本': TestCaseDuplicateStrategy.COPY,
    '另存副本': TestCaseDuplicateStrategy.COPY,
}

# 重复判定来源（回执/预览透出）
DUPLICATE_MATCH_ID = 'id'
DUPLICATE_MATCH_NAME = 'name'

# ---- ZIP 包结构 ----
PACKAGE_FORMAT = 'intelligent-audio-testcase-package'
# 1.1（INT-2214）：ZIP 可携带 audios/（用例引用音频二进制）+ manifest 音频清单/缺失计数
PACKAGE_VERSION = '1.1'
MANIFEST_FILENAME = 'manifest.json'
TESTCASES_FILENAME = 'testcases.json'
REFERENCE_PARAMS_DIR = 'reference_params'
# 用例引用音频在包内的目录（文件名 {audio_id}.{ext}）
AUDIOS_DIR = 'audios'

# 包内单个参考参数文件大小上限（防异常包撑爆内存）
MAX_REFERENCE_PARAM_BYTES = 5 * 1024 * 1024

# 重复判定按名称查询时的单页条数（关键字命中后本地再做精确比对）
NAME_LOOKUP_PAGE_SIZE = 200

# 预览重复检测的行数上限（逐行 RPC，避免超大文件把预览拖成超时）
PREVIEW_DUPLICATE_SCAN_LIMIT = 500

# 「另存副本」名称后缀与去重上限
COPY_NAME_SUFFIX = '_copy'
COPY_NAME_MAX_ATTEMPTS = 100
