import { computed } from 'vue'
import { toMetricsMap } from './specificCaseDataHelpers'

export function createCaseMetricsComputeds(deps: {
  allMetrics: any
  cases: any
}) {
  const { allMetrics, cases } = deps

  const actualAllMetrics = computed(() => {
    let metrics = allMetrics.value || [];

    console.log('actualAllMetrics - allMetrics.value:', allMetrics.value)
    console.log('actualAllMetrics - cases.value:', cases.value)

    // 如果没有提供维度，从cases数据中提取所有维度
    if (metrics.length === 0 && cases.value.length > 0) {
      const dimensionSet = new Set();
      cases.value.forEach((caseItem: any) => {
        console.log('actualAllMetrics - caseItem.metrics:', caseItem.metrics)
        const metricsData = caseItem.metrics
        if (Array.isArray(metricsData)) {
          metricsData.forEach((m: any) => {
            if (m && m.metric) {
              dimensionSet.add(m.metric);
            }
          });
        } else if (metricsData && typeof metricsData === 'object') {
          Object.keys(metricsData).forEach(dimName => {
            dimensionSet.add(dimName);
          });
        }
      });

      console.log('actualAllMetrics - dimensionSet:', dimensionSet)

      metrics = Array.from(dimensionSet).map(dimName => ({
        name: dimName,
        unit: '%' // 默认单位
      }));
    }

    // 如果仍然没有维度，添加默认维度
    if (metrics.length === 0) {
      metrics = [{ name: 'WER', unit: '%' }];
    }

    const usedMetricNames = new Set()
    const allCases = cases.value || []
    if (allCases.length > 0) {
      allCases.forEach((caseItem: any) => {
        const metricsData = caseItem.metrics
        if (Array.isArray(metricsData)) {
          metricsData.forEach((m: any) => {
            if (m && m.metric && typeof m.value === 'number') {
              usedMetricNames.add(m.metric)
            }
          })
        } else if (metricsData && typeof metricsData === 'object') {
          Object.entries(metricsData).forEach(([metricName, metricValue]) => {
            const n = typeof metricValue === 'number' ? metricValue : Number(metricValue)
            if (Number.isFinite(n)) usedMetricNames.add(metricName)
          })
        }
      })
    }

    if (usedMetricNames.size > 0) {
      metrics = metrics.filter((m: any) => m?.name && usedMetricNames.has(m.name))
      if (metrics.length === 0) {
        metrics = [{ name: 'WER', unit: '%' }]
      }
    }

    console.log('actualAllMetrics - final metrics:', metrics)
    return metrics;
  })

  return { actualAllMetrics }
}

export function createFilteredCases(deps: {
  cases: any
  searchKeyword: any
  selectedCategories: any
  allTags: any
  selectedTags: any
  actualAllMetrics: any
  selectedMetrics: any
  sortDimension: any
  selectedSortMetric: any
  sortOrder: any
}) {
  const {
    cases, searchKeyword, selectedCategories, allTags, selectedTags,
    actualAllMetrics, selectedMetrics, sortDimension, selectedSortMetric, sortOrder
  } = deps

  const filteredCases = computed(() => {
    const caseData = cases.value || []

    let filtered = caseData.filter((caseItem: any) => {
      const keywordMatch = !searchKeyword.value ||
        caseItem.name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
        (caseItem.description && caseItem.description.toLowerCase().includes(searchKeyword.value.toLowerCase()))

      const categoryMatch = selectedCategories.value.length === 0 ||
        selectedCategories.value.includes(caseItem.category)

      const allTagsSelected = selectedTags.value.length === allTags.value.length
      const tagMatch = allTagsSelected || selectedTags.value.length === 0 ||
        selectedTags.value.some(tag => {
          if (!caseItem.tags) return false
          const tagNames = caseItem.tags.map((t: any) => typeof t === 'object' ? t.name : t)
          return tagNames.includes(tag)
        })

      const allMetricsSelected = selectedMetrics.value.length === actualAllMetrics.value.length
      const metricMatch = allMetricsSelected || selectedMetrics.value.length === 0 ||
        selectedMetrics.value.every(metric => {
          const metricsMap = toMetricsMap(caseItem)
          return Object.values(metricsMap).some((deviceMetrics: any) => deviceMetrics && typeof deviceMetrics[metric] === 'number')
        })

      return keywordMatch && categoryMatch && tagMatch && metricMatch
    })

    filtered.sort((a: any, b: any) => {
      let aVal: any, bVal: any

      if (sortDimension.value === '评估维度') {
        const aMap = toMetricsMap(a)
        const bMap = toMetricsMap(b)
        aVal = Object.values(aMap).reduce((sum: number, metrics: any) => sum + (metrics?.[selectedSortMetric.value] || 0), 0) / (Object.values(aMap).length || 1)
        bVal = Object.values(bMap).reduce((sum: number, metrics: any) => sum + (metrics?.[selectedSortMetric.value] || 0), 0) / (Object.values(bMap).length || 1)
      } else {
        switch (sortDimension.value) {
          case 'name':
            aVal = a.name.toLowerCase()
            bVal = b.name.toLowerCase()
            break
          case 'category':
            aVal = (a.category || '').toLowerCase()
            bVal = (b.category || '').toLowerCase()
            break
          case 'tags': {
            const aTags = a.tags ? a.tags.map((t: any) => typeof t === 'object' ? t.name : t) : []
            const bTags = b.tags ? b.tags.map((t: any) => typeof t === 'object' ? t.name : t) : []
            aVal = aTags.length > 0 ? aTags[0].toLowerCase() : ''
            bVal = bTags.length > 0 ? bTags[0].toLowerCase() : ''
            break
          }
          case 'createdAt': {
            const aResults = (Array.isArray(a.results) ? a.results : Object.values(a.results || {})) as any[]
            const bResults = (Array.isArray(b.results) ? b.results : Object.values(b.results || {})) as any[]
            aVal = aResults[0]?.startTime || 0
            bVal = bResults[0]?.startTime || 0
            break
          }
          default:
            aVal = 0
            bVal = 0
        }
      }

      if (aVal < bVal) {
        return sortOrder.value === 'asc' ? -1 : 1
      }
      if (aVal > bVal) {
        return sortOrder.value === 'asc' ? 1 : -1
      }
      return 0
    })

    return filtered
  })

  return { filteredCases }
}
