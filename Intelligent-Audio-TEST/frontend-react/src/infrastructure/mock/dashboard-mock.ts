/**
 * 控制台工作台 mock 常量（红线④：数据一律 mock，不接真实后端）。
 * 字段形态对照 api_gateway/schemas/home.py + task.py 实测 schema（见 domain/models/stats.ts 注释），
 * 后续接线时仅替换 infrastructure/api 桩实现，页面与 hook 不返工。
 * 数字口径与基座 MOCK_HOME_STATS（infrastructure/api/home.ts）对齐：任务 342/已完成 297、
 * 设备 8 在线/2 离线，跨页面演示数据不打架；trend 为「任务完成趋势」口径，各粒度序列可互推。
 */
import type {
  HomeStatsSummary,
  TaskDomainStats,
  TaskQualityStats,
} from '@/domain/models/stats'

type TrendPoints = TaskDomainStats['trend']

// 状态覆盖五色徽章：completed=success / running·queued=info / paused=warning /
// failed=danger / pending·stopped=neutral / merged=chart-4（映射见 constants.ts）
const MOCK_RECENT_TASKS = [
  {
    id: 1042,
    name: '智能音箱旗舰机型全量回归 · 第 3 轮',
    device_types: ['smart_speaker'],
    status: 'running',
    algorithm_type: 'asr_streaming',
    total_cases: 48,
    completed_cases: 31,
    created_at: '2026-10-15T08:42:00',
  },
  {
    id: 1041,
    name: '车载语音助手唤醒词响应测试',
    device_types: ['car_system'],
    status: 'completed',
    algorithm_type: 'wakeword_detect',
    total_cases: 96,
    completed_cases: 96,
    created_at: '2026-10-14T17:05:00',
  },
  {
    id: 1040,
    name: 'API 通道并发稳定性验证（压测时段）',
    device_types: ['http_api'],
    status: 'failed',
    algorithm_type: 'asr_streaming',
    total_cases: 60,
    completed_cases: 37,
    created_at: '2026-10-14T14:20:00',
  },
  {
    id: 1039,
    name: '耳机产品线夜间批量回归',
    device_types: ['headset'],
    status: 'queued',
    algorithm_type: 'tts_eval',
    total_cases: 120,
    completed_cases: 0,
    created_at: '2026-10-14T09:10:00',
  },
  {
    id: 1038,
    name: '新风控语音播报音质评估',
    device_types: ['smart_speaker'],
    status: 'paused',
    algorithm_type: 'tts_eval',
    total_cases: 36,
    completed_cases: 12,
    created_at: '2026-10-13T16:48:00',
  },
  {
    id: 1037,
    name: '多方言识别准确性抽样测试',
    device_types: ['headset', 'smart_speaker'],
    status: 'pending',
    algorithm_type: 'asr_streaming',
    total_cases: 72,
    completed_cases: 0,
    created_at: '2026-10-13T11:02:00',
  },
  {
    id: 1036,
    name: 'TTS 自然度主观评估（第 2 期）',
    device_types: ['http_api'],
    status: 'stopped',
    algorithm_type: 'tts_eval',
    total_cases: 54,
    completed_cases: 20,
    created_at: '2026-10-12T15:30:00',
  },
  {
    id: 1035,
    name: 'Q3 音箱品类回归汇总（合并自 4 个任务）',
    device_types: ['smart_speaker'],
    status: 'merged',
    algorithm_type: 'asr_streaming',
    total_cases: 384,
    completed_cases: 384,
    created_at: '2026-10-11T10:00:00',
  },
] satisfies HomeStatsSummary['recent_tasks']

/** GET /api/v1/home/stats/summary 形态（home.py HomeStatsSummary） */
export const MOCK_HOME_STATS_SUMMARY: HomeStatsSummary = {
  recent_tasks: MOCK_RECENT_TASKS,
  top_groups: [
    { id: 'g-01', name: '旗舰音箱回归集', case_count: 128 },
    { id: 'g-02', name: '车载唤醒与识别', case_count: 96 },
    { id: 'g-03', name: 'API 通道稳定性', case_count: 84 },
    { id: 'g-04', name: '耳机产品线冒烟', case_count: 61 },
    { id: 'g-05', name: '方言与口音抽样', case_count: 45 },
  ],
  // 与基座 MOCK_HOME_STATS.devices（8/2/10）一致
  device_status: { online: 8, offline: 2 },
}

/**
 * GET /api/v1/tasks/stats?granularity=… 形态（task.py TaskDomainStatsData）。
 * 仅 trend 随粒度变化（status_counts/type_counts 与粒度无关，照后端口径）。
 * trend 为「任务完成趋势」口径，序列按 全期完成 297 互推：
 * 年合计 297 → 2026 月合计 92 → 周合计与所在月一致 → 日合计与所在周一致。
 */
export function buildMockTaskDomainStats(
  granularity: TaskDomainStats['granularity']
): TaskDomainStats {
  const trendByGranularity: Record<TaskDomainStats['granularity'], TrendPoints> =
    {
      day: [
        { key: '10-09', count: 2 },
        { key: '10-10', count: 2 },
        { key: '10-11', count: 1 },
        { key: '10-12', count: 3 },
        { key: '10-13', count: 3 },
        { key: '10-14', count: 3 },
        { key: '10-15', count: 3 },
      ],
      week: [
        { key: '09-08', count: 3 },
        { key: '09-15', count: 4 },
        { key: '09-22', count: 4 },
        { key: '09-29', count: 5 },
        { key: '10-06', count: 8 },
        { key: '10-13', count: 9 },
      ],
      month: [
        { key: '05月', count: 10 },
        { key: '06月', count: 12 },
        { key: '07月', count: 13 },
        { key: '08月', count: 14 },
        { key: '09月', count: 16 },
        { key: '10月', count: 27 },
      ],
      year: [
        { key: '2021', count: 6 },
        { key: '2022', count: 14 },
        { key: '2023', count: 31 },
        { key: '2024', count: 58 },
        { key: '2025', count: 96 },
        { key: '2026', count: 92 },
      ],
    }

  return {
    total: 342,
    deleted_total: 6,
    // 与基座 tasks（total 342/completed 297/running 3/failed 42）一致
    status_counts: {
      completed: 297,
      failed: 42,
      running: 3,
    },
    type_counts: { e2e: 205, api: 112, mixed: 25 },
    trend: trendByGranularity[granularity],
    granularity,
  }
}

/** 质量统计 mock：pass_rate ← task.py TaskStatsData（297/342≈86.8）；average_score ← 报告域口径（立项前 mock） */
export const MOCK_TASK_QUALITY: TaskQualityStats = {
  pass_rate: 86.8,
  average_score: 87.5,
  scored_reports: 142,
}

/** 通过率近 7 日 mock 序列（task.py TaskStatsData.pass_rate 时序扩展，接口立项前 mock） */
export const MOCK_PASS_RATE_TREND = [78, 80, 79, 82, 83, 84, 86.8]

/** 平均得分近 7 日 mock 序列（同上，仅可视化用） */
export const MOCK_AVG_SCORE_TREND = [82, 83.5, 85, 84, 86, 87, 87.5]
