/**
 * AI 对话页 mock 数据（infrastructure 层；红线④：数据一律 mock 常量，不接真实后端）。
 * 形态对照 api_gateway/schemas/report.py ReportListItem / task.py TaskListItem 实测字段：
 * report.type ∈ ReportType 枚举（task/comparison/secondary_comparison）、
 * report.status ∈ ReportStatus 枚举（draft/published）、summary.pass_rate 为百分比 0-100
 * （report_data_builder_persist_mixin.py 实测 round(completed/total*100,2)），后续接线字段不返工。
 */
import type { ReportContextType } from '@/domain/models/aiChat'

export type MockReportListItem = {
  id: number
  name: string
  type: ReportContextType
  task_id: number | null
  task_name: string
  algorithm_type: string | null
  summary: {
    total_cases: number
    completed_cases: number
    failed_cases: number
    pass_rate: number
    task_count: number | null
  }
  description: string | null
  status: 'draft' | 'published'
  created_at: string
  updated_at: string
}

export type MockTaskListItem = {
  id: number
  name: string
  status: string
  algorithm_type: string | null
  created_at: string
}

/** GET /reports 列表 mock（report:read 实测在册；report_bp.py:29） */
export const MOCK_REPORTS: MockReportListItem[] = [
  {
    id: 320,
    name: 'T320 唤醒词识别回归测试报告',
    type: 'task',
    task_id: 320,
    task_name: '任务 #320 唤醒词识别回归',
    algorithm_type: '唤醒词识别',
    summary: {
      total_cases: 156,
      completed_cases: 144,
      failed_cases: 12,
      pass_rate: 92.31,
      task_count: 1,
    },
    description: '唤醒词「小智小智」多设备/多噪声环境回归',
    status: 'published',
    created_at: '2026-10-14T09:20:00Z',
    updated_at: '2026-10-14T09:35:00Z',
  },
  {
    id: 319,
    name: 'T319 远场唤醒性能对比报告',
    type: 'comparison',
    task_id: null,
    task_name: '对比：T315 vs T318',
    algorithm_type: '唤醒词识别',
    summary: {
      total_cases: 120,
      completed_cases: 115,
      failed_cases: 5,
      pass_rate: 95.83,
      task_count: 2,
    },
    description: '对比 v2.1 与 v2.2 两版唤醒算法的远场性能',
    status: 'published',
    created_at: '2026-10-13T15:10:00Z',
    updated_at: '2026-10-13T15:42:00Z',
  },
  {
    id: 317,
    name: 'T317 噪声场景鲁棒性二次对比报告',
    type: 'secondary_comparison',
    task_id: null,
    task_name: '二次对比：T319 关键指标',
    algorithm_type: '唤醒词识别',
    summary: {
      total_cases: 88,
      completed_cases: 79,
      failed_cases: 9,
      pass_rate: 89.77,
      task_count: 3,
    },
    description: '针对 T319 报告退步项再做信噪比分层二次对比',
    status: 'published',
    created_at: '2026-10-13T11:05:00Z',
    updated_at: '2026-10-13T11:50:00Z',
  },
  {
    id: 315,
    name: 'T315 端到端唤醒延迟测试报告',
    type: 'task',
    task_id: 315,
    task_name: '任务 #315 唤醒延迟基线',
    algorithm_type: '唤醒词识别',
    summary: {
      total_cases: 96,
      completed_cases: 94,
      failed_cases: 2,
      pass_rate: 97.92,
      task_count: 1,
    },
    description: '首唤醒延迟 / 误唤醒率基线采集',
    status: 'draft',
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:28:00Z',
  },
]

/** GET /tasks 列表 mock（task:read；报告上下文选择器任务组数据源） */
export const MOCK_TASKS: MockTaskListItem[] = [
  {
    id: 320,
    name: '任务 #320 唤醒词识别回归',
    status: 'completed',
    algorithm_type: '唤醒词识别',
    created_at: '2026-10-14T08:40:00Z',
  },
  {
    id: 315,
    name: '任务 #315 唤醒延迟基线',
    status: 'completed',
    algorithm_type: '唤醒词识别',
    created_at: '2026-10-12T09:20:00Z',
  },
  {
    id: 308,
    name: '任务 #308 噪声场景信噪比分层',
    status: 'completed',
    algorithm_type: '噪声鲁棒性',
    created_at: '2026-10-10T14:30:00Z',
  },
]
