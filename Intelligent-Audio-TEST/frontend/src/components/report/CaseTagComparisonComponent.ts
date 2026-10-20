/**
 * 标签对比区块 composable（useCaseTagComparison）
 *
 * Presentation 层：只消费 camelCase Domain（adapter 出口），内存矩阵为本地结构。
 * 筛选查询（searchCases / getCaseAveragesByFilters）走 reportsPort（Application Port），
 * 请求参数使用 camelCase（searchCases 内部双拼写归一化后转 snake_case 发后端）。
 */
import type {
  Report,
  ReportMetricConfig as MetricConfigItem,
  MetricMatrix as TagMetricMatrix,
  ComparisonColumn as TagColumn,
} from '../../domain'
import { ref, computed, watch } from 'vue'
import { reportsPort } from '@/composables/report/reportsPort'
import { useCollapse, useMetricCollapse, useTableRefs, useDisplayTypes, useSaveSummary, useResourceHeaders, chartColors, chartBorderColors, generateDistributionChartData, toggle as toggleSelection, usePaginatedSelection } from './shared/useReportShared'
import { extractInitialTagMetricData, createTagChartData } from './caseTagComparisonHelpers'
import { createResourceLabelGetter, createTagMetricValueGetters } from './caseTagResourceHelpers'
import { usePagination } from '../../composables/usePagination'

/** 标签对比组件 props（reportData 由父组件注入的 Report Domain） */
interface CaseTagComparisonProps {
  reportData?: Report | null
}

/** 从 Report Domain 读取标签列表（adapter 出口 summary.allCaseTags） */
function getTags(data: Report | null | undefined): string[] {
  const raw = data?.summary?.allCaseTags ?? []
  if (!Array.isArray(raw)) return []
  return raw.map((tag: string) => String(tag))
}

/** 从 Report Domain 读取分类列表（adapter 出口 summary.caseCategories） */
function getCategories(data: Report | null | undefined): string[] {
  const raw = data?.summary?.caseCategories ?? []
  if (!Array.isArray(raw)) return []
  return raw.map((cat: string) => String(cat))
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

/** 标签维度归一：兼容字符串与 {name} 对象 */
function toTagName(tag: string | { name?: string }): string {
  return typeof tag === 'string' ? tag : (tag?.name || '')
}

export function useCaseTagComparison(props: CaseTagComparisonProps) {
  // Collapse state
  const { isCollapsed, toggleCollapse } = useCollapse()

  // 评估维度折叠状态
  const { collapsedMetrics, toggleMetricCollapse } = useMetricCollapse()

  // 表格引用
  const { tableRefs, setTableRef } = useTableRefs()

  // Data
  const allTags = ref<string[]>(getTags(props.reportData))
  const caseCategories = ref<string[]>(getCategories(props.reportData))

  // 分类：搜索 + 分页 + 选择（消费 usePaginatedSelection）
  const {
    searchQuery: categorySearchQuery,
    page: categoryPage,
    pageSize: categoryPageSize,
    selected: selectedCategories,
    filtered: filteredCategoriesForSelection,
    totalPages: totalCategoryPages,
    paginated: paginatedCategories,
  } = usePaginatedSelection<string>(() => caseCategories.value, 50)

  // 标签：搜索 + 分页 + 选择（消费 usePaginatedSelection）
  const {
    searchQuery: tagSearchQuery,
    page: tagPage,
    pageSize,
    selected: selectedTags,
    filtered: availableTagsForSelection,
    totalPages: totalTagPages,
    paginated: paginatedTags,
  } = usePaginatedSelection<string>(() => allTags.value, 50)

  // Metrics configuration（adapter 出口为 camelCase：name/decimalPlaces）
  const allMetrics = ref<MetricConfigItem[]>(readAllMetrics(props.reportData))

  const selectedMetrics = ref<string[]>([])

  // Search and pagination for metrics
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

  // 维度分页：使用通用分页 composable
  const { totalPages: totalMetricPages, paginatedItems: paginatedMetrics } = usePagination<MetricConfigItem>(filteredMetricsForDisplay, metricPageSize, { currentPage: metricPage })

  // 聚合展示精度由聚合代码（后端 round 4 位）决定，统一保留 2 位小数展示；
  // 不再读取维度 decimal_places（INT-364 对齐 V9.7.10 f02ba75e），
  // decimal_places 仅用于具体用例卡片（TestCaseReportDetail）。
  const formatMetricForDisplay = (metricName: string, value: unknown) => {
    if (value === '-' || value === null || value === undefined) return '-'
    const num = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(num)) return String(value)
    return num.toFixed(2)
  }

  // 同时使用设备和API作为资源
  const devices = ref<string[]>(getValidResources(props.reportData))

  // 使用ref管理内部tagMetricData状态
  const tagMetricData = ref<TagMetricMatrix>({})

  // 初始化和更新数据的函数
  const updateData = (reportData: Report | null | undefined) => {
    const report = reportData ?? null
    const summary = report?.summary

    // 标签来源：allTags + allCaseTags（adapter 出口 camelCase）
    const tagsRaw = [...(summary?.allTags ?? []), ...(summary?.allCaseTags ?? [])]
    const tags = tagsRaw.map(tag => String(tag))

    const extractedTagMetricData = extractInitialTagMetricData(report) || {}

    const extractedTags = Object.keys(extractedTagMetricData)

    // detailedResults（Report 顶层或 summary，adapter 输出 camelCase）
    let detailedTags: string[] = []
    const detailedResults = report?.detailedResults ?? summary?.detailedResults
    if (Array.isArray(detailedResults)) {
      detailedResults.forEach(result => {
        const caseTags = result?.testCase?.tags
        if (Array.isArray(caseTags)) {
          detailedTags = [...detailedTags, ...caseTags.map(tag => toTagName(tag as string | { name?: string }))]
        }
      })

      const hasUntaggedCase = detailedResults.some(r => {
        const tagsOfCase = r?.testCase?.tags
        return !Array.isArray(tagsOfCase) || tagsOfCase.length === 0
      })
      if (hasUntaggedCase) detailedTags = [...detailedTags, '未标记']
    }

    const mergedTags = [...new Set([...tags, ...extractedTags, ...detailedTags])]

    allTags.value = mergedTags;

    // 分类来源：caseCategories（adapter 出口 camelCase）
    const mappedCategories = (summary?.caseCategories ?? []).map(cat => String(cat))
    if (Array.isArray(detailedResults)) {
      const hasUncategorized = detailedResults.some(r => !r?.testCaseGroup)
      if (hasUncategorized && !mappedCategories.includes('未分类')) mappedCategories.push('未分类')
    }
    caseCategories.value = mappedCategories

    allMetrics.value = readAllMetrics(report)
    tagMetricData.value = extractedTagMetricData
    devices.value = getValidResources(report)

    selectedTags.value = []
    selectedCategories.value = []
    selectedMetrics.value = []
  };

  // 初始化数据
  updateData(props.reportData);

  // 监听reportData变化，更新内部状态
  watch(() => props.reportData, (newReportData) => {
    updateData(newReportData);
  }, { deep: true })

  const { displayTypes, activeDisplayType } = useDisplayTypes()

  // Computed
  const { reportId, scheduleSaveSummary } = useSaveSummary(props as { reportData?: unknown }, 'CaseTagComparison')

  const { resourceHeaderMap } = useResourceHeaders(props)

  const { getResourceLabel } = createResourceLabelGetter(resourceHeaderMap)

  const editingResourceKey = ref<string | null>(null)
  const editingResourceValue = ref('')

  const startEditResource = (resourceKey: string) => {
    editingResourceKey.value = resourceKey
    editingResourceValue.value = String(getResourceLabel(resourceKey) ?? '')
  }

  const commitEditResource = (resourceKey: string) => {
    if (editingResourceKey.value !== resourceKey) return
    const next = String(editingResourceValue.value ?? '').trim()
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

  const editingTagKey = ref<string | null>(null)
  const editingTagValue = ref('')

  const startEditTag = (tagName: string) => {
    editingTagKey.value = tagName
    editingTagValue.value = String(tagName ?? '')
  }

  const commitEditTag = (oldName: string, newName?: string) => {
    const next = newName || String(editingTagValue.value ?? '').trim()
    editingTagKey.value = null
    editingTagValue.value = ''
    if (!next || next === oldName) return

    if (tagMetricData.value && tagMetricData.value[oldName] && !tagMetricData.value[next]) {
      tagMetricData.value[next] = tagMetricData.value[oldName]
      delete tagMetricData.value[oldName]
    }
    allTags.value = allTags.value.map(t => (t === oldName ? next : t))
    selectedTags.value = selectedTags.value.map(t => (t === oldName ? next : t))

    // allCaseTags 为 camelCase Domain 字段（string[]：重命名 = 数组元素替换）
    const tagsList = props.reportData?.summary?.allCaseTags ?? []
    if (Array.isArray(tagsList)) {
      const index = tagsList.indexOf(oldName)
      if (index >= 0) tagsList[index] = next
    }
    scheduleSaveSummary({ allCaseTags: tagsList, allTags: tagsList })
  }

  const processedDevices = computed(() => {
    return devices.value.map(device => String(getResourceLabel(device) ?? ''))
  })

  const filteredTags = computed(() => {
    if (selectedTags.value.length === 0) {
      return allTags.value
    }
    return selectedTags.value
  })

  // 根据selectedCategories过滤标签数据
  const filteredTagMetricData = computed<TagMetricMatrix>(() => {
    const selectedTagSet = new Set(selectedTags.value || [])
    const useTagFilter = selectedTagSet.size > 0
    const useCategoryFilter = selectedCategories.value.length > 0

    if (!useTagFilter && !useCategoryFilter) {
      return tagMetricData.value
    }

    const filteredData: TagMetricMatrix = {}
    const data = tagMetricData.value || {}

    if (useTagFilter) {
      for (const [tag, resources] of Object.entries(data)) {
        if (selectedTagSet.has(tag)) {
          filteredData[tag] = resources
        }
      }
    } else {
      Object.assign(filteredData, data)
    }

    return filteredData
  })

  const filteredMetrics = computed(() => {
    if (selectedMetrics.value.length === 0) {
      return allMetrics.value
    }
    return allMetrics.value.filter(m => selectedMetrics.value.includes(m.name))
  })

  // Methods
  const toggleTag = (tagName: string) => {
    toggleSelection(selectedTags, tagName)
    applyFilters()
  }

  const toggleCategory = (category: string) => {
    toggleSelection(selectedCategories, category)
    applyFilters()
  }

  const toggleMetric = (metricName: string) => {
    toggleSelection(selectedMetrics, metricName)
  }

  const resetFilters = () => {
    selectedTags.value = []
    selectedCategories.value = []
    selectedMetrics.value = []
    categorySearchQuery.value = ''
    categoryPage.value = 1
    tagSearchQuery.value = ''
    tagPage.value = 1
    metricSearchQuery.value = ''
    metricPage.value = 1
    applyFilters()
  }

  const applyFilters = async () => {
    try {
      const report = props.reportData
      const reportIdValue = report?.id

      if (reportIdValue) {
        // 对比/二次对比报告：走后端聚合（reportId → 源任务集合 → 策略聚合，
        // INT-1059 对齐 0c6b2028a），不再前端手写聚合
        const result = await reportsPort.getCaseAveragesByFilters(reportIdValue, {
          tags: selectedTags.value,
          categories: selectedCategories.value
        }, {}, true)

        const extractedFromApi = extractInitialTagMetricData(result);
        if (extractedFromApi && Object.keys(extractedFromApi).length > 0) {
          tagMetricData.value = extractedFromApi;
          return;
        }
      }

      const taskId = report?.taskId
      if (taskId) {
        const result = await reportsPort.getCaseAveragesByFilters(taskId, {
          tags: selectedTags.value,
          categories: selectedCategories.value
        });

        const extractedFromApi = extractInitialTagMetricData(result);
        if (extractedFromApi && Object.keys(extractedFromApi).length > 0) {
          tagMetricData.value = extractedFromApi;
          return;
        }
      }
    } catch (error) {
      console.error('调用API失败:', error);
    }
  }

  const { getMetricValue, getRawDataValue } = createTagMetricValueGetters({ filteredTagMetricData })

  const getMetricDisplayValue = (tag: string, device: string, metricName: string) => {
    return formatMetricForDisplay(metricName, getMetricValue(tag, device, metricName))
  }

  const getMetricUnit = (metricName: string) => {
    const metric = allMetrics.value.find(m => m.name === metricName)
    return metric?.unit || ''
  }

  // 生成表格列配置
  const getTableColumns = (metricName: string): TagColumn[] => {
    const unit = getMetricUnit(metricName)
    const columns: TagColumn[] = [
      {
        key: 'tag',
        label: '用例标签',
        editable: true,
        resize: true,
        class: 'tag-column'
      }
    ]

    devices.value.forEach((device, index) => {
      columns.push({
        key: `device-${index}`,
        label: processedDevices.value[index] ?? '',
        editable: true,
        resize: true,
        class: 'device-column',
        color: 'var(--secondary)',
        unit: unit
      })
    })

    return columns
  }

  // 生成表格数据
  const getTableData = (metricName: string): Record<string, string>[] => {
    return filteredTags.value.map(tag => {
      const row: Record<string, string> = {
        tag: tag
      }

      devices.value.forEach((device, index) => {
        row[`device-${index}`] = getMetricDisplayValue(tag, device, metricName)
      })

      return row
    })
  }

  // 处理表头保存
  const handleHeaderSave = ({ column, value, originalValue }: { column: unknown; value: string; originalValue: string }) => {
    if (column === 'tag' && value !== originalValue) {
      commitEditTag(originalValue, value)
    } else if (typeof column === 'string' && column.startsWith('device-')) {
      const index = parseInt(column.split('-')[1] ?? '', 10)
      const device = devices.value[index]
      if (device && value !== originalValue) {
        editingResourceKey.value = device
        editingResourceValue.value = value
        commitEditResource(device)
      }
    }
  }

  // 处理单元格保存
  const handleCellSave = ({ column, value, originalValue }: { column: unknown; value: string; originalValue: string }) => {
    if (column === 'tag' && value !== originalValue) {
      commitEditTag(originalValue, value)
    }
  }

  // 处理行头（用例标签）单元格点击
  const handleTagCellClick = (metricName: string, rowIndex: number, colIndex: number, row?: unknown) => {
    const tableRef = tableRefs.value[metricName]
    if (tableRef) {
      tableRef.startEditCell(rowIndex, colIndex)
    }
    void row
  }

  // 使用提取的 getChartData
  const { getChartData } = createTagChartData({
    activeDisplayType,
    devices,
    filteredTags,
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
    // Tags
    selectedTags,
    tagSearchQuery,
    paginatedTags,
    toggleTag,
    filteredTags,
    tagPage,
    pageSize,
    totalTagPages,
    // Categories
    selectedCategories,
    categorySearchQuery,
    paginatedCategories,
    toggleCategory,
    filteredCategoriesForSelection,
    categoryPage,
    categoryPageSize,
    totalCategoryPages,
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
    handleTagCellClick,
    // Chart
    getChartData
  }
}
