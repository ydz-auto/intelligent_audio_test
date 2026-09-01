import { ref, computed, watch, onUnmounted, inject } from 'vue'
import { useNotification } from '../../composables/modal/useNotification'
import { debounce } from '../../utils/utils'
import { useCollapse, useResourceHeaders } from './shared/useReportShared'
import { getValidResources, toMetricsMap, toTextMap, createCaseDataHelpers } from './specificCaseDataHelpers'
import { createDownloadLogic } from './specificCaseDownload'
import { createCaseDetailPrep } from './specificCaseDetailPrep'
import { createCaseMetricsComputeds, createFilteredCases } from './specificCaseComputeds'
import { usePagination } from '../../composables/usePagination'

export function useSpecificCaseComparison(props: any) {
  // 导出模式：导出时展开所有用例、显示全部不分页
  const isExporting = inject('isExporting', ref(false))

  // Audio player state
  const showAudioModal = ref(false)
  const currentAudioId = ref<any>(null)
  const currentAudioTitle = ref('')
  const currentAudioTypeLabel = ref('')
  const currentAudioType = ref('api')
  const currentAudioSpl = ref<any>(null)
  const currentAudioPlayOrder = ref<any>(null)
  const currentAudioNoiseSpl = ref<any>(null)
  const currentAudioDeviceName = ref<any>(null)

  const playAudio = (audio: any, typeLabel: string = '', type: string = 'api') => {
    if (!audio || (!audio.id && !audio.url)) return
    currentAudioId.value = audio.id
    currentAudioTitle.value = audio.filename || audio.label || '未知音频'
    currentAudioTypeLabel.value = typeLabel || audio.label || '测试音频'
    currentAudioType.value = type
    currentAudioSpl.value = audio.spl || null
    currentAudioPlayOrder.value = audio.play_order || null
    currentAudioNoiseSpl.value = audio.noise_spl || null
    currentAudioDeviceName.value = audio.device_name || null
    showAudioModal.value = true
  }

  // Collapse state
  const { isCollapsed, toggleCollapse } = useCollapse()

  const resourceHeaders = computed(() => {
    const data = props.reportData || {}
    return (
      data.resource_headers ||
      data.summary?.resource_headers ||
      []
    )
  })

  const { resourceHeaderMap, getResourceLabel } = useResourceHeaders(props)

  // Data
  const searchKeyword = ref('')
  const selectedCategories = ref<any[]>([])
  const categorySearchQuery = ref('')
  const categoryPage = ref(1)
  const categoryPageSize = ref(50)

  // 处理标签：如果是对象数组，提取name属性
  const processTags = (tags: any) => {
    if (!tags) return []
    if (!Array.isArray(tags)) return []
    return tags.map(tag => typeof tag === 'object' ? tag.name : tag)
  }

  // 处理类别：如果是对象数组，提取name属性
  const processCategories = (categories: any) => {
    if (!categories) return []
    if (!Array.isArray(categories)) return []
    return categories.map(cat => typeof cat === 'object' ? cat.name : cat)
  }

  const filteredCategoriesForSelection = computed(() => {
    if (!categorySearchQuery.value.trim()) {
      return categories.value
    }
    const query = categorySearchQuery.value.toLowerCase()
    return categories.value.filter((cat: string) => cat.toLowerCase().includes(query))
  })

  // 类别分页：使用通用分页 composable
  const { totalPages: totalCategoryPages, paginatedItems: paginatedCategories } = usePagination(filteredCategoriesForSelection, categoryPageSize, { currentPage: categoryPage })

  const selectedTags = ref<any[]>([])
  const selectedMetrics = ref<any[]>([])
  const sortDimension = ref('name')
  const selectedSortMetric = ref('')
  const sortOrder = ref('asc')
  const expandedCases = ref<any[]>([])
  const pinnedCases = ref<any[]>([])
  const currentCaseDetail = ref<any>(null)
  const casesLoading = ref(false)
  const casesLoadError = ref('')
  const isDownloadingLog = ref(false)
  const downloadingCaseName = ref('')
  const downloadProgress = ref(0)
  const downloadSpeed = ref('')
  const downloadSize = ref('')
  const downloadTotal = ref('')

  // 从reportData中获取数据，优先使用reportData直接提供的数据，然后再使用summary中的数据
  // 注意：二次对比报告中用例分组存储在caseCategories字段中，而不是categories字段中
  const categories = ref<any[]>(processCategories(props.reportData.categories || props.reportData.summary?.categories || props.reportData.summary?.case_categories))
  const allTags = ref<any[]>(processTags(props.reportData.all_tags || props.reportData.summary?.all_tags || props.reportData.summary?.all_case_tags))

  // 所有评测维度，确保至少有一个默认维度
  const allMetrics = ref<any[]>(props.reportData.all_metrics || props.reportData.summary?.all_metrics || [])

  // 获取用例数据
  const cases = ref<any[]>([])
  const totalCases = ref(0)
  const pageSize = ref(10)
  const currentPage = ref(1)

  // 计算实际使用的评测维度
  const { actualAllMetrics } = createCaseMetricsComputeds({ allMetrics, cases })

  // 设备/API列表
  const devices = ref<any[]>(getValidResources(props.reportData));

  // 使用提取的数据辅助函数
  const { extractCasesFromReportData, loadCasesPage, loadAllCasesForExport } = createCaseDataHelpers({
    props,
    cases,
    totalCases,
    currentPage,
    pageSize,
    casesLoading,
    casesLoadError,
    searchKeyword,
    selectedCategories,
    selectedTags,
    selectedMetrics,
    sortDimension,
    selectedSortMetric,
    sortOrder,
    processTags
  })

  // Computed
  const allDevices = computed(() => {
    const allCases = cases.value || []
    if (allCases.length > 0) {
      const resourcesSet = new Set()
      allCases.forEach((caseItem: any) => {
        if (caseItem.asr) {
          const asrMap = toTextMap(caseItem.asr)
          Object.keys(asrMap).forEach(resource => resourcesSet.add(resource))
        }
        if (caseItem.translation) {
          const tranMap = toTextMap(caseItem.translation)
          Object.keys(tranMap).forEach(resource => resourcesSet.add(resource))
        }
        if (caseItem.metrics) {
          const metricsMap = toMetricsMap(caseItem)
          Object.keys(metricsMap).forEach(resource => resourcesSet.add(resource))
        }
      })
      return Array.from(resourcesSet)
    }
    return devices.value || []
  })

  // Helper function to extract device/API name from resource key
  const getResourceName = (resourceKey: string) => {
    if (resourceKey.includes('_')) {
      const parts = resourceKey.split('_');
      if (parts.length >= 2) {
        return `${parts[0]} - ${parts.slice(1).join('_')}`;
      }
      return parts.slice(1).join('_');
    }
    return resourceKey;
  }

  const { filteredCases } = createFilteredCases({
    cases, searchKeyword, selectedCategories, allTags, selectedTags,
    actualAllMetrics, selectedMetrics, sortDimension, selectedSortMetric, sortOrder
  })

  const unpinnedFilteredCases = computed(() => {
    const pinnedIds = new Set((pinnedCases.value || []).map((p: any) => p?.id))
    return (filteredCases.value || []).filter((c: any) => c && !pinnedIds.has(c.id))
  })

  // 用例分页为服务端分页，totalCases 由 API 返回
  // 此处用 totalCases 长度的占位数组驱动 totalPages 计算
  const placeholderForTotalCases = computed(() => Array(totalCases.value).fill(0))
  const { totalPages } = usePagination(placeholderForTotalCases, pageSize, { currentPage })

  const paginatedCases = computed(() => filteredCases.value)

  // 导出模式：拉取全量用例并展开所有用例详情
  watch(isExporting, async (exporting) => {
    if (exporting) {
      isCollapsed.value = false
      const reportId = props.reportData?.id || props.reportData?.report_id
      if (reportId) {
        await loadAllCasesForExport(reportId)
      }
      // 展开所有用例详情，让 .case-details 渲染到 DOM 中
      // 克隆后由 ReportView 的 generateExportZip 统一隐藏，JS 点击再展开
      expandedCases.value = (unpinnedFilteredCases.value || []).map((c: any) => c.id)
    }
  }, { immediate: true })

  // 使用提取的case detail准备逻辑
  const { prepareComparisonData, getAlgorithmResults, prepareAudioList, prepareCaseItem } = createCaseDetailPrep({
    props,
    allDevices
  })

  const currentCaseDetailWithPreparedData = computed(() => {
    if (!currentCaseDetail.value) return null
    const caseItem = currentCaseDetail.value
    return prepareCaseItem(caseItem)
  })

  // Search and pagination for tags
  const tagSearchQuery = ref('')
  const tagPage = ref(1)
  const tagPageSize = ref(50)

  const filteredTags = computed(() => {
    if (!tagSearchQuery.value.trim()) {
      return allTags.value
    }
    const query = tagSearchQuery.value.toLowerCase()
    return allTags.value.filter((tag: string) => tag.toLowerCase().includes(query))
  })

  // 标签分页：使用通用分页 composable
  const { totalPages: totalTagPages, paginatedItems: paginatedTags } = usePagination(filteredTags, tagPageSize, { currentPage: tagPage })

  // Search and pagination for metrics
  const metricSearchQuery = ref('')
  const metricPage = ref(1)
  const metricPageSize = ref(30)

  const filteredMetricsForDisplay = computed(() => {
    if (!metricSearchQuery.value.trim()) {
      return actualAllMetrics.value
    }
    const query = metricSearchQuery.value.toLowerCase()
    return actualAllMetrics.value.filter((metric: any) => metric.name.toLowerCase().includes(query))
  })

  // 维度分页：使用通用分页 composable
  const { totalPages: totalMetricPages, paginatedItems: paginatedMetrics } = usePagination(filteredMetricsForDisplay, metricPageSize, { currentPage: metricPage })

  const paginatedCasesWithPreparedData = computed(() => {
    const sourceCases = paginatedCases.value
    return sourceCases.map((caseItem: any) => prepareCaseItem(caseItem))
  })

  // 筛选/排序条件变化时重新请求后端
  const debouncedReload = debounce(() => {
    const reportId = props.reportData?.id || props.reportData?.report_id
    if (reportId && !isExporting.value) {
      currentPage.value = 1
      loadCasesPage(reportId)
    }
  }, 300)

  watch([searchKeyword, selectedCategories, selectedTags, selectedMetrics, sortDimension, selectedSortMetric, sortOrder], () => {
    debouncedReload()
  }, { deep: true })

  // 翻页/改页大小
  const handlePrevPage = () => {
    if (currentPage.value > 1) {
      currentPage.value -= 1
      const reportId = props.reportData?.id || props.reportData?.report_id
      if (reportId) loadCasesPage(reportId)
    }
  }

  const handleNextPage = () => {
    if (currentPage.value < totalPages.value) {
      currentPage.value += 1
      const reportId = props.reportData?.id || props.reportData?.report_id
      if (reportId) loadCasesPage(reportId)
    }
  }

  const handleGoToPage = (page: any) => {
    const p = Number(page)
    if (!Number.isFinite(p)) return
    currentPage.value = Math.min(Math.max(1, p), totalPages.value)
    const reportId = props.reportData?.id || props.reportData?.report_id
    if (reportId) loadCasesPage(reportId)
  }

  const handlePageSizeChange = (newSize: any) => {
    pageSize.value = Number(newSize)
    currentPage.value = 1
    const reportId = props.reportData?.id || props.reportData?.report_id
    if (reportId) loadCasesPage(reportId)
  }

  // Methods
  const toggleCaseExpand = (caseId: any) => {
    const index = expandedCases.value.indexOf(caseId)
    if (index > -1) {
      expandedCases.value.splice(index, 1)
      console.log('Case collapsed:', caseId, 'Expanded cases:', expandedCases.value)
    } else {
      expandedCases.value.push(caseId)
      console.log('Case expanded:', caseId, 'Expanded cases:', expandedCases.value)
    }
  }

  const toggleTag = (tag: any) => {
    const index = selectedTags.value.indexOf(tag)
    if (index > -1) {
      selectedTags.value.splice(index, 1)
    } else {
      selectedTags.value.push(tag)
    }
  }

  const toggleCategoryFilter = (category: any) => {
    const index = selectedCategories.value.indexOf(category)
    if (index > -1) {
      selectedCategories.value.splice(index, 1)
    } else {
      selectedCategories.value.push(category)
    }
  }

  const togglePin = (caseId: any) => {
    const caseItem = cases.value.find((c: any) => c.id === caseId) || filteredCases.value.find((c: any) => c.id === caseId)
    if (!caseItem) return

    const pinnedIndex = pinnedCases.value.findIndex((p: any) => p.id === caseId)
    if (pinnedIndex > -1) {
      pinnedCases.value.splice(pinnedIndex, 1)
    } else {
      pinnedCases.value.push(caseItem)
    }
  }

  const openCaseDetail = (caseItem: any) => {
    currentCaseDetail.value = caseItem
  }

  const closeCaseDetail = () => {
    currentCaseDetail.value = null
  }

  // 监听键盘事件，处理 ESC 退出
  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && currentCaseDetail.value) {
      closeCaseDetail();
    }
  };

  watch(() => currentCaseDetail.value, (newVal) => {
    if (newVal) {
      window.addEventListener('keydown', handleKeyDown);
    } else {
      window.removeEventListener('keydown', handleKeyDown);
    }
  }, { immediate: true });

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown);
  });

  const getOverallStatus = (caseItem: any) => {
    const statuses = (Array.isArray(caseItem.results) ? caseItem.results : []).map((r: any) => r.status)
    if (statuses.includes('失败') || statuses.includes('Failed')) return 'failed'
    if (statuses.includes('警告') || statuses.includes('Warning')) return 'warning'
    return 'success'
  }

  const getCaseTaskId = (caseItem: any) => {
    return caseItem.task_id || props.reportData?.task_id || props.reportData?.summary?.task_id || ''
  }

  const copyToClipboard = (text: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => {
        const notification = useNotification()
        notification.success('ID已复制到剪贴板')
      }).catch(() => {
        const notification = useNotification()
        notification.error('复制失败')
      })
    }
  }

  // 使用提取的下载逻辑
  const { downloadCaseLogZip } = createDownloadLogic({
    props,
    isDownloadingLog,
    downloadingCaseName,
    downloadProgress,
    downloadSpeed,
    downloadSize,
    downloadTotal
  })

  const formatTime = (timestamp: any) => {
    return new Date(timestamp).toLocaleString()
  }

  const toggleMetric = (metricName: any) => {
    const index = selectedMetrics.value.indexOf(metricName)
    if (index > -1) {
      selectedMetrics.value.splice(index, 1)
    } else {
      selectedMetrics.value.push(metricName)
    }
  }

  const resetFilters = () => {
    searchKeyword.value = ''
    selectedCategories.value = []
    categorySearchQuery.value = ''
    categoryPage.value = 1
    selectedTags.value = []
    selectedMetrics.value = []
    sortDimension.value = 'name'
    selectedSortMetric.value = ''
    sortOrder.value = 'asc'
    tagSearchQuery.value = ''
    tagPage.value = 1
    metricSearchQuery.value = ''
    metricPage.value = 1
  }

  const applyFilters = () => {
    // 筛选由 watch 自动触发后端请求，这里仅做日志
    console.log('应用筛选:', {
      searchKeyword: searchKeyword.value,
      selectedCategories: selectedCategories.value,
      selectedTags: selectedTags.value,
      selectedMetrics: selectedMetrics.value,
      sortDimension: sortDimension.value,
      sortOrder: sortOrder.value
    })
  }

  watch(actualAllMetrics, (newMetrics: any) => {
    const names = (newMetrics || []).map((m: any) => m?.name).filter(Boolean)
    if (selectedMetrics.value.length > 0) {
      selectedMetrics.value = selectedMetrics.value.filter((n: any) => names.includes(n))
    }
    if (selectedSortMetric.value && !names.includes(selectedSortMetric.value)) {
      selectedSortMetric.value = ''
    }
  }, { immediate: true })

  // 调试信息
  console.log('SpecificCaseComparisonComponent - reportData:', props.reportData)
  console.log('SpecificCaseComparisonComponent - cases:', cases.value)
  console.log('SpecificCaseComparisonComponent - caseItem.metrics sample:', cases.value.length > 0 ? JSON.stringify(Object.values(cases.value[0].metrics || {})) : 'no cases')
  console.log('SpecificCaseComparisonComponent - actualAllMetrics:', actualAllMetrics.value)
  console.log('SpecificCaseComparisonComponent - devices:', devices.value)

  // 防止同一 reportId 重复加载
  let loadedReportId: any = null

  // 监听reportData变化，更新内部状态
  watch([
    () => props.reportData?.id,
    () => props.reportData?.report_id,
    () => props.reportData?.cases?.length,
    () => props.reportData?.test_reports_cases?.length,
    () => props.reportData?.summary?.cases?.length
  ], async ([id, reportId, casesLen, testReportsCasesLen, summaryCasesLen]: any, [oldId, oldReportId]: any) => {
    const newReportData = props.reportData

    categories.value = processCategories(newReportData.categories || newReportData.summary?.categories || newReportData.summary?.case_categories)
    allTags.value = processTags(newReportData.all_tags || newReportData.summary?.all_tags || newReportData.summary?.all_case_tags)
    allMetrics.value = newReportData.all_metrics || newReportData.summary?.all_metrics || []
    devices.value = getValidResources(newReportData);

    const effectiveReportId = id || reportId
    if (effectiveReportId) {
      if (effectiveReportId !== loadedReportId && effectiveReportId !== oldId && effectiveReportId !== oldReportId) {
        loadedReportId = effectiveReportId
        console.log('watch: 优先调用 /api/v1/reports/{id}/cases/search API 获取用例数据')
        currentPage.value = 1
        await loadCasesPage(effectiveReportId)

        if (!cases.value || cases.value.length === 0) {
          console.log('watch: API 返回空数据，尝试从本地数据提取')
          cases.value = extractCasesFromReportData(newReportData)
        }
      }
    } else {
      cases.value = extractCasesFromReportData(newReportData)
    }

    // 重置选中状态
    selectedTags.value = []
    selectedMetrics.value = []
    selectedCategories.value = []
    categorySearchQuery.value = ''
    categoryPage.value = 1
    tagSearchQuery.value = ''
    tagPage.value = 1
    metricSearchQuery.value = ''
    metricPage.value = 1
  }, { immediate: true })

  return {
    showAudioModal, currentAudioId, currentAudioTitle, currentAudioTypeLabel,
    currentAudioType, currentAudioSpl, currentAudioPlayOrder, currentAudioNoiseSpl,
    currentAudioDeviceName, playAudio,
    isCollapsed, toggleCollapse,
    casesLoading, casesLoadError,
    searchKeyword,
    selectedCategories, categorySearchQuery, paginatedCategories, toggleCategoryFilter,
    filteredCategoriesForSelection, categoryPage, categoryPageSize, totalCategoryPages,
    selectedTags, tagSearchQuery, paginatedTags, toggleTag, filteredTags,
    tagPage, tagPageSize, totalTagPages,
    selectedMetrics, metricSearchQuery, paginatedMetrics, toggleMetric,
    filteredMetricsForDisplay, metricPage, metricPageSize, totalMetricPages,
    sortDimension, selectedSortMetric, sortOrder, actualAllMetrics,
    resetFilters, applyFilters,
    pinnedCases, togglePin,
    getResourceLabel, resourceHeaders,
    paginatedCasesWithPreparedData, toggleCaseExpand, getOverallStatus,
    copyToClipboard, downloadCaseLogZip, expandedCases, allDevices,
    unpinnedFilteredCases, totalCases, currentPage, pageSize, handlePrevPage, handleNextPage, handleGoToPage, handlePageSizeChange,
    currentCaseDetailWithPreparedData, closeCaseDetail, openCaseDetail,
    getResourceName, getCaseTaskId, formatTime,
    isDownloadingLog, downloadingCaseName, downloadProgress, downloadSpeed, downloadSize, downloadTotal
  }
}
