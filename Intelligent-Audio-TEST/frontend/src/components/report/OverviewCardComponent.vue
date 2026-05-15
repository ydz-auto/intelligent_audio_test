<template>
  <div class="overview-card">
    <div class="section-header" @click="toggleCollapse">
      <h3 class="section-title">总览卡片 (Overview)</h3>
      <button class="collapse-btn" :class="{ collapsed: isCollapsed }" title="折叠/展开">
        <i class="fas fa-chevron-up" v-if="isCollapsed"></i>
        <i class="fas fa-chevron-down" v-else></i>
      </button>
    </div>

    <div class="section-content" v-if="!isCollapsed">
      <div class="overview-stats">
        <div class="stat-item">
          <span class="stat-label">用例总数</span>
          <span class="stat-value">{{ totalCases }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">评估维度</span>
          <span class="stat-value">{{ metricsCount }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">资源数</span>
          <span class="stat-value">{{ devicesCount }}</span>
        </div>
      </div>

      <div class="overview-table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th class="dimension-header">维度 / 资源</th>
              <th v-for="device in processedDevices" :key="device" class="resource-header">
                {{ device }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="metric in actualAllMetrics" :key="metric.name">
              <td class="dimension-cell">
                {{ metric.name }}
              </td>
              <td v-for="device in devices" :key="device" class="value-cell">
                {{ formatMetricValue(metric.name, getAverageValue(metric.name, device)) }}{{ metric.unit }}
              </td>
            </tr>
            <tr v-if="actualAllMetrics.length === 0" class="empty-row">
              <td :colspan="devices.length + 1" class="empty-cell">
                <div class="empty-state">
                  <i class="fas fa-inbox"></i>
                  <p>暂无维度数据</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { reportsApi } from '../../utils/api'

const props = defineProps({
  reportData: {
    type: Object, default: () => ({})
  }
})

const cases = ref([])
const casesLoading = ref(false)

const isCollapsed = ref(false)

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const loadCasesFromApi = async (reportId) => {
  casesLoading.value = true
  try {
    const perPage = 200
    let page = 1
    let pages = 1
    const allItems = []
    while (page <= pages) {
      const data = await reportsApi.searchCases(reportId, { page, per_page: perPage })
      const items = data?.items || []
      pages = data?.pages || 1
      allItems.push(...items)
      page += 1
      if (allItems.length >= 5000) break
    }
    cases.value = allItems
  } catch (e) {
    cases.value = []
  } finally {
    casesLoading.value = false
  }
}

const extractCasesFromReportData = (reportData) => {
  if (reportData.testReportsCases && Array.isArray(reportData.testReportsCases) && reportData.testReportsCases.length > 0) {
    return reportData.testReportsCases
  }
  if (reportData.cases && Array.isArray(reportData.cases) && reportData.cases.length > 0) {
    return reportData.cases
  }
  if (reportData.summary?.cases && Array.isArray(reportData.summary.cases) && reportData.summary.cases.length > 0) {
    return reportData.summary.cases
  }
  return []
}

const loadCases = async () => {
  const reportId = props.reportData?.id || props.reportData?.reportId
  if (reportId) {
    await loadCasesFromApi(reportId)
  }
  if (cases.value.length === 0) {
    cases.value = extractCasesFromReportData(props.reportData)
  }
}

onMounted(async () => {
  await loadCases()
})

watch(() => props.reportData, async () => {
  await loadCases()
}, { deep: true })

const resourceHeaderMap = computed(() => {
  const data = props.reportData || {}
  const headers =
    data.resourceHeaders ||
    data.resource_headers ||
    data.summary?.resourceHeaders ||
    data.summary?.resource_headers ||
    []

  const map = {}
  if (Array.isArray(headers)) {
    headers.forEach(h => {
      if (!h) return
      const key = h.key || h.resource
      const label = h.label || h.name || key
      if (key) map[String(key)] = String(label || key)
    })
  }
  return map
})

const getResourceLabel = (resourceKey) => {
  const key = String(resourceKey ?? '')
  const mapped = resourceHeaderMap.value?.[key]
  if (mapped) return mapped

  if (typeof resourceKey === 'string' && /^t\d+-\d{12}-/.test(resourceKey)) {
    const parts = resourceKey.split('-')
    if (parts.length >= 4) {
      const name = parts.slice(3).join('-')
      if (name) return name
    }
  }

  if (typeof resourceKey === 'string' && resourceKey.includes('_')) {
    const parts = resourceKey.split('_')
    const prefix = parts[0]
    const name = parts.slice(1).join('_')
    if (/^\d{14}$/.test(prefix)) {
      const month = prefix.substring(4, 6)
      const day = prefix.substring(6, 8)
      const hour = prefix.substring(8, 10)
      const minute = prefix.substring(10, 12)
      return `${month}-${day} ${hour}:${minute} ${name}`
    }
    return name
  }

  return resourceKey
}

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
}

const devices = computed(() => getValidResources(props.reportData))

const processedDevices = computed(() => {
  return devices.value.map(device => getResourceLabel(device))
})

const actualAllMetrics = computed(() => {
  let metrics = props.reportData?.allMetrics || props.reportData?.summary?.allMetrics || []

  if (metrics.length === 0 && cases.value.length > 0) {
    const dimensionSet = new Set()
    cases.value.forEach(caseItem => {
      const metricsData = caseItem.metrics
      if (Array.isArray(metricsData)) {
        metricsData.forEach(m => {
          if (m && m.metric) dimensionSet.add(m.metric)
        })
      } else if (metricsData && typeof metricsData === 'object') {
        Object.keys(metricsData).forEach(dimName => dimensionSet.add(dimName))
      }
    })
    metrics = Array.from(dimensionSet).map(dimName => ({ name: dimName, unit: '%' }))
  }

  if (metrics.length === 0) {
    metrics = [{ name: 'WER', unit: '%' }]
  }

  return metrics
})

const totalCases = computed(() => cases.value.length)
const metricsCount = computed(() => actualAllMetrics.value.length)
const devicesCount = computed(() => devices.value.length)

const metricDecimalPlacesMap = computed(() => {
  const map = {}
  const list = Array.isArray(actualAllMetrics.value) ? actualAllMetrics.value : []
  list.forEach(m => {
    if (!m || !m.name) return
    const dp = m.decimalPlaces ?? m.decimal_places
    if (Number.isInteger(dp) && dp >= 0) map[String(m.name)] = dp
  })
  return map
})

const formatMetricValue = (metricName, value) => {
  if (value === '-' || value === null || value === undefined) return '-'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return String(value)
  const dp = metricDecimalPlacesMap.value?.[String(metricName)]
  if (Number.isInteger(dp) && dp >= 0) return num.toFixed(dp)
  return String(num.toFixed(2))
}

const toMetricsMap = (caseItem) => {
  const metrics = caseItem?.metrics
  if (Array.isArray(metrics)) {
    if (metrics.length > 0 && metrics[0]?.resource) {
      const map = {}
      metrics.forEach(group => {
        if (!group || !group.resource) return
        const resource = group.resource
        if (!map[resource]) map[resource] = {}
        if (Array.isArray(group.metrics)) {
          group.metrics.forEach(m => {
            if (!m || !m.metric) return
            map[resource][m.metric] = m.value
          })
        }
      })
      return map
    }
    const flatMap = {}
    metrics.forEach(m => {
      if (!m || !m.metric) return
      flatMap[m.metric] = m.value
    })
    return flatMap
  }
  return metrics || {}
}

const getAverageValue = (metricName, device) => {
  if (!cases.value || cases.value.length === 0) return 0

  const values = []

  cases.value.forEach(caseItem => {
    const metricsMap = toMetricsMap(caseItem)
    const isFlatFormat = !Object.keys(metricsMap).some(k => devices.value.includes(k))

    let value
    if (isFlatFormat) {
      value = metricsMap[metricName]
    } else {
      value = metricsMap[device]?.[metricName]
    }

    if (value !== null && value !== undefined && typeof value === 'number' && Number.isFinite(value)) {
      values.push(value)
    }
  })

  if (values.length === 0) return 0

  const sum = values.reduce((acc, v) => acc + v, 0)
  return sum / values.length
}
</script>

<style scoped>
.overview-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 16px;
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  transition: all 0.3s ease;
}

.section-header:hover {
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
  flex: 1;
}

.collapse-btn {
  background: none;
  border: none;
  font-size: 16px;
  color: #64748b;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 16px;
}

.collapse-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #1677ff;
}

.collapse-btn.collapsed {
  transform: rotate(180deg);
}

.section-content {
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.overview-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 13px;
  color: #64748b;
  font-weight: 500;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1677ff;
}

.overview-table-container {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  font-size: 14px;
}

.data-table th {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  font-weight: 600;
  padding: 16px 20px;
  text-align: left;
  border-bottom: 2px solid #e2e8f0;
  color: #1e293b;
  font-size: 14px;
}

.data-table th:not(:first-child) {
  background: linear-gradient(135deg, rgba(255, 106, 0, 0.1) 0%, rgba(255, 106, 0, 0.05) 100%);
  text-align: center;
}

.data-table td {
  padding: 16px 20px;
  text-align: left;
  border-bottom: 1px solid #f1f5f9;
  font-weight: 500;
  font-size: 15px;
}

.data-table td:not(:first-child) {
  text-align: center;
  color: #1677ff;
}

.data-table tr {
  transition: all 0.3s ease;
  border-bottom: 1px solid #f1f5f9;
}

.data-table tr:hover {
  background-color: #f8fafc;
  transform: translateX(4px);
}

.data-table td.dimension-cell {
  text-align: left;
  font-weight: 600;
  color: #333;
  background: #fafafa;
}

.empty-row {
  text-align: center;
}

.empty-cell {
  padding: 40px 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #999;
}

.empty-state i {
  font-size: 32px;
  opacity: 0.5;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}
</style>
