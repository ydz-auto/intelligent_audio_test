/**
 * BenchmarkReportPanel 交互回归（INT-483 详情 benchmark 渲染分支）
 *
 * 覆盖：报告详情内嵌排行区块——按 suite/category/source 反查 benchmark_reports
 * 记录 → 详情取排行快照 → 指标组页签 + 榜单表 + 双轨来源徽章渲染。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const portMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getOne: vi.fn(),
}))

vi.mock('@/composables/benchmark/benchmarkReportsPort', () => ({
  benchmarkReportsPort: portMocks,
}))

import BenchmarkReportPanel from '../BenchmarkReportPanel.vue'

const REPORT_PROPS = {
  report: {
    id: 101,
    name: 'LibriSpeech 基准报告',
    type: 'benchmark',
    status: 'published',
    config: {
      benchmark: true,
      suite: 'librispeech-test-clean',
      category: 'asr',
      source: 'platform_test',
      name: 'LibriSpeech 基准报告',
      description: '',
    },
    summary: {},
  },
}

const RECORD = {
  id: 5,
  reportId: 101,
  taskId: null,
  suite: 'librispeech-test-clean',
  category: 'asr',
  source: 'platform_test',
  algorithmSet: '',
  publishedTaskCount: 3,
  subjectCount: 2,
  metricCount: 1,
  version: 1,
  publishedBy: 'tester',
  publishedAt: '2026-10-16T07:00:00',
  createdAt: '2026-10-16T07:00:00',
  updatedAt: '2026-10-16T07:00:00',
  rankingData: {
    filters: { suite: 'librispeech-test-clean', category: 'asr', source: 'platform_test' },
    counts: { publishedTaskCount: 3, subjectCount: 2, metricCount: 1, rowCount: 2 },
    rows: [
      {
        id: 1, source: 'platform_test', publishedTaskId: null, publishedTaskVersion: null,
        reportId: null, baselineId: null, subjectName: '模型A', subjectType: 'closed_source',
        deviceType: 'websocket_api', benchmarkSuite: 'librispeech-test-clean', category: 'asr',
        metricCode: 'WER', metricName: '字错误率', metricValue: 8.5, unit: '%',
        direction: 'lower_is_better', rank: 1, total: 2, percentile: null, score100: null,
        gapBest: null, gapMedian: null, deltaExternal: null, scenarioKey: '通用',
        computedAt: '2026-10-16T07:00:00',
      },
      {
        id: 2, source: 'external_import', publishedTaskId: null, publishedTaskVersion: null,
        reportId: null, baselineId: null, subjectName: '基线B', subjectType: 'external',
        deviceType: null, benchmarkSuite: 'librispeech-test-clean', category: 'asr',
        metricCode: 'WER', metricName: '字错误率', metricValue: 9.2, unit: '%',
        direction: 'lower_is_better', rank: 2, total: 2, percentile: null, score100: null,
        gapBest: null, gapMedian: null, deltaExternal: null, scenarioKey: '通用',
        computedAt: '2026-10-16T07:00:00',
      },
    ],
  },
}

beforeEach(() => {
  portMocks.list.mockReset()
  portMocks.getOne.mockReset()
})

describe('BenchmarkReportPanel（INT-483）', () => {
  it('反查记录并以 reportId 匹配后取详情渲染排行区块', async () => {
    portMocks.list.mockResolvedValue({ items: [RECORD], total: 1, page: 1, perPage: 100, pages: 1 })
    portMocks.getOne.mockResolvedValue(RECORD)

    const w = mount(BenchmarkReportPanel, { props: REPORT_PROPS })
    await flushPromises()

    expect(portMocks.list).toHaveBeenCalledWith({
      suite: 'librispeech-test-clean',
      category: 'asr',
      source: 'platform_test',
      perPage: 100,
    })
    expect(portMocks.getOne).toHaveBeenCalledWith(5)

    expect(w.text()).toContain('LibriSpeech 基准报告')
    expect(w.text()).toContain('librispeech-test-clean')
    expect(w.text()).toContain('语音识别（ASR）')
    expect(w.text()).toContain('参与任务')
    expect(w.text()).toContain('字错误率')
    // 双轨来源徽章
    expect(w.text()).toContain('平台实测')
    expect(w.text()).toContain('外部基线')
    // 榜单行
    expect(w.text()).toContain('模型A')
    expect(w.text()).toContain('基线B')
  })

  it('记录未匹配时展示无快照兜底态', async () => {
    portMocks.list.mockResolvedValue({ items: [], total: 0, page: 1, perPage: 100, pages: 0 })

    const w = mount(BenchmarkReportPanel, { props: REPORT_PROPS })
    await flushPromises()

    expect(w.text()).toContain('暂无')
    expect(portMocks.getOne).not.toHaveBeenCalled()
  })

  it('列表接口异常时展示错误态', async () => {
    portMocks.list.mockRejectedValue(new Error('网络异常'))

    const w = mount(BenchmarkReportPanel, { props: REPORT_PROPS })
    await flushPromises()

    expect(w.text()).toContain('网络异常')
  })
})
