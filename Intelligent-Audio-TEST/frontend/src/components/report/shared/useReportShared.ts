/**
 * 报告组件共享 composables
 *
 * 从 SpecificCaseComparison / CaseTagComparison / CaseCategoryComparison
 * 三个组件中提取的公共逻辑。
 */
import { ref, computed } from 'vue'
import { reportsApi } from '../../../utils/api'
import { usePagination } from '../../../composables/usePagination'

/** 折叠状态（isCollapsed + toggleCollapse） */
export function useCollapse() {
  const isCollapsed = ref(false)
  const toggleCollapse = () => {
    isCollapsed.value = !isCollapsed.value
  }
  return { isCollapsed, toggleCollapse }
}

/** 维度折叠状态（collapsedMetrics + toggleMetricCollapse） */
export function useMetricCollapse() {
  const collapsedMetrics = ref<Record<string, boolean>>({})
  const toggleMetricCollapse = (metricName: string) => {
    collapsedMetrics.value[metricName] = !collapsedMetrics.value[metricName]
  }
  return { collapsedMetrics, toggleMetricCollapse }
}

/** 表格引用（tableRefs + setTableRef） */
export function useTableRefs() {
  const tableRefs = ref<Record<string, any>>({})
  const setTableRef = (metricName: string, el: any) => {
    tableRefs.value[metricName] = el
  }
  return { tableRefs, setTableRef }
}

/** 显示类型（displayTypes 常量 + activeDisplayType） */
export function useDisplayTypes() {
  const displayTypes = [
    { type: 'table', label: '表格', icon: 'fas fa-table' },
    { type: 'bar', label: '柱状图', icon: 'fas fa-chart-bar' },
    { type: 'line', label: '折线图', icon: 'fas fa-chart-line' },
    { type: 'radar', label: '雷达图', icon: 'fas fa-hexagon' },
    { type: 'distribution', label: '正态分布图', icon: 'fas fa-chart-area' }
  ]
  const activeDisplayType = ref('table')
  return { displayTypes, activeDisplayType }
}

/** 保存摘要（reportId computed + scheduleSaveSummary 防抖） */
export function useSaveSummary(props: any, logTag = 'ReportComparison') {
  const reportId = computed(() => props.reportData?.id || props.reportData?.report_id)

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  const scheduleSaveSummary = (partialSummary: any) => {
    const id = reportId.value
    if (!id) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(async () => {
      try {
        await reportsApi.update(id, { id, summary: partialSummary })
      } catch (e) {
        console.error(`[${logTag}] Failed to save header edits:`, e)
      }
    }, 200)
  }

  return { reportId, scheduleSaveSummary }
}

/** 图表颜色常量 */
export const chartColors = [
  'rgba(22, 119, 255, 0.6)',
  'rgba(255, 106, 0, 0.6)',
  'rgba(82, 196, 26, 0.6)',
  'rgba(250, 173, 20, 0.6)',
  'rgba(19, 194, 194, 0.6)',
  'rgba(114, 46, 209, 0.6)'
]

export const chartBorderColors = [
  'rgba(22, 119, 255, 1)',
  'rgba(255, 106, 0, 1)',
  'rgba(82, 196, 26, 1)',
  'rgba(250, 173, 20, 1)',
  'rgba(19, 194, 194, 1)',
  'rgba(114, 46, 209, 1)'
]

/**
 * 通用分页 composables
 * 支持搜索过滤 + 分页的列表选择器
 */
export function usePaginatedSelection<T>(
  sourceList: () => T[],
  pageSizeDefault = 50
) {
  const searchQuery = ref('')
  const page = ref(1)
  const pageSize = ref(pageSizeDefault)
  const selected = ref<T[]>([])

  const filtered = computed(() => {
    if (!searchQuery.value.trim()) return sourceList()
    const query = searchQuery.value.toLowerCase()
    const list = sourceList()
    return list.filter((item: any) =>
      String(typeof item === 'object' ? item.name : item).toLowerCase().includes(query)
    )
  })

  // 使用通用分页 composable
  const { totalPages, paginatedItems: paginated } = usePagination(filtered, pageSize, { currentPage: page })

  const toggle = (item: T) => {
    const idx = (selected.value as T[]).indexOf(item)
    if (idx > -1) {
      selected.value.splice(idx, 1)
    } else {
      selected.value.push(item as any)
    }
  }

  return {
    searchQuery,
    page,
    pageSize,
    selected,
    filtered,
    totalPages,
    paginated,
    toggle
  }
}

/**
 * 资源标签映射
 * 从 reportData 中提取 resourceHeaders 并构建 key→label 映射
 */
export function useResourceHeaders(props: any) {
  const resourceHeaderMap = computed(() => {
    const data = props.reportData || {}
    const headers =
      data.resource_headers ||
      data.summary?.resource_headers ||
      []

    const map: Record<string, string> = {}
    if (Array.isArray(headers)) {
      headers.forEach((h: any) => {
        if (!h) return
        const key = h.key || h.resource
        const label = h.label || h.name || key
        if (key) map[String(key)] = String(label || key)
      })
    }
    return map
  })

  const getResourceLabel = (resourceKey: any) => {
    const key = String(resourceKey ?? '')
    const mapped = resourceHeaderMap.value?.[key]
    if (mapped) return mapped
    return resourceKey
  }

  return { resourceHeaderMap, getResourceLabel }
}

/**
 * 维度小数位映射 + 格式化显示
 */
export function useMetricFormat(allMetrics: () => any[]) {
  const metricDecimalPlacesMap = computed(() => {
    const map: Record<string, number> = {}
    allMetrics().forEach((m: any) => {
      if (m && m.name) {
        const decimals = m.decimal_places
        if (decimals !== undefined && decimals !== null) {
          map[m.name] = Number(decimals)
        }
      }
    })
    return map
  })

  const formatMetricForDisplay = (metricName: string, value: any) => {
    if (value === null || value === undefined || value === '' || value === 'N/A') {
      return 'N/A'
    }
    const numValue = parseFloat(value)
    if (isNaN(numValue)) return String(value)

    const decimals = metricDecimalPlacesMap.value[metricName]
    if (decimals !== undefined && decimals >= 0) {
      return numValue.toFixed(decimals)
    }
    return numValue.toFixed(2)
  }

  return { metricDecimalPlacesMap, formatMetricForDisplay }
}

/**
 * 正态分布计算工具
 */
export function calculateNormalDistribution(data: number[]) {
  if (!data || data.length === 0) {
    return null
  }
  const mean = data.reduce((sum, value) => sum + value, 0) / data.length
  const variance = data.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / data.length
  const stdDev = Math.sqrt(variance)
  return { mean, stdDev, totalDataPoints: data.length }
}

/**
 * 生成正态分布图表数据
 * 供 getChartData 在 distribution 模式下调用
 */
export function generateDistributionChartData(
  devices: string[],
  deviceRawDataMap: Record<string, number[]>,
  allRawData: number[],
  getResourceLabel: (key: any) => any
) {
  const distribution = calculateNormalDistribution(allRawData)
  if (!distribution) {
    return { labels: [], datasets: [], rawData: allRawData }
  }

  const step = distribution.stdDev / 8
  let minValue = distribution.mean - 32 * step
  const maxValue = distribution.mean + 32 * step
  if (!allRawData.some(v => v < 0)) {
    minValue = 0
  }
  const intervals = Math.round((maxValue - minValue) / step)

  const chartData = {
    labels: [],
    datasets: devices.map((device, index) => {
      const color = chartColors[index % chartColors.length]
      const borderColor = chartBorderColors[index % chartBorderColors.length]
      const deviceRawData = deviceRawDataMap[device] || []
      const deviceDistribution = calculateNormalDistribution(deviceRawData)

      if (!deviceDistribution) {
        return {
          label: getResourceLabel(device),
          data: Array.from({ length: intervals }, (_, i) => ({ x: minValue + i * step, y: 0 })),
          backgroundColor: color,
          borderColor: borderColor,
          borderWidth: 1,
          fill: true,
          tension: 0.3
        }
      }

      const values = []
      for (let i = 0; i < intervals; i++) {
        const intervalStart = minValue + i * step
        const midPoint = minValue + (i + 0.5) * step
        const count = deviceRawData.filter(v =>
          i === intervals - 1 ? v >= intervalStart : v >= intervalStart && v < intervalStart + step
        ).length
        values.push({ x: parseFloat(midPoint.toFixed(2)), y: count })
      }

      return {
        label: getResourceLabel(device),
        data: values,
        backgroundColor: color,
        borderColor: borderColor,
        borderWidth: 1,
        fill: false,
        tension: 0.3,
        _step: step
      }
    }),
    rawData: allRawData,
    deviceRawData: Object.fromEntries(
      devices.map(d => [getResourceLabel(d), deviceRawDataMap[d] || []])
    )
  }

  return chartData
}
