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
  updated_at: string | null
  config: {
    rounds: Array<Record<string, unknown>> | null
    dimensions: Array<{ id: number; name: string; weight: number | null; test_type: string | null }>
  }
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
