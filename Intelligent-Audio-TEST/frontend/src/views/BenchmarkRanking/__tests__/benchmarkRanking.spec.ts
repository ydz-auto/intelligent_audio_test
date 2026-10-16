/**
 * INT-482：Benchmark 排行页（Vue 主库版）交互回归
 *
 * 覆盖验收标准②：/benchmarks 页遍历——Hero 类别页签、筛选行（测试集/指标/数据来源/
 * 搜索主体）、双轨来源数据展示与筛选联动、URL query 可还原、三态渲染。
 * 路由 meta.permission 不可达语义由 router/index.ts 断言覆盖（见文末）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const portMocks = vi.hoisted(() => ({
  getRanking: vi.fn(),
  getMetricMappings: vi.fn(),
  getRankingSubjects: vi.fn(),
  computeRanking: vi.fn(),
}))

vi.mock('@/composables/benchmark/benchmarkPort', () => ({
  benchmarkPort: portMocks,
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({
    isLoggedIn: true,
    hasPermission: (perm: string) =>
      ['benchmark:ranking:read', 'benchmark:ranking:compute', 'report:read'].includes(perm),
  }),
}))

const routerReplace = vi.fn()
// 仅替换 useRoute/useRouter（视图注入点）；createRouter/createWebHashHistory 保持原实现，
// 供真实路由表 meta.permission 断言使用（对齐 tasks.createTaskEntry.spec 模式）。
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ query: {} }),
    useRouter: () => ({ replace: routerReplace }),
  }
})

import BenchmarkRanking from '../BenchmarkRanking.vue'
import { useBenchmarkStore } from '../../../store/benchmarkStore'
import router from '../../../router'

/** 双轨来源样例：platform_test（实测，含溯源） + external_import（外部基线） */
const RANKING_ROWS = [
  {
    id: 1,
    source: 'platform_test',
    publishedTaskId: 1,
    publishedTaskVersion: 2,
    reportId: 10,
    baselineId: null,
    subjectName: 'Moshi',
    subjectType: 'open_source',
    deviceType: 'websocket_api',
    benchmarkSuite: 'full-duplex-v1',
    category: 'voice_llm',
    metricCode: 'TTLW',
    metricName: '接管时延',
    metricValue: 320,
    unit: 'ms',
    direction: 'lower_is_better',
    rank: 1,
    total: 2,
    percentile: 50,
    score100: 80,
    gapBest: 0,
    gapMedian: 5,
    deltaExternal: -10,
    scenarioKey: '通用',
    computedAt: '2026-10-16T07:00:00',
  },
  {
    id: 2,
    source: 'external_import',
    publishedTaskId: null,
    publishedTaskVersion: null,
    reportId: null,
    baselineId: 3,
    subjectName: 'Deepgram Nova',
    subjectType: 'closed_source',
    deviceType: 'http_api',
    benchmarkSuite: 'librispeech',
    category: 'asr',
    metricCode: 'WER',
    metricName: '词错误率',
    metricValue: 4.5,
    unit: '%',
    direction: 'lower_is_better',
    rank: 1,
    total: 1,
    percentile: 100,
    score100: null,
    gapBest: 0,
    gapMedian: 0,
    deltaExternal: null,
    scenarioKey: '通用',
    computedAt: '2026-10-16T07:00:00',
  },
  {
    id: 3,
    source: 'platform_test',
    publishedTaskId: 2,
    publishedTaskVersion: 1,
    reportId: 11,
    baselineId: null,
    subjectName: 'Gemini Live',
    subjectType: 'closed_source',
    deviceType: 'websocket_api',
    benchmarkSuite: 'full-duplex-v1',
    category: 'voice_llm',
    metricCode: 'TTLW',
    metricName: '接管时延',
    metricValue: 290,
    unit: 'ms',
    direction: 'lower_is_better',
    rank: 1,
    total: 2,
    percentile: 50,
    score100: 88,
    gapBest: 0,
    gapMedian: 3,
    deltaExternal: 12,
    scenarioKey: '通用',
    computedAt: '2026-10-16T07:00:00',
  },
]

const MAPPINGS = [
  { id: 1, dimensionName: 'TTLW', metricCode: 'TTLW', metricName: '接管时延', unit: 'ms', direction: 'lower_is_better', scenarioTags: [], active: true },
  { id: 2, dimensionName: 'WER', metricCode: 'WER', metricName: '词错误率', unit: '%', direction: 'lower_is_better', scenarioTags: [], active: true },
]

async function mountPage() {
  const wrapper = mount(BenchmarkRanking, {
    global: {
      plugins: [createPinia()],
      stubs: { RouterLink: true, teleport: true },
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  routerReplace.mockReset()
  portMocks.getRanking.mockResolvedValue({ items: RANKING_ROWS, total: 3, page: 1, perPage: 3, pages: 1 })
  portMocks.getMetricMappings.mockResolvedValue(MAPPINGS)
  portMocks.getRankingSubjects.mockResolvedValue(['Moshi', 'Deepgram Nova'])
})

describe('页面遍历（验收②）', () => {
  it('渲染 Hero 标题 / 副标题 / 类别下划线页签（全量中文文案）', async () => {
    const wrapper = await mountPage()
    const hero = wrapper.find('.rankings-hero')
    expect(hero.exists()).toBe(true)
    expect(hero.text()).toContain('Benchmark 排行')
    expect(hero.text()).toContain('汇聚平台实测与业界公开基线的语音能力横向对比')

    const tabs = wrapper.findAll('.category-tab')
    const labels = tabs.map((t) => t.text())
    expect(labels).toEqual(['全部', '语音识别', '语音对话', '语音合成', '翻译'])
    expect(tabs[0].classes()).toContain('active')
  })

  it('渲染筛选行（测试集 / 指标 / 数据来源 / 搜索主体 / 重置）', async () => {
    const wrapper = await mountPage()
    const filterText = wrapper.find('.ranking-filters').text()
    expect(filterText).toContain('测试集')
    expect(filterText).toContain('指标')
    expect(filterText).toContain('数据来源')
    expect(filterText).toContain('搜索主体')

    const sourceSelect = wrapper.find('.filter-select').attributes('value')
    expect(sourceSelect).toBeDefined()
  })

  it('双轨来源数据按 category×metric×scenario 分组渲染组卡（平台实测+外部基线各就位）', async () => {
    const wrapper = await mountPage()
    const cards = wrapper.findAll('.metric-group-card')
    // voice_llm/TTLW + asr/WER → 2 组
    expect(cards).toHaveLength(2)
    const texts = cards.map((c) => c.text())
    expect(texts.some((t) => t.includes('接管时延') && t.includes('Moshi'))).toBe(true)
    expect(texts.some((t) => t.includes('词错误率') && t.includes('Deepgram Nova'))).toBe(true)
    // 说明行带方向语义与主体数
    expect(texts.some((t) => t.includes('共 2 个主体参与'))).toBe(true)
  })

  it('类别页签切换 → store.load + URL query 写入 category', async () => {
    const wrapper = await mountPage()
    portMocks.getRanking.mockClear()

    const tabs = wrapper.findAll('.category-tab')
    await tabs[2].trigger('click') // 语音对话 voice_llm
    await flushPromises()

    expect(routerReplace).toHaveBeenCalledWith({ query: { category: 'voice_llm' } })
    const lastCall = portMocks.getRanking.mock.calls.at(-1)
    expect(lastCall![0].category).toBe('voice_llm')
  })

  it('数据来源筛选 → store.load + URL query 写入 source（仅 platform_test）', async () => {
    const wrapper = await mountPage()
    portMocks.getRanking.mockClear()

    // 数据来源是第三个 select（测试集/指标/数据来源）
    const selects = wrapper.findAll('.filter-select')
    const sourceSelect = selects[2]
    await sourceSelect.setValue('platform_test')
    await flushPromises()

    expect(routerReplace).toHaveBeenCalledWith(expect.objectContaining({ query: expect.objectContaining({ source: 'platform_test' }) }))
    const lastCall = portMocks.getRanking.mock.calls.at(-1)
    expect(lastCall![0].source).toBe('platform_test')
  })

  it('空态：0 行 → 「暂无排行数据」+ 立即计算（持 compute 权限）', async () => {
    portMocks.getRanking.mockResolvedValue({ items: [], total: 0, page: 1, perPage: 1, pages: 0 })
    const wrapper = await mountPage()
    const empty = wrapper.find('.empty-state')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无排行数据')
    expect(empty.text()).toContain('立即计算')
  })

  it('错误态：请求失败 → 「排行加载失败」+ 重试', async () => {
    portMocks.getRanking.mockRejectedValue(new Error('查询排行失败，请稍后重试'))
    const wrapper = await mountPage()
    const error = wrapper.find('.error-state')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('排行加载失败')
    expect(error.text()).toContain('查询排行失败，请稍后重试')
    expect(error.find('.btn-retry').exists()).toBe(true)

    // 重试成功后恢复
    portMocks.getRanking.mockResolvedValue({ items: RANKING_ROWS, total: 3, page: 1, perPage: 3, pages: 1 })
    await error.find('.btn-retry').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.metric-group-card')).toHaveLength(2)
  })
})

describe('路由 meta.permission（权限不可达语义）', () => {
  it('/benchmarks 路由要求 benchmark:ranking:read', () => {
    const route = router.getRoutes().find((r) => r.path === '/benchmarks')
    expect(route).toBeDefined()
    expect(route?.meta.permission).toBe('benchmark:ranking:read')
  })
})
