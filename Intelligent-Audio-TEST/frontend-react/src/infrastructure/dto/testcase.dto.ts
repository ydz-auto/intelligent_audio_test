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

/** 用例执行详情（task_bp.py GET /tasks/{id}/cases/{cid}/detail） */
export interface CaseDetailDto {
  test_case_id: string
  task_id: number
  name: string
  execution_status: string
  evaluation_status: string
  duration: number | null
  score: number | null
  devices: Array<{
    device_id: number
    device_name: string
    status: string
    duration: number | null
    score: number | null
    metrics: Array<{
      dimension: string
      round: number | null
      value: string | number | null
    }>
    asr_reference: string | null
    translation_reference: string | null
    audio_results: Array<{ audio_name: string; duration: number | null }>
  }>
}
