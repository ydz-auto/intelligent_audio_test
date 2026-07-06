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
        <DataTable
          :columns="tableColumns"
          :data="tableData"
          :resizable="true"
          :min-column-width="60"
          :default-column-width="{ first: 200, others: 150 }"
          table-class="report-data-table"
          row-key="dimension"
        >
          <!-- 自定义第一列（维度名称） -->
          <template #cell-dimension="{ row, value }">
            <span>{{ row.dimension }}</span>
          </template>

          <!-- 空状态 -->
          <template #empty>
            <div class="empty-state">
              <i class="fas fa-inbox"></i>
              <p>暂无维度数据</p>
            </div>
          </template>
        </DataTable>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import DataTable from '../common/DataTable.vue'

const props = defineProps({
  reportData: {
    type: Object, default: () => ({})
  }
})

const isCollapsed = ref(false)

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

// 从 get_one 返回的 metricData (dict格式: {category: {resource: {metric: avg}}}) 跨 category 聚合
const getMetricData = () => {
  return props.reportData?.metricData || props.reportData?.summary?.metricData ||
         props.reportData?.metric_data || props.reportData?.summary?.metric_data || {}
}

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

  // 如果 allMetrics 为空，从 metricData 中提取维度名
  if (metrics.length === 0) {
    const metricData = getMetricData()
    const dimensionSet = new Set()
    Object.keys(metricData).forEach(category => {
      const resData = metricData[category]
      if (!resData || typeof resData !== 'object') return
      Object.keys(resData).forEach(resourceKey => {
        const metrics = resData[resourceKey]
        if (!metrics || typeof metrics !== 'object') return
        Object.keys(metrics).forEach(dimName => {
          // 跳过 _raw 后缀的原始数据 key
          if (!dimName.endsWith('_raw')) dimensionSet.add(dimName)
        })
      })
    })
    metrics = Array.from(dimensionSet).map(dimName => ({ name: dimName, unit: '%' }))
  }

  if (metrics.length === 0) {
    metrics = [{ name: 'WER', unit: '%' }]
  }

  return metrics
})

const totalCases = computed(() => props.reportData?.summary?.totalCases || props.reportData?.summary?.total_cases || 0)
const metricsCount = computed(() => actualAllMetrics.value.length)
const devicesCount = computed(() => devices.value.length)

const tableColumns = computed(() => {
  const columns = [
    {
      key: 'dimension',
      label: '维度 / 资源',
      resize: true,
      class: 'dimension-column'
    }
  ]

  processedDevices.value.forEach((device, index) => {
    columns.push({
      key: `device-${index}`,
      label: device,
      resize: true,
      class: 'device-column',
      color: '#1677ff'
    })
  })

  return columns
})

const tableData = computed(() => {
  return actualAllMetrics.value.map(metric => {
    const row = {
      dimension: metric.name
    }

    devices.value.forEach((device, index) => {
      const metricObj = actualAllMetrics.value.find(m => m.name === metric.name)
      const unit = metricObj?.unit || ''
      row[`device-${index}`] = formatMetricValue(metric.name, getAverageValue(metric.name, device)) + unit
    })

    return row
  })
})

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

// 从 metricData (dict格式: {category: {resource: {metric: avg}}}) 跨 category 聚合
// 返回每个 resource 的每个 metric 的平均值（跨所有 category）
const getAverageValue = (metricName, device) => {
  const metricData = getMetricData()
  if (!metricData || typeof metricData !== 'object') return 0

  const values = []

  Object.keys(metricData).forEach(category => {
    const resData = metricData[category]
    if (!resData || typeof resData !== 'object') return

    // 直接用 device key 查找
    if (resData[device] && typeof resData[device][metricName] === 'number') {
      values.push(resData[device][metricName])
      return
    }

    // 如果 device 是对象，构建 key 查找
    if (typeof device === 'object' && device !== null) {
      const resourceKey = `${device.id}-${device.name}`
      if (resData[resourceKey] && typeof resData[resourceKey][metricName] === 'number') {
        values.push(resData[resourceKey][metricName])
        return
      }
    }

    // 兜底：按名称匹配（去掉ID前缀）
    const deviceName = typeof device === 'object' ? (device.name || device.deviceName) :
                      (typeof device === 'string' && device.includes('-') ? device.split('-').slice(1).join('-') : device)
    for (const [key, metrics] of Object.entries(resData)) {
      if (!metrics || typeof metrics !== 'object') continue
      const currentResourceName = key.includes('-') ? key.split('-').slice(1).join('-') : key
      if (currentResourceName === deviceName && typeof metrics[metricName] === 'number') {
        values.push(metrics[metricName])
        break
      }
    }
  })

  if (values.length === 0) return 0
  const sum = values.reduce((acc, v) => acc + v, 0)
  return sum / values.length
}
</script>

<style scoped>
.overview-card {
  background: transparent;
  padding: 0;
  margin-bottom: 24px;
  width: 100%;
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
  padding: 16px 0;
  width: 100%;
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
  width: 100%;
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
