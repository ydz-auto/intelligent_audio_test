/**
 * 测试用例 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 形态对照 api_gateway/schemas/testcase.py TestCaseListItem/TestCaseDimensionBrief 实测逐字段。
 */

/** POST /testcases 列表项（testcase.py TestCaseListItem；选择场景所需子集） */
export interface TestCaseListItemDto {
  id: string
  name: string
  description: string | null
  group_id: string | null
  group_name: string | null
  type: string | null
  tags: string[]
  algorithm_type: string | null
  total_duration: number | null
  /** INT-141 收藏 / 回收站（对照 Vue TestCaseDto 同款可选；mock/partial 源兼容） */
  created_at?: string | null
  updated_at?: string | null
  is_favorite?: boolean | null
  deleted?: boolean | null
  deleted_at?: string | null
  deleted_by_user_id?: number | null
  config: {
    rounds: Array<Record<string, unknown>> | null
    dimensions: Array<{ id: number; name: string; weight: number | null; test_type: string | null }>
  }
  /**
   * 算法参数独立列（test_cases.algorithm_params；按轮分组
   * [{round_number, params:[{field_code, field_value}]}]，编辑回填/保存原样透传）
   */
  algorithm_params?: unknown
  /** 参考参数独立列（test_cases.reference_params；按轮分组 [{round_number, reference_params_path}]） */
  reference_params?: unknown
}

/** GET /testcases 列表响应（testcase.py TestCaseListData：PaginatedData 信封内 items） */
export interface TestCaseListDataDto {
  items: TestCaseListItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/**
 * 用例试听响应（POST /testcases/{id}/preview → testcase.py TestCasePreviewData 逐字段）。
 * frontend 模式回音频流 URL（多轮时 audio_stream_urls 连续播放），
 * backend 模式由网关经播放编排在用例配置设备上放音，仅回时长。
 */
export interface TestCasePreviewDto {
  test_case_id: string
  preview_task_id?: string | null
  status: string
  message?: string | null
  duration?: number | null
  playback_mode?: string | null
  audio_id?: number | string | null
  audio_stream_url?: string | null
  /** 多轮音频连续播放（>1 条时返回） */
  audio_stream_urls?: string[] | null
}

/** 停止用例试听响应（POST /testcases/{id}/stop_preview → TestCaseStopPreviewData） */
export interface TestCaseStopPreviewDto {
  test_case_id: string
  status: string
  message?: string | null
}

/** POST /testcases/import 响应 data（TestCaseImportResult，snake_case 回执） */
export interface TestCaseImportResultDto {
  imported_count?: number
  updated_count?: number
  skipped_count?: number
  copied_count?: number
  errors?: unknown[]
}

/** 导入预览重复项（POST /testcases/import/preview 的 duplicates[]） */
export interface TestCaseImportDuplicateDto {
  row?: number
  name?: string | null
  id?: string | number | null
  existingId?: string | number | null
  existingName?: string | null
  matchedBy?: 'id' | 'name' | null
}

/**
 * POST /testcases/import/preview 响应 data。
 * 后端 preview_result 使用 camelCase 键（totalRows/duplicates/duplicateCount…），按实测契约声明。
 */
export interface TestCaseImportPreviewDto {
  totalRows?: number
  duplicates?: TestCaseImportDuplicateDto[]
  duplicateCount?: number
  duplicateScanTruncated?: boolean
  errors?: unknown[]
}

/** 用例执行详情·算法结果扁平项（task_bp.py get_case_detail algorithm_results 实测；API/voice_llm 用例分节①结果摘要消费） */
export interface CaseAlgorithmResultDto {
  param_code: string
  param_type?: string | null
  label?: string | null
  round_number?: number | null
  dimension_name?: string | null
  device?: string | null
  value?: unknown
  rounds?: unknown
}

/** 评估维度配置项（GET /tasks/{id}/cases/{cid}/detail metric_configs 实测：{code,name}） */
export interface CaseMetricConfigDto {
  code: string
  name: string
}

/** 结果音频项（detail result_audios 实测：设备键 → [{url, filename, param_code}]） */
export interface CaseResultAudioDto {
  url?: string | null
  filename?: string | null
  param_code?: string | null
}

/** 参考/输入音频项（detail audio_list 实测；后端部分字段为 camelCase，照原样声明） */
export interface CaseAudioListItemDto {
  id: number
  filename: string
  duration?: number | null
  url?: string | null
  testType?: string | null
  /** 所属轮次（1 起；camelCase 实测，snake_case 兜底） */
  roundNumber?: number | null
  round_number?: number | null
}

/** 用例执行详情（task_bp.py GET /tasks/{id}/cases/{cid}/detail 实测） */
export interface CaseDetailDto {
  test_case_id: string
  task_id: number
  /** 后端实测返回 case_name（无 name 字段）；name 留底兼容 */
  case_name: string
  name?: string
  execution_status: string
  evaluation_status: string
  duration: number | null
  score: number | null
  algorithm_type: string | null
  algorithm_results: CaseAlgorithmResultDto[]
  /**
   * 设备名列表——后端 `task_query_service` 实测按 `list(set(pr['device_name']))` 派生，
   * **字符串数组**（INT-1688 修正：此前按对象数组声明，真实响应对应元素全 undefined）。
   */
  devices: string[]
  /** 评估维度配置（维度列顺序权威源；实测 6 项） */
  metric_configs?: CaseMetricConfigDto[]
  /**
   * 参考参数（网关侧经 report_service BuildReferenceParams 构建；INT-2088 接线）。
   * `{code: {code, type, value, segments, text, json}}`，键含 `answer@round:N` 等多轮展开。
   */
  reference_params?: Record<string, unknown>
  /**
   * 字段映射（算法 GetFullFieldMapping；`{result:[...], reference:[...]}`，
   * 项含 `param_code`/`param_type`/`label`；INT-2088 接线——参考/结果文本字段与时间轴判据）。
   */
  field_mapping?: { result?: Array<Record<string, unknown>>; reference?: Array<Record<string, unknown>> }
  /** 结果音频（设备键 → 音频项；多数用例为空，音频在 algorithm_results 的 audio_file 项里） */
  result_audios?: Record<string, CaseResultAudioDto[]>
  /** 参考/输入音频（用例音频列表；旧 Vue 走「音频时间轴」，不在结果音频区） */
  audio_list?: CaseAudioListItemDto[]
}
