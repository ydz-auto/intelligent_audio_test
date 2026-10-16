/**
 * 报告 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 形态对照 api_gateway/schemas/report.py 实测：generate-task（report:create）响应 +
 * ReportExportRequest（format=csv/excel/pdf/html，report_bp.py:101、schemas/report.py:230）。
 * 报告详情模型复用 15_报告域卡 domain 模型（reports-mock.ts），接线时经本层 DTO 回填。
 */

/** POST /reports/generate-task 载荷（report:create） */
export interface ReportGenerateTaskDto {
  task_id: number
  template: string
  include_charts: boolean
  include_detailed_logs: boolean
  include_reference_params: boolean
}

/** POST /reports/generate-task 响应 */
export interface ReportGenerateResultDto {
  report_id: number
  status: string
}

/** POST /reports/export 载荷（report_bp.py:101；format csv/excel/pdf/html） */
export interface ReportExportRequestDto {
  report_ids: number[]
  format: 'csv' | 'excel' | 'pdf' | 'html'
}
