/**
 * 任务 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 形态对照 api_gateway/schemas/task.py TaskListItem/TaskDetailData + task_bp.py 实测。
 * 本卡消费：POST /tasks（task:create）+ POST /tasks/{id}/start（task:execute）。
 * 任务详情 mock 复用 09_任务域卡 domain 模型（tasks-mock.ts），接线时经本层 DTO 回填。
 */

/** 任务创建载荷（task_bp.py POST /tasks；实际请求体按后端 TaskCreateSchema 对齐） */
export interface TaskCreateDto {
  name: string
  test_type: 'e2e' | 'api'
  algorithm_type: string | null
  test_case_ids: string[]
  device_ids: number[] | null
  api_ids: number[] | null
  config: {
    rounds: number
    timeout: number
    retries: number
    concurrency: number
    network: string | null
    report_template: string
    include_charts: boolean
    include_detailed_logs: boolean
    include_reference_params: boolean
  }
}

/** 任务启动响应（POST /tasks/{id}/start；实际为 TaskDetailData 信封） */
export interface TaskStartResultDto {
  id: number
  execution_status: string
}
