/**
 * 分类对比区块 composable（useCaseCategoryComparison）
 *
 * Presentation 层：只消费 camelCase Domain（adapter 出口），内存矩阵为本地结构。
 * 筛选查询（searchCases / getCaseAveragesByFilters）走 reportsPort（Application Port），
 * 请求参数使用 camelCase（searchCases 内部双拼写归一化后转 snake_case 发后端）。
 */
import type {
  Report,
  ReportMetricConfig as MetricConfigItem,
  MetricMatrix as CategoryMetricMatrix,
  ComparisonColumn as CategoryColumn,
} from '../../domain'
import { ref, computed, watch, type Ref } from 'vue'
import { reportsPort } from '@/composables/report/reportsPort'
import { useCollapse, useMetricCollapse, useTableRefs, useDisplayTypes, useSaveSummary, useResourceHeaders, chartColors, chartBorderColors, generateDistributionChartData, toggle as toggleSelection, usePaginatedSelection } from './shared/useReportShared'
import { extractInitialMetricData, computeMetricDataFromCases, createCategoryChartData, createCategoryMetricValueGetters } from './caseCategoryComparisonHelpers'
import { createResourceLabelGetter } from './caseTagResourceHelpers'
import { usePagination } from '../../composables/usePagination'

/** 分类对比组件 props（reportData 由父组件注入的 Report Domain） */
interface CaseCategoryComparisonProps {
  reportData?: Report | null
}

/** 表头保存事件载荷 */
interface HeaderSavePayload {
  colIndex: number
  value: string
  column?: { key: string; label: string }
}

/** 单元格保存事件载荷 */
interface CellSavePayload {
  rowIndex: number
  colIndex: number
  value: string
}

/** 从 Report Domain 读取分类列表（adapter 出口 summary.caseCategories） */
function getCategories(data: Report | null | undefined): string[] {
  const raw = data?.summary?.caseCategories ?? []
  if (!Array.isArray(raw)) return []
  return raw.map((cat: string) => String(cat))
}

/** 从 Report Domain 读取标签列表（adapter 出口 summary.allCaseTags） */
function getTags(data: Report | null | undefined): string[] {
  const raw = data?.summary?.allCaseTags ?? []
  if (!Array.isArray(raw)) return []
  return raw.map((tag: string) => String(tag))
}

/** 资源列表优先级：summary.resources → apis → devices（adapter 出口 camelCase） */
function getValidResources(data: Report | null | undefined): string[] {
  if (!data) return []
  const candidates = [data.summary?.resources, data.summary?.apis, data.summary?.devices]
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return candidate.map((item: string | { name: string }) => typeof item === 'object' && item !== null ? item.name : String(item))
    }
  }
  return []
}

/** 指标配置列表读取（adapter 出口 summary.allMetrics） */
function readAllMetrics(data: Report | null | undefined): MetricConfigItem[] {
  const raw = data?.summary?.allMetrics
  return Array.isArray(raw) ? raw : []
}

export function useCaseCategoryComparison(props: CaseCategoryComparisonProps) {
  // Collapse state
  const { isCollapsed, toggleCollapse } = useCollapse()

  // 评估维度折叠状态
  const { collapsedMetrics, toggleMetricCollapse } = useMetricCollapse()

  // 表格引用
  const { tableRefs, setTableRef } = useTableRefs()

  // Data
  const allAvailableCategories = ref<string[]>(getCategories(props.reportData))
  const allAvailableTags = ref<string[]>(getTags(props.reportData))

  const caseNameSearchQuery = ref('')

  // 分类：搜索 + 分页 + 选择（消费 usePaginatedSelection）
  const {
    searchQuery: categorySearchQuery,
    page: categoryPage,
    pageSize: categoryPageSize,
    selected: selectedCategories,
    filtered: filteredCategoriesForSelection,
    totalPages: totalCategoryPages,
    paginated: paginatedCategories,
  } = usePaginatedSelection<string>(() => allAvailableCategories.value, 50)

  // 标签：搜索 + 分页 + 选择（消费 usePaginatedSelection）
  const {
    searchQuery: tagSearchQuery,
    page: tagPage,
    pageSize: tagPageSize,
    selected: selectedTags,
    filtered: filteredTagsForSelection,
    totalPages: totalTagPages,
    paginated: paginatedTags,
  } = usePaginatedSelection<string>(() => allAvailableTags.value, 50)

  // Metrics configuration（adapter 出口为 camelCase：name/decimalPlaces）
  const allMetrics = ref<MetricConfigItem[]>(readAllMetrics(props.reportData))

  const selectedMetrics = ref<string[]>([])

  // 指标：搜索 + 分页（源为对象数组，选择为 name 字符串，不兼容 usePaginatedSelection）
  const metricSearchQuery = ref('')
  const metricPage = ref(1)
  const metricPageSize = ref(30)

  const filteredMetricsForDisplay = computed(() => {
    if (!metricSearchQuery.value.trim()) {
      return allMetrics.value
    }
    const query = metricSearchQuery.value.toLowerCase()
    return allMetrics.value.filter(metric => metric.name.toLowerCase().includes(query))
  })

  // 使用通用分页 composable 统一处理指标选择分页
  const {
    totalPages: totalMetricPages,
    paginatedItems: paginatedMetrics,
  } = usePagination<MetricConfigItem>(filteredMetricsForDisplay, metricPageSize, { currentPage: metricPage })

  // 指标小数位映射（camelCase 字段 decimalPlaces）
  const metricDecimalPlacesMap = computed<Record<string, number>>(() => {
    const map: Record<string, number> = {}
    allMetrics.value.forEach(m => {
      if (!m || !m.name) return
      const dp = m.decimalPlaces
      if (Number.isInteger(dp) && dp !== null && dp !== undefined && dp >= 0) map[m.name] = dp
    })
    return map
  })

  const formatMetricForDisplay = (metricName: string, value: unknown) => {
    if (value === '-' || value === null || value === undefined) return '-'
    const num = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(num)) return String(value)
    const dp = metricDecimalPlacesMap.value[String(metricName)]
    if (Number.isInteger(dp) && dp >= 0) return num.toFixed(dp)
    return String(num)
  }

  // 同时使用设备和API作为资源
  const devices = ref<string[]>(getValidResources(props.reportData))

  // 使用ref管理内部metricData状态
  const metricData = ref<CategoryMetricMatrix>(extractInitialMetricData(props.reportData))

  // 监听reportData变化，更新内部状态
  watch(() => props.reportData, (newReportData) => {
    console.log('[CaseCategoryComparisonComponent] reportData变化:', newReportData)
    allAvailableCategories.value = getCategories(newReportData)
    allAvailableTags.value = getTags(newReportData)
    allMetrics.value = readAllMetrics(newReportData)
    metricData.value = extractInitialMetricData(newReportData)
    devices.value = getValidResources(newReportData)

    selectedCategories.value = []
    selectedTags.value = []
    selectedMetrics.value = []
  }, { deep: true })

  // Display types
  const { displayTypes, activeDisplayType } = useDisplayTypes()

  // Computed
  const filteredCategories = computed(() => {
    if (selectedCategories.value.length === 0) {
      return allAvailableCategories.value
    }
    return selectedCategories.value
  })

  const filteredMetrics = computed(() => {
    if (selectedMetrics.value.length === 0) {
      return allMetrics.value
    }
    return allMetrics.value.filter(m => selectedMetrics.value.includes(m.name))
  })

  const { reportId, scheduleSaveSummary } = useSaveSummary(props as { reportData?: unknown }, 'CaseCategoryComparison')

  const { resourceHeaderMap } = useResourceHeaders(props)

  const { getResourceLabel } = createResourceLabelGetter(resourceHeaderMap)

  const editingResourceKey = ref<string | null>(null)
  const editingResourceValue = ref('')

  const startEditResource = (resourceKey: string) => {
    editingResourceKey.value = resourceKey
    editingResourceValue.value = String(getResourceLabel(resourceKey) ?? '')
  }

  const commitEditResource = (resourceKey: string, newValue?: string) => {
    const next = newValue !== undefined ? String(newValue ?? '').trim() : String(editingResourceValue.value ?? '').trim()
    if (editingResourceKey.value !== resourceKey && newValue === undefined) return
    editingResourceKey.value = null
    if (!next) return

    // resourceHeaders 为 camelCase Domain 字段（ReportResourceHeader.key/label）
    const headers = props.reportData?.summary?.resourceHeaders ?? []
    if (Array.isArray(headers)) {
      const target = headers.find(h => h && h.key === resourceKey)
      if (target) {
        target.label = next
      }
    }
    scheduleSaveSummary({ resourceHeaders: headers })
  }

  const editingCategoryKey = ref<string | null>(null)
  const editingCategoryValue = ref('')

  const startEditCategory = (categoryName: string) => {
    editingCategoryKey.value = categoryName
    editingCategoryValue.value = String(categoryName ?? '')
  }

  const commitEditCategory = (oldName: string, newValue?: string) => {
    const next = newValue !== undefined ? String(newValue ?? '').trim() : String(editingCategoryValue.value ?? '').trim()
    if (editingCategoryKey.value !== oldName && newValue === undefined) return
    editingCategoryKey.value = null
    if (!next || next === oldName) return

    if (metricData.value && metricData.value[oldName] && !metricData.value[next]) {
      metricData.value[next] = metricData.value[oldName]
      delete metricData.value[oldName]
    }
    allAvailableCategories.value = allAvailableCategories.value.map(c => (c === oldName ? next : c))
    selectedCategories.value = selectedCategories.value.map(c => (c === oldName ? next : c))

    // caseCategories 为 camelCase Domain 字段（string[]：重命名 = 数组元素替换）
    const cats = props.reportData?.summary?.caseCategories ?? []
    if (Array.isArray(cats)) {
      const index = cats.indexOf(oldName)
      if (index >= 0) cats[index] = next
    }
    scheduleSaveSummary({ caseCategories: cats })
  }

  const processedDevices = computed(() => {
    return devices.value.map(device => String(getResourceLabel(device) ?? ''))
  })

  // Methods
  const toggleCategory = (category: string) => {
    toggleSelection(selectedCategories, category)
    applyFilters()
  }

  const toggleTag = (tag: string) => {
    toggleSelection(selectedTags, tag)
    applyFilters()
  }

  const toggleMetric = (metricName: string) => {
    toggleSelection(selectedMetrics, metricName)
  }

  // 重置筛选条件
  const resetFilters = () => {
    selectedCategories.value = []
    selectedTags.value = []
    selectedMetrics.value = []
    caseNameSearchQuery.value = ''
    categorySearchQuery.value = ''
    categoryPage.value = 1
    tagSearchQuery.value = ''
    tagPage.value = 1
    metricSearchQuery.value = ''
    metricPage.value = 1
    applyFilters()
  }

  // 应用筛选条件
  const applyFilters = async () => {
    try {
      const selectedTagList = selectedTags.value || []
      const includeUntagged = selectedTagList.includes('无标签') || selectedTagList.includes('未标记')
      const normalizedTags = selectedTagList.filter(t => t !== '无标签' && t !== '未标记')

      const report = props.reportData
      // taskId（聚合根为 camelCase）
      const taskId = report?.taskId

      if (taskId) {
        const result = await reportsPort.getCaseAveragesByFilters(taskId, {
          tags: normalizedTags,
          includeUntagged,
          categories: selectedCategories.value
        })

        metricData.value = extractInitialMetricData(result)
        return
      }

      const reportIdValue = report?.id
      if (reportIdValue) {
        const body = {
          page: 1,
          perPage: 5000,
          tags: normalizedTags,
          includeUntagged,
          category: (selectedCategories.value || []).length === 1 ? selectedCategories.value[0] : null
        }

        const res = await reportsPort.searchCases(reportIdValue, body)
        const cases = res?.items || []
        metricData.value = computeMetricDataFromCases(cases, {
          selectedCategories,
          selectedTags,
          allAvailableCategories,
          allAvailableTags
        })
        return
      }
    } catch (error) {
      console.error('调用API失败:', error)
    }
  }

  // 使用提取的 getMetricValue/getRawDataValue
  const { getMetricValue, getRawDataValue } = createCategoryMetricValueGetters({ metricData })

  const getMetricDisplayValue = (category: string, device: string, metricName: string) => {
    return formatMetricForDisplay(metricName, getMetricValue(category, device, metricName))
  }

  const getMetricUnit = (metricName: string) => {
    const metric = allMetrics.value.find(m => m.name === metricName)
    return metric?.unit || ''
  }

  const getTableColumns = (metricName: string): CategoryColumn[] => {
    const unit = getMetricUnit(metricName)
    const columns: CategoryColumn[] = [
      {
        key: 'category',
        label: '用例分组',
        editable: true,
        resize: true,
        class: 'category-column'
      }
    ]

    devices.value.forEach((device, index) => {
      columns.push({
        key: `device-${index}`,
        label: processedDevices.value[index] ?? '',
        editable: true,
        resize: true,
        class: 'device-column',
        color: '#1677ff',
        unit: unit
      })
    })

    return columns
  }

  const getTableData = (metricName: string): Record<string, string>[] => {
    return filteredCategories.value.map(category => {
      const row: Record<string, string> = {
        category: category
      }

      devices.value.forEach((device, index) => {
        row[`device-${index}`] = getMetricDisplayValue(category, device, metricName)
      })

      return row
    })
  }

  const handleHeaderSave = ({ colIndex, value, column }: HeaderSavePayload) => {
    if (colIndex === 0) {
      if (column && column.key === 'category') {
        const oldName = column.label
        if (value !== oldName) {
          commitEditCategory(oldName, value)
        }
      }
      return
    }
    const deviceIndex = colIndex - 1
    if (deviceIndex >= 0 && deviceIndex < devices.value.length) {
      const device = devices.value[deviceIndex]
      commitEditResource(device, value)
    }
  }

  const handleCellSave = ({ rowIndex, colIndex, value }: CellSavePayload) => {
    if (colIndex === 0) {
      const category = filteredCategories.value[rowIndex]
      if (category) {
        commitEditCategory(category, value)
      }
    }
  }

  const handleCategoryCellClick = (metricName: string, rowIndex: number, colIndex: number, row?: unknown) => {
    const tableRef = tableRefs.value[metricName]
    if (tableRef) {
      tableRef.startEditCell(rowIndex, colIndex)
    }
    void row
  }

  // 使用提取的 getChartData
  const { getChartData } = createCategoryChartData({
    activeDisplayType,
    devices,
    filteredCategories,
    getRawDataValue,
    getMetricValue,
    getResourceLabel,
    generateDistributionChartData,
    chartColors,
    chartBorderColors
  })

  return {
    // Collapse
    isCollapsed,
    toggleCollapse,
    // Metric collapse
    collapsedMetrics,
    toggleMetricCollapse,
    // Table refs
    setTableRef,
    // Case name search
    caseNameSearchQuery,
    // Categories
    selectedCategories,
    categorySearchQuery,
    paginatedCategories,
    toggleCategory,
    filteredCategoriesForSelection,
    categoryPage,
    categoryPageSize,
    totalCategoryPages,
    // Tags
    selectedTags,
    tagSearchQuery,
    paginatedTags,
    toggleTag,
    filteredTagsForSelection,
    tagPage,
    tagPageSize,
    totalTagPages,
    // Metrics
    selectedMetrics,
    metricSearchQuery,
    paginatedMetrics,
    toggleMetric,
    filteredMetricsForDisplay,
    metricPage,
    metricPageSize,
    totalMetricPages,
    filteredMetrics,
    // Display
    displayTypes,
    activeDisplayType,
    // Table
    getTableColumns,
    getTableData,
    handleHeaderSave,
    handleCellSave,
    handleCategoryCellClick,
    // Chart
    getChartData,
    // Filters
    resetFilters,
    applyFilters
  }
}

// 模块内引用：保持 Ref 类型在接口签名中可用
export type { Ref }
