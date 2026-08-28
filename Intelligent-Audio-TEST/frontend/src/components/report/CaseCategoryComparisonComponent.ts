import { ref, computed, watch } from 'vue'
import { reportsApi } from '../../utils/api'
import { useCollapse, useMetricCollapse, useTableRefs, useDisplayTypes, useSaveSummary, useResourceHeaders, chartColors, chartBorderColors, generateDistributionChartData } from './shared/useReportShared'
import { extractInitialMetricData, computeMetricDataFromCases, createCategoryChartData, createCategoryMetricValueGetters } from './caseCategoryComparisonHelpers'
import { createResourceLabelGetter } from './caseTagResourceHelpers'

export function useCaseCategoryComparison(props) {
  // Collapse state
  const { isCollapsed, toggleCollapse } = useCollapse()

  // 评估维度折叠状态
  const { collapsedMetrics, toggleMetricCollapse } = useMetricCollapse()

  // 表格引用
  const { tableRefs, setTableRef } = useTableRefs()

  // Data
  const getCategories = (data) => {
    if (!data) return []
    const categories = data.case_categories || data.summary?.case_categories || []
    if (!Array.isArray(categories)) return []
    return categories.map(cat => typeof cat === 'object' ? cat.name : cat)
  }

  const getTags = (data) => {
    if (!data) return []
    const tags = data.all_case_tags || data.summary?.all_case_tags || []
    if (!Array.isArray(tags)) return []
    return tags.map(tag => typeof tag === 'object' ? tag.name : tag)
  }

  const allAvailableCategories = ref(getCategories(props.reportData))
  const allAvailableTags = ref(getTags(props.reportData))

  const selectedCategories = ref([])
  const selectedTags = ref([])

  const caseNameSearchQuery = ref('')

  // Search and pagination for categories
  const categorySearchQuery = ref('')
  const categoryPage = ref(1)
  const categoryPageSize = ref(50)

  const filteredCategoriesForSelection = computed(() => {
    if (!categorySearchQuery.value.trim()) {
      return allAvailableCategories.value
    }
    const query = categorySearchQuery.value.toLowerCase()
    return allAvailableCategories.value.filter(cat => cat.toLowerCase().includes(query))
  })

  const totalCategoryPages = computed(() => Math.ceil(filteredCategoriesForSelection.value.length / categoryPageSize.value) || 1)

  const paginatedCategories = computed(() => {
    const start = (categoryPage.value - 1) * categoryPageSize.value
    const end = start + categoryPageSize.value
    return filteredCategoriesForSelection.value.slice(start, end)
  })

  // Search and pagination for tags
  const tagSearchQuery = ref('')
  const tagPage = ref(1)
  const tagPageSize = ref(50)

  const filteredTagsForSelection = computed(() => {
    if (!tagSearchQuery.value.trim()) {
      return allAvailableTags.value
    }
    const query = tagSearchQuery.value.toLowerCase()
    return allAvailableTags.value.filter(tag => tag.toLowerCase().includes(query))
  })

  const totalTagPages = computed(() => Math.ceil(filteredTagsForSelection.value.length / tagPageSize.value) || 1)

  const paginatedTags = computed(() => {
    const start = (tagPage.value - 1) * tagPageSize.value
    const end = start + tagPageSize.value
    return filteredTagsForSelection.value.slice(start, end)
  })

  // Metrics configuration
  const allMetrics = ref(props.reportData.all_metrics || props.reportData.summary?.all_metrics || [])

  const selectedMetrics = ref([])

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

  const totalMetricPages = computed(() => Math.ceil(filteredMetricsForDisplay.value.length / metricPageSize.value) || 1)

  const paginatedMetrics = computed(() => {
    const start = (metricPage.value - 1) * metricPageSize.value
    const end = start + metricPageSize.value
    return filteredMetricsForDisplay.value.slice(start, end)
  })

  const metricDecimalPlacesMap = computed(() => {
    const map = {}
    const list = Array.isArray(allMetrics.value) ? allMetrics.value : []
    list.forEach(m => {
      if (!m || !m.name) return
      const dp = m.decimal_places
      if (Number.isInteger(dp) && dp >= 0) map[String(m.name)] = dp
    })
    return map
  })

  const formatMetricForDisplay = (metricName, value) => {
    if (value === '-' || value === null || value === undefined) return '-'
    const num = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(num)) return String(value)
    const dp = metricDecimalPlacesMap.value?.[String(metricName)]
    if (Number.isInteger(dp) && dp >= 0) return num.toFixed(dp)
    return String(num)
  }

  // 同时使用设备和API作为资源
  const getValidResources = (data) => {
    const resources = [
      data.resources,
      data.devices,
      data.apis,
      data.summary?.resources,
      data.summary?.apis,
      data.summary?.devices
    ];

    for (const resource of resources) {
      if (Array.isArray(resource) && resource.length > 0) {
        return resource;
      }
    }
    return [];
  };

  const devices = ref(getValidResources(props.reportData));

  // 使用ref管理内部metricData状态
  const metricData = ref(extractInitialMetricData(props.reportData));

  // 监听reportData变化，更新内部状态
  watch(() => props.reportData, (newReportData) => {
    console.log('[CaseCategoryComparisonComponent] reportData变化:', newReportData);
    allAvailableCategories.value = getCategories(newReportData)
    allAvailableTags.value = getTags(newReportData)
    allMetrics.value = newReportData.all_metrics || newReportData.summary?.all_metrics || []
    metricData.value = extractInitialMetricData(newReportData);
    devices.value = getValidResources(newReportData);

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

  const { reportId, scheduleSaveSummary } = useSaveSummary(props, 'CaseCategoryComparison')

  const { resourceHeaderMap } = useResourceHeaders(props)

  const { getResourceLabel } = createResourceLabelGetter(resourceHeaderMap)

  const editingResourceKey = ref(null)
  const editingResourceValue = ref('')

  const startEditResource = (resourceKey) => {
    editingResourceKey.value = resourceKey
    editingResourceValue.value = String(getResourceLabel(resourceKey) ?? '')
  }

  const commitEditResource = (resourceKey, newValue) => {
    const next = newValue !== undefined ? String(newValue ?? '').trim() : String(editingResourceValue.value ?? '').trim()
    if (editingResourceKey.value !== resourceKey && newValue === undefined) return
    editingResourceKey.value = null
    if (!next) return

    const report = props.reportData || {}
    const summary = report.summary || report
    const headers = summary.resource_headers || report.resource_headers || []
    if (Array.isArray(headers)) {
      const target = headers.find(h => h && (h.key === resourceKey || h.resource === resourceKey))
      if (target) {
        target.label = next
      }
    }
    scheduleSaveSummary({ resourceHeaders: headers })
  }

  const editingCategoryKey = ref(null)
  const editingCategoryValue = ref('')

  const startEditCategory = (categoryName) => {
    editingCategoryKey.value = categoryName
    editingCategoryValue.value = String(categoryName ?? '')
  }

  const commitEditCategory = (oldName, newValue) => {
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

    const report = props.reportData || {}
    const summary = report.summary || report
    const cats = summary.case_categories || report.case_categories || []
    if (Array.isArray(cats)) {
      const target = cats.find(c => c && typeof c === 'object' && c.name === oldName)
      if (target) target.name = next
    }
    scheduleSaveSummary({ caseCategories: cats })
  }

  const processedDevices = computed(() => {
    return devices.value.map(device => getResourceLabel(device))
  })

  // Methods
  const toggleCategory = (category) => {
    const index = selectedCategories.value.indexOf(category)
    if (index > -1) {
      selectedCategories.value.splice(index, 1)
    } else {
      selectedCategories.value.push(category)
    }
    applyFilters()
  }

  const toggleTag = (tag) => {
    const index = selectedTags.value.indexOf(tag)
    if (index > -1) {
      selectedTags.value.splice(index, 1)
    } else {
      selectedTags.value.push(tag)
    }
    applyFilters()
  }

  const toggleMetric = (metricName) => {
    const index = selectedMetrics.value.indexOf(metricName)
    if (index > -1) {
      selectedMetrics.value.splice(index, 1)
    } else {
      selectedMetrics.value.push(metricName)
    }
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
    console.log('应用筛选条件', {
      categories: selectedCategories.value,
      tags: selectedTags.value
    });

    try {
      const selectedTagList = selectedTags.value || []
      const includeUntagged = selectedTagList.includes('无标签') || selectedTagList.includes('未标记')
      const normalizedTags = selectedTagList.filter(t => t !== '无标签' && t !== '未标记')

      const reportData = props.reportData || {}
      const taskId =
        reportData.task_id ||
        reportData.summary?.task_id

      if (taskId) {
        const result = await reportsApi.getCaseAveragesByFilters(taskId, {
          tags: normalizedTags,
          includeUntagged,
          categories: selectedCategories.value
        });

        metricData.value = extractInitialMetricData(result);
        return
      }

      const reportId = reportData.id || reportData.report_id
      if (reportId) {
        const body = {
          page: 1,
          per_page: 5000,
          tags: normalizedTags,
          includeUntagged,
          category: (selectedCategories.value || []).length === 1 ? selectedCategories.value[0] : null
        }

        const res = await reportsApi.searchCases(reportId, body)
        const cases = res?.items || res?.data?.items || []
        metricData.value = computeMetricDataFromCases(cases, {
          selectedCategories,
          selectedTags,
          allAvailableCategories,
          allAvailableTags
        })
        return
      }
    } catch (error) {
      console.error('调用API失败:', error);
    }
  }

  // 使用提取的 getMetricValue/getRawDataValue
  const { getMetricValue, getRawDataValue } = createCategoryMetricValueGetters({ metricData })

  const getMetricDisplayValue = (category, device, metricName) => {
    return formatMetricForDisplay(metricName, getMetricValue(category, device, metricName))
  }

  const getMetricUnit = (metricName) => {
    const metric = allMetrics.value.find(m => m.name === metricName)
    return metric?.unit || ''
  }

  const getTableColumns = (metricName) => {
    const unit = getMetricUnit(metricName)
    const columns = [
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
        label: processedDevices.value[index],
        editable: true,
        resize: true,
        class: 'device-column',
        color: '#1677ff',
        unit: unit
      })
    })

    return columns
  }

  const getTableData = (metricName) => {
    return filteredCategories.value.map(category => {
      const row = {
        category: category
      }

      devices.value.forEach((device, index) => {
        row[`device-${index}`] = getMetricDisplayValue(category, device, metricName)
      })

      return row
    })
  }

  const handleHeaderSave = ({ colIndex, value, column }) => {
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

  const handleCellSave = ({ rowIndex, colIndex, value }) => {
    if (colIndex === 0) {
      const category = filteredCategories.value[rowIndex]
      if (category) {
        commitEditCategory(category, value)
      }
    }
  }

  const handleCategoryCellClick = (metricName, rowIndex, colIndex, row) => {
    const tableRef = tableRefs.value[metricName]
    if (tableRef) {
      tableRef.startEditCell(rowIndex, colIndex)
    }
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
