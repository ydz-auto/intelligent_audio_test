/**
 * 用例域领域模型（domain 层；10_测试执行.md §9 落位 + 11_用例域.md §3.3 表格版式）。
 * 形态对照 api_gateway/schemas/testcase.py TestCaseListItem/TestCaseConfig 实测：
 * id/name/description/group_id/group_name/type/tags/algorithm_type/total_duration/updated_at
 * + INT-141 收藏/回收站字段（is_favorite/deleted/deleted_at/deleted_by_user_id）。
 * 执行类型子集（选择场景列裁剪）；完整用例管理页列表项 = TestCaseListItem。
 */

export type TestCaseType = 'e2e' | 'api'

/** 用例列表项（选择场景所需子集） */
export interface TestCase {
  id: string
  name: string
  description: string | null
  groupId: string | null
  groupName: string | null
  /** 执行类型（api/e2e）；schema type 字段实测 */
  type: TestCaseType | null
  tags: string[]
  algorithmType: string | null
  /** 轮次数（由 config.rounds 长度派生；展示「{n} 轮」） */
  rounds: number
  /** 总时长（秒，total_duration 实测；展示「{x}m {y}s」） */
  totalDuration: number | null
  updatedAt: string | null
}

/**
 * 用例列表项（11_用例域.md §3.3 表格版式，schemas/testcase.py:122 TestCaseListItem 实测）。
 * tags 为名称串（schema List[str]）；标签分类/色值经 infrastructure/api/tags-api 登记表
 * （TagItem{categoryId,categoryName,color}，INT-487 按分类呈现口径）名称→属性映射，接线不改。
 */
export interface TestCaseListItem {
  id: string
  name: string
  description: string | null
  groupId: string | null
  groupName: string | null
  /** 执行类型（api/e2e；残留 test_type 列，待 INT-79 废弃——正式类型维度=algorithmType） */
  type: TestCaseType | null
  tags: string[]
  algorithmType: string | null
  createdAt: string | null
  updatedAt: string | null
  /** INT-141 收藏 / 回收站 */
  isFavorite: boolean | null
  deleted: boolean | null
  deletedAt: string | null
  deletedByUserId: number | null
  /** 总时长（秒；展示「{x}m {y}s」，0 不显） */
  totalDuration: number | null
  /** 轮次数（由 config.rounds 长度派生；展示「{n} 轮」） */
  rounds: number
  /**
   * 音频条数（mock 阶段派生字段：0=无关联音频 → 预览钮置灰 + Tooltip
   * 「该测试用例没有关联音频文件」，11_用例域.md §3.3.2；
   * 接线后由 TestCaseListItem.config.rounds[].audios 派生（schemas/testcase.py:104
   * RoundConfigItem.audios 实测），不再占位）
   */
  audioCount?: number | null
  /**
   * 原始 config（TestCaseConfig JSONB 透传；编辑回填轮次/保存合并用，结构对照
   * schemas/testcase.py TestCaseConfig：rounds/dimensions/background_noise/... 内嵌
   * snake_case 契约——与 Vue 基准一致，infrastructure 顶层映射、值内 Dict 原样透传）。
   */
  config?: Record<string, unknown> | null
  /** 算法参数独立列（按轮分组 [{round_number, params:[{field_code, field_value}]}]；保存原样回传） */
  algorithmParams?: unknown
  /** 参考参数独立列（按轮分组 [{round_number, reference_params_path}]；保存原样回传） */
  referenceParams?: unknown
}

/** 评估维度简报（testcase.py TestCaseDimensionBrief） */
export interface EvaluationDimension {
  id: number
  name: string
  type: string | null
}

/** 试听播放模式（POST /testcases/{id}/preview 的 preview_type/playback_mode 二值，§5.2） */
export type PreviewPlaybackMode = 'frontend' | 'backend'

/** 用例试听结果（domain；infrastructure 已把 TestCasePreviewData snake_case 转成 camelCase） */
export interface TestCasePreview {
  testCaseId: string
  previewTaskId: string | null
  status: string
  message: string | null
  /** 试听总时长（秒；frontend 模式为全部音频时长之和，backend 模式为编排端实测时长） */
  duration: number | null
  playbackMode: PreviewPlaybackMode
  audioId: number | string | null
  /** 浏览器播放入口（多轮时为第一段） */
  audioStreamUrl: string | null
  /** 多轮音频流（连续播放；单轮为空数组） */
  audioStreamUrls: string[]
}

/** 用例已配置的播放设备（播放器设备区真实数据源：config.rounds[].audios[].playback_device_*） */
export interface CasePlaybackDevice {
  id: string | null
  name: string
}

/**
 * 用例导入重复策略（POST /testcases/import 表单 on_duplicate）。
 * skip=跳过（默认）/ overwrite=覆盖 / copy=另存副本。
 */
export type TestCaseDuplicateStrategy = 'skip' | 'overwrite' | 'copy'

/** 导入预览中的重复用例（后端按 ID 或同分组同名命中） */
export interface TestCaseImportDuplicate {
  row: number
  name: string | null
  id: string | null
  existingId: string | null
  existingName: string | null
  matchedBy: 'id' | 'name' | null
}

/** 导入预览（POST /testcases/import/preview） */
export interface TestCaseImportPreview {
  /** 文件内用例总行数 */
  totalRows: number
  duplicates: TestCaseImportDuplicate[]
  duplicateCount: number
  /** 超过扫描上限时重复清单未覆盖全部行 */
  duplicateScanTruncated: boolean
  errors: string[]
}

/** 导入回执（POST /testcases/import） */
export interface TestCaseImportResult {
  importedCount: number
  updatedCount: number
  skippedCount: number
  copiedCount: number
  errors: string[]
}
