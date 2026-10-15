/**
 * AI 对话页 mock 数据（infrastructure 层；红线④：数据一律 mock 常量，不接真实后端）。
 * 形态对照 api_gateway/schemas/report.py ReportListItem / task.py TaskListItem 实测字段：
 * report.type ∈ ReportType 枚举（task/comparison/secondary_comparison）、
 * report.status ∈ ReportStatus 枚举（draft/published）、summary.pass_rate 为百分比 0-100
 * （report_data_builder_persist_mixin.py 实测 round(completed/total*100,2)），后续接线字段不返工。
 */
import type { ChatMessage, ReportContextType } from '@/domain/models/aiChat'

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

/** 流式回复素材：解读报告指标（rich：推理 + 工具 + 表格 + 来源） */
export const MOCK_AGENT_REPLY =
  '已为你解读这份报告的核心指标。\n\n' +
  '## 通过率\n\n' +
  '报告 #320 共执行 **156** 个用例，通过 **144** 个，通过率 **92.3%**。\n\n' +
  '| 指标 | 数值 | 上版（T315） | 变化 |\n' +
  '| --- | --- | --- | --- |\n' +
  '| 通过率 | 92.3% | 97.9% | -5.6pp |\n' +
  '| 首唤醒延迟 P50 | 412ms | 388ms | +24ms |\n' +
  '| 误唤醒率 | 1.8% | 1.2% | +0.6pp |\n\n' +
  '## 异常项\n\n' +
  '- **远场 3m + 55dB 噪声**：通过率仅 **61%**，为主要退步来源；\n' +
  '- **设备 A（Android 13）**：误唤醒率 2.4%，显著高于均值；\n' +
  '- **连续唤醒 10 次**：存在 2 例静音误触发。\n\n' +
  '> 所有数值均来自报告七表，AI 只起草不算数；无法证明来源的指标已标注「待核实」。\n\n' +
  '可以继续追问：需要我把这些退步项按信噪比分层展开吗？'

/** 流式回复素材：简短确认（追问类） */
export const MOCK_AGENT_SHORT_REPLY =
  '本次测试通过率为 **92.3%**（144/156）。对比上一版 T315（97.9%），**下降了 5.6 个百分点**，主要退步集中在远场噪声场景（详见上方表格）。需要我按设备/信噪比维度进一步展开吗？'

/** 首访演示会话（可视稿展示用；「清空对话」后回到规范空态） */
export const DEMO_MESSAGES: ChatMessage[] = [
  {
    key: 'demo-user-1',
    from: 'user',
    versions: [{ id: 'demo-user-1-v1', content: '解读这份报告的核心指标，指出异常项' }],
    createdAt: 1730000000000,
  },
  {
    key: 'demo-assistant-1',
    from: 'assistant',
    versions: [{ id: 'demo-assistant-1-v1', content: MOCK_AGENT_REPLY }],
    createdAt: 1730000000500,
    completedAt: 1730000009500,
    durationMs: 9000,
    status: 'complete',
    reasoning: {
      content: '用户要求解读报告 #320 核心指标并指出异常项。先读取报告事实表，再按通过率/延迟/误唤醒率三维度组织回答。',
      duration: 3,
    },
    toolCalls: [
      {
        id: 'demo-tool-1',
        tool: 'report_get_facts',
        label: '读取报告数据',
        status: 'completed',
        summary: '报告 #320（T320 唤醒词识别回归）：156 用例，通过 144，通过率 92.3%。',
      },
      {
        id: 'demo-tool-2',
        tool: 'report_query_metrics',
        label: '查询报告指标',
        status: 'completed',
        summary: '首唤醒延迟 P50=412ms；误唤醒率 1.8%；远场 3m+55dB 通过率 61%。',
      },
    ],
    sourceRefs: [
      { reportId: 320, metricId: 'pass_rate', dataVersion: 'v3', verified: true },
      { reportId: 320, metricId: 'p50_latency', dataVersion: 'v3', verified: true },
      { reportId: 320, metricId: 'farfield_55db', dataVersion: 'v2', verified: false },
    ],
  },
  {
    key: 'demo-user-2',
    from: 'user',
    versions: [{ id: 'demo-user-2-v1', content: '这次测试的通过率是多少？和上一版比怎么样？' }],
    createdAt: 1730000010000,
  },
  {
    key: 'demo-assistant-2',
    from: 'assistant',
    versions: [{ id: 'demo-assistant-2-v1', content: MOCK_AGENT_SHORT_REPLY }],
    createdAt: 1730000010500,
    completedAt: 1730000014500,
    durationMs: 4000,
    status: 'complete',
    sourceRefs: [
      { reportId: 320, metricId: 'pass_rate', dataVersion: 'v3', verified: true },
      { reportId: 315, metricId: 'pass_rate', dataVersion: 'v1', verified: true },
    ],
  },
]

/** 展示用推理/思考素材 */
export const MOCK_REASONING_CONTENT =
  '用户要求解读报告核心指标并指出异常项。先读取报告事实表（report_get_facts），再按通过率/延迟/误唤醒率三维度组织回答，异常项按退步幅度排序。'
