import { computed } from 'vue'

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

  // 后端已分页+过滤+排序，cases.value 即当前页数据
  const filteredCases = computed(() => cases.value || [])

  return { filteredCases }
}
