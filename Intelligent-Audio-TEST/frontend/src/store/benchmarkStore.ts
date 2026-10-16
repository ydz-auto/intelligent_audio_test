import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { benchmarkPort } from '../composables/benchmark/benchmarkPort'
import { groupRankings, extractSuiteOptions } from '../composables/benchmark/groupRankings'
import type {
  BenchmarkRankingFilters,
  BenchmarkRankingGroup,
  BenchmarkRankingRow,
  MetricMappingInfo,
} from '../domain/model/benchmark'
import {
  BenchmarkSource,
  type BenchmarkSourceType,
  type BenchmarkCategoryType,
} from '../domain/enums'

/**
 * Benchmark 排行 Store —— 排行页读侧状态 + 筛选（pinia setup store）
 *
 * 职责：仅承载「Benchmark 排行页」的榜单 ReadModel 状态与筛选状态。
 * 用例编排见 composables/benchmark/benchmarkPort（直通 infrastructure）。
 * 筛选状态为页面级（非跨视图共享）；跨页持久化由 URL query 承担（视图层读写）。
 */
export const useBenchmarkStore = defineStore('benchmark', () => {
  // ===== ReadModel 状态 =====
  const rows = ref<BenchmarkRankingRow[]>([])
  const mappings = ref<MetricMappingInfo[]>([])
  const subjects = ref<string[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const computing = ref(false)

  // ===== 筛选状态（camelCase Domain） =====
  const suite = ref<string>('')
  const category = ref<'' | BenchmarkCategoryType>('')
  const metricCode = ref<string>('')
  const source = ref<'' | BenchmarkSourceType>('')
  const subjectName = ref<string>('')

  /** 归一化筛选契约（null = 未启用该维） */
  const filters = computed<BenchmarkRankingFilters>(() => ({
    suite: suite.value || null,
    category: category.value || null,
    metricCode: metricCode.value || null,
    source: (source.value || null) as BenchmarkSourceType | null,
    subjectName: subjectName.value || null,
  }))

  /** 分组后的榜单（category×metric×scenario） */
  const groups = computed<BenchmarkRankingGroup[]>(() => groupRankings(rows.value))

  /** 测试集选项（当前数据去重） */
  const suiteOptions = computed<string[]>(() => extractSuiteOptions(rows.value))

  /** 指标选项（映射清单：显示 metric_name，值 metric_code） */
  const metricOptions = computed<MetricMappingInfo[]>(() => mappings.value)

  /** 任一筛选非默认 */
  const hasActiveFilters = computed<boolean>(
    () => !!suite.value || !!category.value || !!metricCode.value || !!source.value || !!subjectName.value,
  )

  // ===== 动作 =====

  /** 拉取排行（当前筛选条件）；错误收敛到 error，不抛出（页面错误态渲染） */
  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const result = await benchmarkPort.getRanking(filters.value)
      rows.value = result.items
    } catch (e: any) {
      error.value = e?.message || '查询排行失败，请稍后重试'
    } finally {
      loading.value = false
    }
  }

  /** 拉取指标映射清单（指标筛选下拉；失败静默退化，不打断页面） */
  async function loadMappings(): Promise<void> {
    try {
      mappings.value = await benchmarkPort.getMetricMappings(true)
    } catch {
      // 映射接口失败时指标下拉退化为纯文本（INT-359 §4.3 容错口径）
      mappings.value = []
    }
  }

  /** 拉取被测主体去重清单（主体搜索联想；失败静默） */
  async function loadSubjects(): Promise<void> {
    try {
      subjects.value = await benchmarkPort.getRankingSubjects(suite.value || null)
    } catch {
      subjects.value = []
    }
  }

  /** 重算排行（同步接口；成功/失败 toast 由视图层处理，此处收敛状态） */
  async function computeRanking(): Promise<{ ok: boolean; message: string }> {
    computing.value = true
    try {
      await benchmarkPort.computeRanking(suite.value || null, category.value || null, source.value || null)
      return { ok: true, message: '排行计算完成' }
    } catch (e: any) {
      return { ok: false, message: e?.message || '排行计算失败' }
    } finally {
      computing.value = false
    }
  }

  /** 重置全部筛选（触发视图层 load） */
  function resetFilters(): void {
    suite.value = ''
    category.value = ''
    metricCode.value = ''
    source.value = ''
    subjectName.value = ''
  }

  return {
    // state
    rows,
    mappings,
    subjects,
    loading,
    error,
    computing,
    // filters
    suite,
    category,
    metricCode,
    source,
    subjectName,
    filters,
    // derived
    groups,
    suiteOptions,
    metricOptions,
    hasActiveFilters,
    // actions
    load,
    loadMappings,
    loadSubjects,
    computeRanking,
    resetFilters,
  }
})

/** 排行数据来源筛选选项（下拉：全部来源 / 平台实测 / 外部基线） */
export const BENCHMARK_SOURCE_OPTIONS: Array<{ label: string; value: '' | BenchmarkSourceType }> = [
  { label: '全部来源', value: '' },
  { label: '平台实测', value: BenchmarkSource.PLATFORM_TEST },
  { label: '外部基线', value: BenchmarkSource.EXTERNAL_IMPORT },
]
