import { ref, computed, watch } from 'vue'
import { reportsApi } from '../../utils/api'
import { useCollapse, useMetricCollapse, useTableRefs, useDisplayTypes, useSaveSummary, useResourceHeaders, chartColors, chartBorderColors, generateDistributionChartData } from './shared/useReportShared'
import { extractInitialTagMetricData, computeTagMetricDataFromCases, createTagChartData } from './caseTagComparisonHelpers'
import { createResourceLabelGetter, createTagMetricValueGetters } from './caseTagResourceHelpers'

export function useCaseTagComparison(props) {
  // Collapse state
  const { isCollapsed, toggleCollapse } = useCollapse()

  // 评估维度折叠状态
  const { collapsedMetrics, toggleMetricCollapse } = useMetricCollapse()

  // 表格引用
  const { tableRefs, setTableRef } = useTableRefs()

  // Data
  const getTags = (data) => {
    if (!data) return []
    const tags = data.allTags || data.summary?.allTags || data.allCaseTags || data.summary?.allCaseTags || []
    if (!Array.isArray(tags)) return []
    return tags.map(tag => typeof tag === 'object' ? tag.name : tag)
  }

  const getCategories = (data) => {
    if (!data) return []
    const categories = data.caseCategories || data.summary?.caseCategories || []
    if (!Array.isArray(categories)) return []
    return categories.map(cat => typeof cat === 'object' ? cat.name : cat)
  }

  const allTags = ref(getTags(props.reportData))
  const caseCategories = ref(getCategories(props.reportData))

  const selectedTags = ref([])
  const selectedCategories = ref([])

  // Search and pagination for categories
  const categorySearchQuery = ref('')
  const categoryPage = ref(1)
  const categoryPageSize = ref(50)

  const filteredCategoriesForSelection = computed(() => {
    if (!categorySearchQuery.value.trim()) {
      return caseCategories.value
    }
    const query = categorySearchQuery.value.toLowerCase()
    return caseCategories.value.filter(cat => cat.toLowerCase().includes(query))
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
  const pageSize = ref(50)

  const availableTagsForSelection = computed(() => {
    if (!tagSearchQuery.value.trim()) {
      return allTags.value
    }
    const query = tagSearchQuery.value.toLowerCase()
    return allTags.value.filter(tag => tag.toLowerCase().includes(query))
  })

  const totalTagPages = computed(() => Math.ceil(availableTagsForSelection.value.length / pageSize.value) || 1)

  const paginatedTags = computed(() => {
    const start = (tagPage.value - 1) * pageSize.value
    const end = start + pageSize.value
    return availableTagsForSelection.value.slice(start, end)
  })

  // Metrics configuration
  const allMetrics = ref(props.reportData.allMetrics || props.reportData.summary?.allMetrics || [])

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
      const dp = m.decimalPlaces ?? m.decimal_places
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

  // 使用ref管理内部tagMetricData状态
  const tagMetricData = ref({});

  // 初始化和更新数据的函数
  const updateData = (reportData) => {
    if (!reportData) {
      reportData = {}
    }

    let tags = [
      ...(reportData.allTags || reportData.summary?.allTags || []),
      ...(reportData.allCaseTags || reportData.summary?.allCaseTags || [])
    ];

    tags = tags.map(tag => typeof tag === 'object' ? tag.name : tag);

    const extractedTagMetricData = extractInitialTagMetricData(reportData) || {};

    const extractedTags = Object.keys(extractedTagMetricData);

    let detailedTags = [];
    if (reportData.detailedResults) {
      reportData.detailedResults.forEach(result => {
        if (result.testCase?.tags) {
          const caseTags = result.testCase.tags.map(tag => typeof tag === 'object' ? tag.name : tag);
          detailedTags = [...detailedTags, ...caseTags];
        }
      });
    }

    if (reportData.detailedResults) {
      const hasUntaggedCase = reportData.detailedResults.some(r => {
        const tags = r?.testCase?.tags
        return !Array.isArray(tags) || tags.length === 0
      })
      if (hasUntaggedCase) detailedTags = [...detailedTags, '未标记']
    }

    const mergedTags = [...new Set([...tags, ...extractedTags, ...detailedTags])];

    allTags.value = mergedTags;

    const categories = reportData.caseCategories || reportData.summary?.caseCategories || [];
    const mappedCategories = categories.map(cat => typeof cat === 'object' ? cat.name : cat);
    if (reportData.detailedResults) {
      const hasUncategorized = reportData.detailedResults.some(r => !r?.testCaseGroup)
      if (hasUncategorized && !mappedCategories.includes('未分类')) mappedCategories.push('未分类')
    }
    caseCategories.value = mappedCategories;

    allMetrics.value = reportData.allMetrics || reportData.summary?.allMetrics || [];
    tagMetricData.value = extractedTagMetricData;
    devices.value = getValidResources(reportData);

    selectedTags.value = [];
    selectedCategories.value = [];
    selectedMetrics.value = [];
  };

  // 初始化数据
  updateData(props.reportData);

  // 监听reportData变化，更新内部状态
  watch(() => props.reportData, (newReportData) => {
    updateData(newReportData);
  }, { deep: true })

  const { displayTypes, activeDisplayType } = useDisplayTypes()

  // Computed
  const { reportId, scheduleSaveSummary } = useSaveSummary(props, 'CaseTagComparison')

  const { resourceHeaderMap } = useResourceHeaders(props)

  const { getResourceLabel } = createResourceLabelGetter(resourceHeaderMap)

  const editingResourceKey = ref(null)
  const editingResourceValue = ref('')

  const startEditResource = (resourceKey) => {
    editingResourceKey.value = resourceKey
    editingResourceValue.value = String(getResourceLabel(resourceKey) ?? '')
  }

  const commitEditResource = (resourceKey) => {
    if (editingResourceKey.value !== resourceKey) return
    const next = String(editingResourceValue.value ?? '').trim()
    editingResourceKey.value = null
    if (!next) return

    const report = props.reportData || {}
    const summary = report.summary || report
    const headers = summary.resourceHeaders || summary.resource_headers || report.resourceHeaders || report.resource_headers || []
    if (Array.isArray(headers)) {
      const target = headers.find(h => h && (h.key === resourceKey || h.resource === resourceKey))
      if (target) {
        target.label = next
      }
    }
    scheduleSaveSummary({ resourceHeaders: headers })
  }

  const editingTagKey = ref(null)
  const editingTagValue = ref('')

  const startEditTag = (tagName) => {
    editingTagKey.value = tagName
    editingTagValue.value = String(tagName ?? '')
  }

  const commitEditTag = (oldName, newName) => {
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

    const report = props.reportData || {}
    const summary = report.summary || report
    const tags = summary.allCaseTags || summary.all_case_tags || summary.allTags || summary.all_tags || report.allCaseTags || report.all_case_tags || []
    if (Array.isArray(tags)) {
      const target = tags.find(t => t && typeof t === 'object' && t.name === oldName)
      if (target) target.name = next
    }
    scheduleSaveSummary({ allCaseTags: tags, allTags: tags })
  }

  const processedDevices = computed(() => {
    return devices.value.map(device => getResourceLabel(device))
  })

  const filteredTags = computed(() => {
    if (selectedTags.value.length === 0) {
      return allTags.value
    }
    return selectedTags.value
  })

  // 根据selectedCategories过滤标签数据
  const filteredTagMetricData = computed(() => {
    const selectedTagSet = new Set(selectedTags.value || [])
    const selectedCategorySet = new Set(selectedCategories.value || [])
    const useTagFilter = selectedTagSet.size > 0
    const useCategoryFilter = selectedCategorySet.size > 0

    if (!useTagFilter && !useCategoryFilter) {
      return tagMetricData.value
    }

    const filteredData = {}
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
  const toggleTag = (tagName) => {
    const index = selectedTags.value.indexOf(tagName)
    if (index > -1) {
      selectedTags.value.splice(index, 1)
    } else {
      selectedTags.value.push(tagName)
    }
    applyFilters()
  }

  const toggleCategory = (category) => {
    const index = selectedCategories.value.indexOf(category)
    if (index > -1) {
      selectedCategories.value.splice(index, 1)
    } else {
      selectedCategories.value.push(category)
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
    console.log('应用筛选:', {
      selectedTags: selectedTags.value,
      selectedCategories: selectedCategories.value,
      selectedMetrics: selectedMetrics.value
    });

    try {
      const reportData = props.reportData || {}
      const reportId = reportData.id || reportData.reportId || reportData.report_id

      if (reportId) {
        const selectedTagList = selectedTags.value || []
        const includeUntagged = selectedTagList.includes('无标签') || selectedTagList.includes('未标记')
        const normalizedTags = selectedTagList.filter(t => t !== '无标签' && t !== '未标记')

        const body = {
          page: 1,
          per_page: 5000,
          tags: normalizedTags,
          includeUntagged,
          category: (selectedCategories.value || []).length === 1 ? selectedCategories.value[0] : null
        }

        const res = await reportsApi.searchCases(reportId, body)
        const cases = res?.items || res?.data?.items || []
        tagMetricData.value = computeTagMetricDataFromCases(cases, { selectedTags, selectedCategories })
        return
      }

      const taskId = reportData.taskId || reportData.summary?.taskId;
      if (taskId) {
        const result = await reportsApi.getCaseAveragesByFilters(taskId, {
          tags: selectedTags.value,
          categories: selectedCategories.value
        });

        console.log('API返回结果:', result);

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

  const getMetricDisplayValue = (tag, device, metricName) => {
    return formatMetricForDisplay(metricName, getMetricValue(tag, device, metricName))
  }

  const getMetricUnit = (metricName) => {
    const metric = allMetrics.value.find(m => m.name === metricName)
    return metric?.unit || ''
  }

  // 生成表格列配置
  const getTableColumns = (metricName) => {
    const unit = getMetricUnit(metricName)
    const columns = [
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

  // 生成表格数据
  const getTableData = (metricName) => {
    return filteredTags.value.map(tag => {
      const row = {
        tag: tag
      }

      devices.value.forEach((device, index) => {
        row[`device-${index}`] = getMetricDisplayValue(tag, device, metricName)
      })

      return row
    })
  }

  // 处理表头保存
  const handleHeaderSave = ({ column, value, originalValue }) => {
    if (column === 'tag' && value !== originalValue) {
      commitEditTag(originalValue, value)
    } else if (typeof column === 'string' && column.startsWith('device-')) {
      const index = parseInt(column.split('-')[1])
      const device = devices.value[index]
      if (device && value !== originalValue) {
        editingResourceKey.value = device
        editingResourceValue.value = value
        commitEditResource(device)
      }
    }
  }

  // 处理单元格保存
  const handleCellSave = ({ row, column, value, originalValue }) => {
    if (column === 'tag' && value !== originalValue) {
      commitEditTag(originalValue, value)
    }
  }

  // 处理行头（用例标签）单元格点击
  const handleTagCellClick = (metricName, rowIndex, colIndex, row) => {
    const tableRef = tableRefs.value[metricName]
    if (tableRef) {
      tableRef.startEditCell(rowIndex, colIndex)
    }
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
