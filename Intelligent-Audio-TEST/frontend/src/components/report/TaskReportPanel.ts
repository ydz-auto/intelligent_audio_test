import { ref, watch, computed, onMounted, onUnmounted, inject } from 'vue';
import { sanitizeConclusion } from '../../utils/sanitize';

export function useTaskReportPanel(props: any, emit: any) {
  const editableConclusion = ref('')
  const localIsEditing = ref(false)
  const isAnalysisCollapsed = ref(false)
  const isDevicesCollapsed = ref(false)
  const activeSection = ref('section-overview')
  const progressHeight = ref('0%')

  // 导出模式：导出时展开所有折叠区块
  const isExporting = inject('isExporting', ref(false))

  // 导出时强制展开所有折叠区块
  watch(isExporting, (exporting) => {
    if (exporting) {
      isAnalysisCollapsed.value = false
      isDevicesCollapsed.value = false
    }
  }, { immediate: true })

  const toggleAnalysisCollapse = () => {
    isAnalysisCollapsed.value = !isAnalysisCollapsed.value
  }

  const toggleDevicesCollapse = () => {
    isDevicesCollapsed.value = !isDevicesCollapsed.value
  }

  const deviceStats = computed(() => {
    const stats = props.report?.summary?.device_stats || []
    return Array.isArray(stats) ? stats : []
  })

  const apiStats = computed(() => {
    const stats = props.report?.summary?.api_stats || []
    return Array.isArray(stats) ? stats : []
  })

  const hasDeviceOrApiStats = computed(() => {
    return deviceStats.value.length > 0 || apiStats.value.length > 0
  })

  const allMetrics = computed(() => {
    const metrics = props.report?.summary?.all_metrics || []
    return Array.isArray(metrics) ? metrics : []
  })

  const getMetricUnit = (metricName: any) => {
    const metric = allMetrics.value.find((m: any) => m.name === metricName)
    return metric?.unit || ''
  }

  const formatPercent = (value: any) => {
    if (value === null || value === undefined) return '0%'
    const num = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(num)) return '0%'
    return `${num.toFixed(1)}%`
  }

  const formatMetricValue = (value: any) => {
    if (value === null || value === undefined) return '-'
    const num = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(num)) return String(value)
    return num.toFixed(2)
  }

  const formatMetricWithUnit = (value: any, metricName: any) => {
    const formattedValue = formatMetricValue(value)
    const unit = getMetricUnit(metricName)
    return unit ? `${formattedValue}${unit}` : formattedValue
  }

  const getSuccessRateClass = (rate: any) => {
    if (rate === null || rate === undefined) return ''
    const num = typeof rate === 'number' ? rate : Number(rate)
    if (!Number.isFinite(num)) return ''
    if (num >= 80) return 'success'
    if (num >= 50) return 'warning'
    return 'danger'
  }

  const navItems = computed(() => {
    const items = [
      { id: 'section-overview', label: '概览' },
    ]
    if (hasDeviceOrApiStats.value) {
      items.push({ id: 'section-devices', label: '设备与API' })
    }
    items.push(
      { id: 'section-analysis', label: '分析结论' },
      { id: 'section-category', label: '用例分组' },
      { id: 'section-tag', label: '用例标签' },
      { id: 'section-case', label: '具体用例' },
    )
    return items
  })

  const formatDate = (dateStr: any) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
  }

  watch(() => props.analysisContent, (newVal: any) => {
    editableConclusion.value = newVal
  }, { immediate: true })

  const sanitizedAnalysisContent = computed(() => {
    return sanitizeConclusion(props.analysisContent);
  })

  const startEdit = () => {
    editableConclusion.value = props.analysisContent
    localIsEditing.value = true
  }

  const saveLocalConclusion = () => {
    emit('save-conclusion', editableConclusion.value)
    localIsEditing.value = false
  }

  const cancelLocalConclusion = () => {
    editableConclusion.value = props.analysisContent
    localIsEditing.value = false
    emit('cancel-conclusion')
  }

  const scrollToSection = (sectionId: any) => {
    activeSection.value = sectionId
    const element = document.getElementById(sectionId)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const handleScroll = () => {
    const sections = navItems.value.map(item => ({
      id: item.id,
      element: document.getElementById(item.id)
    }))

    let currentSection = 'section-overview'
    const scrollPosition = window.scrollY + 150

    for (let i = sections.length - 1; i >= 0; i--) {
      const section = sections[i]
      if (section.element) {
        const sectionTop = section.element.offsetTop
        if (scrollPosition >= sectionTop) {
          currentSection = section.id
          break
        }
      }
    }

    activeSection.value = currentSection

    const docHeight = document.documentElement.scrollHeight - window.innerHeight
    const scrollPercent = (window.scrollY / docHeight) * 100
    progressHeight.value = Math.min(100, Math.max(0, scrollPercent)) + '%'
  }

  onMounted(() => {
    window.addEventListener('scroll', handleScroll)
    handleScroll()
  })

  onUnmounted(() => {
    window.removeEventListener('scroll', handleScroll)
  })

  // Props exposed to template
  const report = computed(() => props.report)
  const tables = computed(() => props.tables)

  return {
    report,
    tables,
    editableConclusion,
    localIsEditing,
    isAnalysisCollapsed,
    isDevicesCollapsed,
    isExporting,
    activeSection,
    progressHeight,
    toggleAnalysisCollapse,
    toggleDevicesCollapse,
    deviceStats,
    apiStats,
    hasDeviceOrApiStats,
    getSuccessRateClass,
    formatPercent,
    formatMetricWithUnit,
    navItems,
    formatDate,
    sanitizedAnalysisContent,
    startEdit,
    saveLocalConclusion,
    cancelLocalConclusion,
    scrollToSection
  }
}
