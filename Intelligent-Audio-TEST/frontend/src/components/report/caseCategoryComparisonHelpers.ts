/**
 * 分类对比 helper —— 分类×资源×指标均值矩阵的提取/重算
 *
 * 输入为 adapter 转换后的 camelCase Domain 行（ReportMetricByResource）。
 * 输出统一为内存矩阵：{ [分类名]: { [资源键]: { [指标名]: number | number[] } } }
 */
import type { MetricAccumulator, MetricMatrix as CategoryMetricMatrix } from '../../domain/model/report'

/** 后端预计算行（dict 格式的分类分组，snake_case 原始字段） */
interface RawCategoryGroupDict {
  [category: string]: { [resourceKey: string]: { [metricName: string]: unknown } }
}

/** 后端预计算行（数组格式，adapter 输出 camelCase） */
interface RawCategoryRow {
  /** camelCase（adapter 输出） */
  resource?: string
  categories?: Array<{
    categoryId?: unknown
    categoryName?: string
    metrics?: Array<{ metric: string; value: unknown }>
  }>
  /** 兼容扁平行 */
  metrics?: Array<{ metric: string; value: unknown }>
  metric?: string
  value?: unknown
  /** 扁平行顶层分类标识（后端 dict 行直传） */
  categoryId?: unknown
  categoryName?: string
}

/** raw_data 分组（camelCase） */
interface RawDataRow {
  resource: string
  metrics?: Array<{ metric: string; values: unknown }>
  metric?: string
  values?: unknown
}

/** 报告用例（兼容 adapter Domain 与后端原值） */
interface RawCaseItem {
  category?: string
  tags?: Array<string | { name?: string }> | string[]
  metrics?:
    | Array<{ resource: string; metrics: Array<{ metric: string; value: unknown }> }>
    | Record<string, Record<string, unknown>>
}

/** 用例维度明细（adapter 输出 camelCase） */
interface RawDetailedResult {
  testCaseId?: string | number
  testCaseGroup?: { id: unknown; name: string }
  testCaseTags?: Array<{ name: string }>
  testCaseName?: string
  device?: { id: unknown; name: string }
  api?: { id: unknown; name: string }
  dimensionScores?: Array<{ dimensionName: string; score: number }>
  metrics?: Record<string, unknown>
}

/** 从 reportData 上按 camelCase 读取字段（顶层优先，回退 summary） */
function pickRawField(reportData: Record<string, unknown>, camel: string): unknown {
  const summary = reportData.summary as Record<string, unknown> | undefined
  if (reportData[camel] !== undefined) return reportData[camel]
  if (summary && summary[camel] !== undefined) return summary[camel]
  return undefined
}

/** 判定是否普通对象（排除 null/数组） */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 提取分类×资源×指标矩阵
 * 优先级：后端预计算 metricData(dict/数组) → summary.cases 重算 → detailedResults 重算
 */
export function extractInitialMetricData(reportData: unknown): CategoryMetricMatrix {
  // 1. 优先使用后端预计算的 metricData
  const preCalculatedRows = pickRawField(
    (reportData ?? {}) as Record<string, unknown>, 'metricData')

  // 处理 dict 格式: {category: {resource: {metric: value}}}
  if (isPlainObject(preCalculatedRows)) {
    const mergedData: CategoryMetricMatrix = {}
    Object.keys(preCalculatedRows).forEach(category => {
      const resData = preCalculatedRows[category]
      if (!isPlainObject(resData)) return
      mergedData[category] = {}
      Object.keys(resData).forEach(resourceKey => {
        const metrics = resData[resourceKey]
        if (!isPlainObject(metrics)) return
        mergedData[category]![resourceKey] = {}
        Object.keys(metrics).forEach(metricName => {
          mergedData[category]![resourceKey]![metricName] = Number(metrics[metricName] ?? 0)
        })
      })
    })

    const rawRows = pickRawField(
      (reportData ?? {}) as Record<string, unknown>, 'rawData')
    if (isPlainObject(rawRows)) {
      Object.keys(mergedData).forEach(category => {
        const resources = mergedData[category] ?? {}
        Object.keys(resources).forEach(resourceKey => {
          const resourceObj = resources[resourceKey]
          if (!isPlainObject(resourceObj)) return
          const resourceRawData = rawRows[resourceKey]
          if (!isPlainObject(resourceRawData)) return
          Object.keys(resourceRawData).forEach(key => {
            const rawValue = resourceRawData[key]
            if (typeof rawValue === 'number') {
              resourceObj[key] = rawValue
            } else if (Array.isArray(rawValue)) {
              resourceObj[key] = rawValue
            } else if (rawValue !== undefined && rawValue !== null) {
              resourceObj[key] = Number(rawValue)
            }
          })
        })
      })
    }

    return mergedData
  }

  if (Array.isArray(preCalculatedRows) && preCalculatedRows.length > 0) {
    const mergedData: CategoryMetricMatrix = {}
    ;(preCalculatedRows as RawCategoryRow[]).forEach(row => {
      if (!row) return
      // adapter 对扁平行输出 categories: []（空数组），需与 undefined 同等视为扁平行走复制逻辑
      if (Array.isArray(row.categories) && row.categories.length > 0) {
        const resourceKey = row.resource || '0-默认资源'
        row.categories.forEach(c => {
          if (!c) return
          const category = String(c.categoryName ?? c.categoryId ?? '未分类')
          if (!mergedData[category]) mergedData[category] = {}
          if (!mergedData[category]![resourceKey]) mergedData[category]![resourceKey] = {}
          ;(c.metrics || []).forEach(m => {
            if (!m || !m.metric) return
            mergedData[category]![resourceKey]![m.metric] = Number(m.value ?? 0)
          })
        })
      } else {
        // 扁平行（resource 级别全局平均，无 category 维度）：将资源级数据复制到所有已知
        // 分组下，保证按已知分组查找能命中（与 V9.7.10 行为一致）；无已知分组时回退行自带分类/未分类
        const knownCategories = pickRawField(
          (reportData ?? {}) as Record<string, unknown>, 'caseCategories')
        const knownList = Array.isArray(knownCategories)
          ? knownCategories.map(c => String(c)).filter(Boolean)
          : []
        const rowCategory = String(row.categoryName ?? row.categoryId ?? '未分类')
        const categories = knownList.length > 0 ? knownList : [rowCategory]
        const resourceKey = row.resource || '0-默认资源'
        categories.forEach(category => {
          if (!mergedData[category]) mergedData[category] = {}
          if (!mergedData[category]![resourceKey]) mergedData[category]![resourceKey] = {}
          if (Array.isArray(row.metrics)) {
            row.metrics.forEach(m => {
              if (!m || !m.metric) return
              mergedData[category]![resourceKey]![m.metric] = Number(m.value ?? 0)
            })
          } else {
            const metricName = row.metric
            if (!metricName) return
            mergedData[category]![resourceKey]![metricName] = Number(row.value ?? 0)
          }
        })
      }
    })

    const rawRows = pickRawField(
      (reportData ?? {}) as Record<string, unknown>, 'rawData') as RawDataRow[] | undefined
    if (Array.isArray(rawRows) && rawRows.length > 0) {
      const rawMap: Record<string, Record<string, unknown>> = {}
      rawRows.forEach(r => {
        if (!r || !r.resource) return
        if (!rawMap[r.resource]) rawMap[r.resource] = {}
        if (Array.isArray(r.metrics)) {
          r.metrics.forEach(m => {
            if (!m || !m.metric) return
            rawMap[r.resource]![m.metric] = Array.isArray(m.values) ? m.values : []
          })
        } else if (r.metric) {
          rawMap[r.resource]![r.metric] = Array.isArray(r.values) ? r.values : []
        }
      })

      Object.keys(mergedData).forEach(category => {
        const resources = mergedData[category] ?? {}
        Object.keys(resources).forEach(resourceKey => {
          const resourceRawData = rawMap[resourceKey]
          if (!resourceRawData) return
          Object.keys(resourceRawData).forEach(metricName => {
            mergedData[category]![resourceKey]![`${metricName}_raw`] = resourceRawData[metricName] as number[]
          })
        })
      })
    }

    return mergedData
  }

  // 3. Fallback: Reconstruct metricData from reportData.summary.cases if available
  const cases = pickRawField(
    (reportData ?? {}) as Record<string, unknown>, 'cases')
  if (Array.isArray(cases) && cases.length > 0) {
    console.log('[CaseCategoryComparison] Reconstructing metricData from cases')
    const reconstructedData: CategoryMetricMatrix = {}
    const accumulator: Record<string, Record<string, Record<string, MetricAccumulator>>> = {}

    ;(cases as RawCaseItem[]).forEach(caseItem => {
      const category = caseItem?.category || 'Uncategorized'
      const caseMetrics = caseItem?.metrics || {}

      if (!accumulator[category]) accumulator[category] = {}

      if (Array.isArray(caseMetrics)) {
        caseMetrics.forEach(group => {
          if (!group || !group.resource || !Array.isArray(group.metrics)) return
          const resourceKey = group.resource
          if (!accumulator[category]![resourceKey]) accumulator[category]![resourceKey] = {}
          group.metrics.forEach(m => {
            if (!m || !m.metric) return
            const dim = m.metric
            if (!accumulator[category]![resourceKey]![dim]) {
              accumulator[category]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
            }
            const val = m.value
            if (val !== null && val !== undefined) {
              accumulator[category]![resourceKey]![dim]!.sum += Number(val)
              accumulator[category]![resourceKey]![dim]!.count += 1
              accumulator[category]![resourceKey]![dim]!.values.push(Number(val))
            }
          })
        })
      } else {
        Object.keys(caseMetrics).forEach(resourceKey => {
          if (!accumulator[category]![resourceKey]) accumulator[category]![resourceKey] = {}

          const metrics = caseMetrics[resourceKey]
          Object.keys(metrics).forEach(dim => {
            if (!accumulator[category]![resourceKey]![dim]) {
              accumulator[category]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
            }
            const val = metrics[dim]
            if (val !== null && val !== undefined) {
              accumulator[category]![resourceKey]![dim]!.sum += Number(val)
              accumulator[category]![resourceKey]![dim]!.count += 1
              accumulator[category]![resourceKey]![dim]!.values.push(Number(val))
            }
          })
        })
      }
    })

    // 计算均值并填充结果矩阵
    Object.keys(accumulator).forEach(category => {
      reconstructedData[category] = {}
      Object.keys(accumulator[category]!).forEach(resourceKey => {
        reconstructedData[category]![resourceKey] = {}
        Object.keys(accumulator[category]![resourceKey]!).forEach(dim => {
          const stats = accumulator[category]![resourceKey]![dim]!
          if (stats.count > 0) {
            reconstructedData[category]![resourceKey]![dim] = Number((stats.sum / stats.count).toFixed(4))
            reconstructedData[category]![resourceKey]![`${dim}_raw`] = stats.values
          } else {
            reconstructedData[category]![resourceKey]![dim] = 0
          }
        })
      })
    })

    return reconstructedData
  }

  // 2. 如果没有预计算数据，则从 detailedResults 中提取
  const detailedResults = pickRawField(
    (reportData ?? {}) as Record<string, unknown>, 'detailedResults')
  const dataAccumulator: Record<string, Record<string, {
    counts: Record<string, number>
    sums: Record<string, number>
    values: Record<string, number[]>
  }>> = {}

  if (Array.isArray(detailedResults) && detailedResults.length > 0) {
    ;(detailedResults as RawDetailedResult[]).forEach(result => {
      // 有分组用分组名；无分组无标签时回退用例名；有标签保持分组分类
      let category = '其他'

      if (result?.testCaseGroup) {
        category = result.testCaseGroup.name
      } else if (!result?.testCaseTags && result?.testCaseName) {
        category = result.testCaseName
      }

      let resourceId = ''
      let resourceName = ''
      if (result?.device) {
        resourceId = String(result.device.id)
        resourceName = result.device.name
      } else if (result?.api) {
        resourceId = String(result.api.id)
        resourceName = result.api.name
      } else {
        resourceId = 'default'
        resourceName = '默认资源'
      }

      const resourceKey = `${resourceId}_${resourceName}`

      if (!dataAccumulator[category]) {
        dataAccumulator[category] = {}
      }
      if (!dataAccumulator[category]![resourceKey]) {
        dataAccumulator[category]![resourceKey] = {
          counts: {},
          sums: {},
          values: {}
        }
      }
      const bucket = dataAccumulator[category]![resourceKey]!

      if (result?.dimensionScores) {
        result.dimensionScores.forEach(dim => {
          if (!bucket.counts[dim.dimensionName]) {
            bucket.counts[dim.dimensionName] = 0
            bucket.sums[dim.dimensionName] = 0
            bucket.values[dim.dimensionName] = []
          }

          bucket.counts[dim.dimensionName]++
          bucket.sums[dim.dimensionName] += dim.score
          bucket.values[dim.dimensionName].push(dim.score)
        })
      } else if (result?.metrics) {
        Object.entries(result.metrics).forEach(([dimName, value]) => {
          if (!bucket.counts[dimName]) {
            bucket.counts[dimName] = 0
            bucket.sums[dimName] = 0
            bucket.values[dimName] = []
          }

          bucket.counts[dimName]++
          bucket.sums[dimName] += Number(value ?? 0)
          bucket.values[dimName].push(Number(value ?? 0))
        })
      }
      void result.testCaseId
    })
  }

  const extractedMetricData: CategoryMetricMatrix = {}

  Object.entries(dataAccumulator).forEach(([category, resources]) => {
    extractedMetricData[category] = {}

    Object.entries(resources).forEach(([resourceKey, data]) => {
      if (!extractedMetricData[category]![resourceKey]) {
        extractedMetricData[category]![resourceKey] = {}
      }

      Object.entries(data.counts).forEach(([dimName, count]) => {
        const sum = data.sums[dimName]
        const average = count > 0 ? sum / count : 0

        extractedMetricData[category]![resourceKey]![dimName] = average

        extractedMetricData[category]![resourceKey]![`${dimName}_raw`] = data.values[dimName]
      })
    })
  })

  return extractedMetricData
}

/** 分类对比筛选依赖（分类/标签选中项与全量列表，均为 Ref） */
interface CategoryComputeDeps {
  selectedCategories: { value: string[] }
  selectedTags: { value: string[] }
  allAvailableCategories: { value: string[] }
  allAvailableTags: { value: string[] }
}

/** 按分类/标签筛选条件从用例列表重算分类×资源×指标矩阵 */
export function computeMetricDataFromCases(cases: unknown, deps: CategoryComputeDeps) {
  const { selectedCategories, selectedTags, allAvailableCategories, allAvailableTags } = deps
  const reconstructedData: CategoryMetricMatrix = {}
  const accumulator: Record<string, Record<string, Record<string, MetricAccumulator>>> = {}

  const selectedCategorySet = new Set(selectedCategories.value || [])
  const selectedTagSet = new Set(selectedTags.value || [])
  const includeUntagged = selectedTagSet.has('无标签') || selectedTagSet.has('未标记')
  selectedTagSet.delete('无标签')
  selectedTagSet.delete('未标记')
  const useCategoryFilter = selectedCategorySet.size > 0 && selectedCategorySet.size !== (allAvailableCategories.value || []).length
  const useTagFilter =
    (selectedTagSet.size > 0 || includeUntagged) &&
    ((selectedTags.value || []).length !== (allAvailableTags.value || []).length)

  ;(Array.isArray(cases) ? (cases as RawCaseItem[]) : []).forEach(caseItem => {
    if (!caseItem) return
    const category = caseItem.category || '未分类'
    if (useCategoryFilter && !selectedCategorySet.has(category)) return

    const caseTagsRaw = caseItem.tags || []
    const caseTagNames = Array.isArray(caseTagsRaw)
      ? caseTagsRaw.map(t => (typeof t === 'object' ? t?.name : t)).filter((t): t is string => Boolean(t))
      : []
    if (useTagFilter) {
      const hasTagMatch = caseTagNames.some(t => selectedTagSet.has(t))
      const isUntagged = caseTagNames.length === 0
      if (!hasTagMatch && !(includeUntagged && isUntagged)) return
    }

    const caseMetrics = caseItem.metrics || {}
    if (!accumulator[category]) accumulator[category] = {}

    if (Array.isArray(caseMetrics)) {
      caseMetrics.forEach(group => {
        if (!group || !group.resource || !Array.isArray(group.metrics)) return
        const resourceKey = group.resource
        if (!accumulator[category]![resourceKey]) accumulator[category]![resourceKey] = {}
        group.metrics.forEach(m => {
          if (!m || !m.metric) return
          const dim = m.metric
          if (!accumulator[category]![resourceKey]![dim]) {
            accumulator[category]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
          }
          const val = m.value
          if (val !== null && val !== undefined) {
            accumulator[category]![resourceKey]![dim]!.sum += Number(val)
            accumulator[category]![resourceKey]![dim]!.count += 1
            accumulator[category]![resourceKey]![dim]!.values.push(Number(val))
          }
        })
      })
    } else {
      Object.keys(caseMetrics).forEach(resourceKey => {
        if (!accumulator[category]![resourceKey]) accumulator[category]![resourceKey] = {}
        const metrics = caseMetrics[resourceKey] || {}
        Object.keys(metrics).forEach(dim => {
          if (!accumulator[category]![resourceKey]![dim]) {
            accumulator[category]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
          }
          const val = metrics[dim]
          if (val !== null && val !== undefined) {
            accumulator[category]![resourceKey]![dim]!.sum += Number(val)
            accumulator[category]![resourceKey]![dim]!.count += 1
            accumulator[category]![resourceKey]![dim]!.values.push(Number(val))
          }
        })
      })
    }
  })

  Object.keys(accumulator).forEach(category => {
    reconstructedData[category] = {}
    Object.keys(accumulator[category]!).forEach(resourceKey => {
      reconstructedData[category]![resourceKey] = {}
      Object.keys(accumulator[category]![resourceKey]!).forEach(dim => {
        const stats = accumulator[category]![resourceKey]![dim]!
        if (stats.count > 0) {
          reconstructedData[category]![resourceKey]![dim] = Number((stats.sum / stats.count).toFixed(4))
          reconstructedData[category]![resourceKey]![`${dim}_raw`] = stats.values
        } else {
          reconstructedData[category]![resourceKey]![dim] = 0
        }
      })
    })
  })

  return reconstructedData
}

/** 分类对比图表构建依赖 */
interface CategoryChartDeps {
  activeDisplayType: { value: string }
  devices: { value: string[] }
  filteredCategories: { value: string[] }
  getRawDataValue: (category: string, device: string, metricName: string) => unknown
  getMetricValue: (category: string, device: string, metricName: string) => unknown
  getResourceLabel: (key: unknown) => unknown
  generateDistributionChartData: (
    devices: string[],
    deviceRawDataMap: Record<string, number[]>,
    allRawData: number[],
    getResourceLabel: (key: unknown) => unknown
  ) => unknown
  chartColors: string[]
  chartBorderColors: string[]
}

/** 分类对比图表构建（柱状/折线/雷达共用 + 正态分布模式） */
export function createCategoryChartData(deps: CategoryChartDeps) {
  const {
    activeDisplayType, devices, filteredCategories, getRawDataValue, getMetricValue,
    getResourceLabel, generateDistributionChartData, chartColors, chartBorderColors
  } = deps

  const getChartData = (metricName: string) => {
    if (activeDisplayType.value === 'distribution') {
      let allRawData: number[] = []
      const deviceRawDataMap: Record<string, number[]> = {}

      devices.value.forEach(device => {
        deviceRawDataMap[device] = []
      })

      devices.value.forEach(device => {
        const seenArrays = new Set<unknown>()
        filteredCategories.value.forEach(category => {
          const rawData = getRawDataValue(category, device, metricName)
          if (seenArrays.has(rawData)) return
          seenArrays.add(rawData)
          const values = Array.isArray(rawData) ? rawData : []
          deviceRawDataMap[device] = deviceRawDataMap[device].concat(values)
          allRawData = allRawData.concat(values)
        })
      })

      allRawData = allRawData.filter(v => typeof v === 'number' && !isNaN(v) && isFinite(v))
      Object.keys(deviceRawDataMap).forEach(device => {
        deviceRawDataMap[device] = deviceRawDataMap[device].filter(v => typeof v === 'number' && !isNaN(v) && isFinite(v))
      })

      return generateDistributionChartData(devices.value, deviceRawDataMap, allRawData, getResourceLabel)
    }

    const chartData = {
      labels: filteredCategories.value,
      datasets: devices.value.map((device, index: number) => {
        const color = chartColors[index % chartColors.length]
        const borderColor = chartBorderColors[index % chartBorderColors.length]

        const data = filteredCategories.value.map((category) => {
          return parseFloat(getMetricValue(category, device, metricName) as string)
        })

        return {
          label: getResourceLabel(device),
          data: data,
          backgroundColor: color,
          borderColor: borderColor,
          borderWidth: 1
        }
      })
    }

    return chartData
  }

  return { getChartData }
}

/** 分类对比取值依赖（metricData 矩阵 Ref） */
interface CategoryMetricValueDeps {
  metricData: { value: CategoryMetricMatrix }
}

/** 分类对比矩阵取值器：按 分类/设备/指标名 兜底匹配取均值与原始值 */
export function createCategoryMetricValueGetters(deps: CategoryMetricValueDeps) {
  const { metricData } = deps

  const getMetricValue = (category: string, device: string | { id?: unknown; name?: string; deviceName?: string }, metricName: string) => {
    if (metricData.value) {
      const categoryData = metricData.value[category]
      if (categoryData) {
        if (typeof device === 'string' && categoryData[device] && categoryData[device][metricName] !== undefined) {
          return categoryData[device][metricName]
        }

        if (typeof device === 'object' && device !== null) {
          const resourceKey = `${device.id}-${device.name}`
          if (categoryData[resourceKey] && categoryData[resourceKey][metricName] !== undefined) {
            return categoryData[resourceKey][metricName]
          }
        }

        const deviceName = typeof device === 'object' && device !== null ? (device.name || device.deviceName) :
                          (typeof device === 'string' && device.includes('-') ? device.split('-').slice(1).join('-') : device)

        const entries = Object.entries(categoryData)
        for (const [key, data] of entries) {
          const currentResourceName = key.includes('-') ? key.split('-').slice(1).join('-') : key
          if (currentResourceName === deviceName && data && data[metricName] !== undefined) {
            return data[metricName]
          }
        }
      }
    }

    return 0
  }

  const getRawDataValue = (category: string, device: string | { id?: unknown; name?: string; deviceName?: string }, metricName: string) => {
    const rawDataKey = `${metricName}_raw`
    if (metricData.value) {
      const categoryData = metricData.value[category]
      if (categoryData) {
        if (typeof device === 'string' && categoryData[device] && Array.isArray(categoryData[device][rawDataKey])) {
          return categoryData[device][rawDataKey]
        }

        if (typeof device === 'object' && device !== null) {
          const resourceKey = `${device.id}-${device.name}`
          if (categoryData[resourceKey] && Array.isArray(categoryData[resourceKey]![rawDataKey])) {
            return categoryData[resourceKey]![rawDataKey]
          }
        }

        const deviceName = typeof device === 'object' && device !== null ? (device.name || device.deviceName) :
                          (typeof device === 'string' && device.includes('-') ? device.split('-').slice(1).join('-') : device)
        const entries = Object.entries(categoryData)
        for (const [key, data] of entries) {
          const currentResourceName = key.includes('-') ? key.split('-').slice(1).join('-') : key
          if (currentResourceName === deviceName && data && Array.isArray(data[rawDataKey])) {
            return data[rawDataKey]
          }
        }
      }
    }
    return []
  }

  return { getMetricValue, getRawDataValue }
}
