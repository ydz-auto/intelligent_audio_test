/**
 * 标签对比 helper —— 标签×资源×指标均值矩阵的提取/重算
 *
 * 输入为 adapter 转换后的 camelCase Domain 行（ReportTagMetricByResource）。
 * 输出统一为内存矩阵：{ [标签名]: { [资源键]: { [指标名]: number | number[] } } }
 */
import type { MetricAccumulator, MetricMatrix as TagMetricMatrix } from '../../domain/model/report'

/** 后端预计算行（adapter 输出 camelCase） */
interface RawTagRow {
  /** camelCase（adapter 输出） */
  resource?: string
  tags?: Array<{
    tagId?: unknown
    tagName?: string
    metrics?: Array<{ metric: string; value: unknown }>
  }>
  /** 兼容扁平行 */
  tagName?: string
  tagId?: unknown
  metrics?: Array<{ metric: string; value: unknown }>
  metric?: string
  value?: unknown
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
  id?: unknown
  tags?: Array<string | { name?: string }> | string[]
  metrics?:
    | Array<{ resource: string; metrics: Array<{ metric: string; value: unknown }> }>
    | Record<string, Record<string, unknown>>
}

/** 用例维度明细（adapter 输出 camelCase） */
interface RawDetailedResult {
  testCaseId?: string | number
  testCaseTags?: Array<string | { name: string }>
  testCase?: { tags?: Array<string | { name: string }> }
  device?: { id: unknown; name: string }
  api?: { id: unknown; name: string }
  asr?: { referenceText?: string }
  dimensionScores?: Array<{ dimensionName: string; score: number }>
  metrics?: Record<string, unknown>
}

/** 标签对象（名称 + 可选 id） */
interface TagObject {
  id: unknown
  name: string
}

/** 从 reportData 上按 camelCase 读取字段（顶层优先，回退 summary） */
function pickRawField(reportData: Record<string, unknown>, camel: string): unknown {
  const summary = reportData.summary as Record<string, unknown> | undefined
  if (reportData[camel] !== undefined) return reportData[camel]
  if (summary && summary[camel] !== undefined) return summary[camel]
  return undefined
}

/** 标签维度归一：兼容字符串与 {name} 对象，回退未标记 */
function toTagName(tag: string | { name?: string }): string {
  if (typeof tag === 'string') return tag
  return tag?.name || ''
}

/**
 * 提取标签×资源×指标矩阵
 * 优先级：后端预计算 tagMetricData(数组) → summary.cases 重算 → detailedResults 重算
 */
export function extractInitialTagMetricData(reportData: unknown): TagMetricMatrix {
  if (!reportData) {
    return {}
  }
  const raw = reportData as Record<string, unknown>

  // 1. 优先使用后端预计算的 tagMetricData
  const preCalculatedRows = pickRawField(raw, 'tagMetricData')

  if (Array.isArray(preCalculatedRows) && preCalculatedRows.length > 0) {
    const mergedData: TagMetricMatrix = {}
    ;(preCalculatedRows as RawTagRow[]).forEach(row => {
      if (!row) return
      if (Array.isArray(row.tags)) {
        const resourceKey = row.resource || '0-默认资源'
        row.tags.forEach(t => {
          if (!t) return
          const tag = String(t.tagName ?? t.tagId ?? '未标记')
          if (!mergedData[tag]) mergedData[tag] = {}
          if (!mergedData[tag]![resourceKey]) mergedData[tag]![resourceKey] = {}
          ;(t.metrics || []).forEach(m => {
            if (!m || !m.metric) return
            mergedData[tag]![resourceKey]![m.metric] = Number(m.value ?? 0)
          })
        })
      } else {
        const tag = String(row.tagName ?? row.tagId ?? '未标记')
        const resourceKey = row.resource || '0-默认资源'
        if (!mergedData[tag]) mergedData[tag] = {}
        if (!mergedData[tag]![resourceKey]) mergedData[tag]![resourceKey] = {}
        if (Array.isArray(row.metrics)) {
          row.metrics.forEach(m => {
            if (!m || !m.metric) return
            mergedData[tag]![resourceKey]![m.metric] = Number(m.value ?? 0)
          })
        } else {
          const metricName = row.metric
          if (!metricName) return
          mergedData[tag]![resourceKey]![metricName] = Number(row.value ?? 0)
        }
      }
    })

    const rawRows = pickRawField(raw, 'rawData') as RawDataRow[] | undefined
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

      Object.keys(mergedData).forEach(tag => {
        const resources = mergedData[tag] ?? {}
        Object.keys(resources).forEach(resourceKey => {
          const resourceRawData = rawMap[resourceKey]
          if (!resourceRawData) return
          Object.keys(resourceRawData).forEach(metricName => {
            mergedData[tag]![resourceKey]![`${metricName}_raw`] = resourceRawData[metricName] as number[]
          })
        })
      })
    }

    return mergedData
  }

  // 3. Fallback: Reconstruct tagMetricData from reportData.summary.cases
  const cases = pickRawField(raw, 'cases')
  if (Array.isArray(cases) && cases.length > 0) {
    console.log('[CaseTagComparison] Reconstructing tagMetricData from cases')
    const reconstructedData: TagMetricMatrix = {}
    const accumulator: Record<string, Record<string, Record<string, MetricAccumulator>>> = {}

    ;(cases as RawCaseItem[]).forEach(caseItem => {
      const rawTags = caseItem?.tags
      const tags: Array<string | { name?: string }> = Array.isArray(rawTags) && rawTags.length > 0
        ? (rawTags as Array<string | { name?: string }>)
        : ['未标记']
      const caseMetrics = caseItem?.metrics || {}

      tags.forEach(tag => {
        const tagName = toTagName(tag)
        if (!tagName) return

        if (!accumulator[tagName]) accumulator[tagName] = {}

        if (Array.isArray(caseMetrics)) {
          caseMetrics.forEach(group => {
            if (!group || !group.resource || !Array.isArray(group.metrics)) return
            const resourceKey = group.resource
            if (!accumulator[tagName]![resourceKey]) accumulator[tagName]![resourceKey] = {}
            group.metrics.forEach(m => {
              if (!m || !m.metric) return
              const dim = m.metric
              if (!accumulator[tagName]![resourceKey]![dim]) {
                accumulator[tagName]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
              }
              const val = m.value
              if (val !== null && val !== undefined) {
                accumulator[tagName]![resourceKey]![dim]!.sum += Number(val)
                accumulator[tagName]![resourceKey]![dim]!.count += 1
                accumulator[tagName]![resourceKey]![dim]!.values.push(Number(val))
              }
            })
          })
        } else {
          Object.keys(caseMetrics).forEach(resourceKey => {
            if (!accumulator[tagName]![resourceKey]) accumulator[tagName]![resourceKey] = {}

            const metrics = caseMetrics[resourceKey]
            Object.keys(metrics).forEach(dim => {
              if (!accumulator[tagName]![resourceKey]![dim]) {
                accumulator[tagName]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
              }
              const val = metrics[dim]
              if (val !== null && val !== undefined) {
                accumulator[tagName]![resourceKey]![dim]!.sum += Number(val)
                accumulator[tagName]![resourceKey]![dim]!.count += 1
                accumulator[tagName]![resourceKey]![dim]!.values.push(Number(val))
              }
            })
          })
        }
      })
    })

    // 计算均值并填充结果矩阵
    Object.keys(accumulator).forEach(tag => {
      reconstructedData[tag] = {}
      Object.keys(accumulator[tag]!).forEach(resourceKey => {
        reconstructedData[tag]![resourceKey] = {}
        Object.keys(accumulator[tag]![resourceKey]!).forEach(dim => {
          const stats = accumulator[tag]![resourceKey]![dim]!
          if (stats.count > 0) {
            reconstructedData[tag]![resourceKey]![dim] = Number((stats.sum / stats.count).toFixed(4))
            reconstructedData[tag]![resourceKey]![`${dim}_raw`] = stats.values
          } else {
            reconstructedData[tag]![resourceKey]![dim] = 0
          }
        })
      })
    })

    return reconstructedData
  }

  // 2. 如果没有预计算数据，则从 detailedResults 中提取
  const detailedResults = pickRawField(raw, 'detailedResults')
  if (Array.isArray(detailedResults) && detailedResults.length > 0) {
    const detailed = detailedResults as RawDetailedResult[]
    const rawCases = pickRawField(raw, 'cases') as RawCaseItem[] | undefined
    const dataAccumulator: Record<string, Record<string, {
      counts: Record<string, number>
      sums: Record<string, number>
      values: Record<string, number[]>
    }>> = {}

    detailed.forEach(result => {
      const testCaseId = result?.testCaseId
      let tagObjects: TagObject[] = []
      let tags: string[] = []

      if (result?.testCaseTags && result.testCaseTags.length > 0) {
        tags = result.testCaseTags.map(tag => toTagName(tag))
        tagObjects = tags.map(tag => ({ id: tag, name: tag }))
      } else if (rawCases) {
        const testCase = rawCases.find(c => c?.id === testCaseId)
        const caseTags = testCase?.tags
        if (caseTags && Array.isArray(caseTags) && caseTags.length > 0) {
          tags = caseTags.map(tag => toTagName(tag as string | { name?: string }))
          tagObjects = tags.map(tag => ({ id: tag, name: tag }))
        }
      }

      const nestedTags = result?.testCase?.tags
      if (nestedTags && nestedTags.length > 0) {
        tags = nestedTags.map(tag => toTagName(tag))
        tagObjects = tags.map(tag => ({ id: tag, name: tag }))
      }

      if (tags.length === 0) {
        if (result?.asr?.referenceText) {
          const defaultTag = result.asr.referenceText.slice(0, 5)
          tags = [defaultTag]
          tagObjects = [{ id: defaultTag, name: defaultTag }]
        } else {
          const defaultTag = String(testCaseId ?? '').slice(0, 5)
          tags = [defaultTag]
          tagObjects = [{ id: defaultTag, name: defaultTag }]
        }
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

      tagObjects.forEach(tagObj => {
        const tagName = tagObj.name

        if (!dataAccumulator[tagName]) {
          dataAccumulator[tagName] = {}
        }
        if (!dataAccumulator[tagName]![resourceKey]) {
          dataAccumulator[tagName]![resourceKey] = {
            counts: {},
            sums: {},
            values: {}
          }
        }
        const bucket = dataAccumulator[tagName]![resourceKey]!

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
      })
    })

    const extractedTagMetricData: TagMetricMatrix = {}

    Object.entries(dataAccumulator).forEach(([tag, resources]) => {
      extractedTagMetricData[tag] = {}

      Object.entries(resources).forEach(([resourceKey, data]) => {
        // 同一矩阵同时落「资源名」与「原始资源键」两个键，便于取值端两种查找方式
        const resourceName = resourceKey.includes('_') ? resourceKey.split('_').slice(1).join('_') : resourceKey

        if (!extractedTagMetricData[tag]![resourceName]) {
          extractedTagMetricData[tag]![resourceName] = {}
        }
        if (!extractedTagMetricData[tag]![resourceKey]) {
          extractedTagMetricData[tag]![resourceKey] = {}
        }

        Object.entries(data.counts).forEach(([dimName, count]) => {
          const sum = data.sums[dimName]
          const average = count > 0 ? sum / count : 0

          extractedTagMetricData[tag]![resourceName]![dimName] = average
          extractedTagMetricData[tag]![resourceKey]![dimName] = average

          extractedTagMetricData[tag]![resourceName]![`${dimName}_raw`] = data.values[dimName]
          extractedTagMetricData[tag]![resourceKey]![`${dimName}_raw`] = data.values[dimName]
        })
      })
    })

    return extractedTagMetricData
  }

  return {}
}

/** 标签对比筛选依赖（标签/分类选中项，均为 Ref） */
interface TagComputeDeps {
  selectedTags: { value: string[] }
  selectedCategories: { value: string[] }
}

/** 按标签/分类筛选条件从用例列表重算标签×资源×指标矩阵 */
export function computeTagMetricDataFromCases(cases: unknown, deps: TagComputeDeps) {
  const { selectedTags, selectedCategories } = deps
  const selectedTagSet = new Set(selectedTags.value || [])
  const selectedCategorySet = new Set(selectedCategories.value || [])
  const includeUntagged = selectedTagSet.has('无标签') || selectedTagSet.has('未标记')
  selectedTagSet.delete('无标签')
  selectedTagSet.delete('未标记')
  const useTagFilter = selectedTagSet.size > 0 || includeUntagged
  const useCategoryFilter = selectedCategorySet.size > 0

  const accumulator: Record<string, Record<string, Record<string, MetricAccumulator>>> = {}

  ;(Array.isArray(cases) ? (cases as RawCaseItem[]) : []).forEach(caseItem => {
    if (!caseItem) return

    const category = caseItem.category || '未分类'
    if (useCategoryFilter && !selectedCategorySet.has(category)) return

    const caseTagsRaw = caseItem.tags || []
    const caseTagNames = Array.isArray(caseTagsRaw)
      ? caseTagsRaw.map(t => (typeof t === 'object' ? t?.name : t)).filter((t): t is string => Boolean(t))
      : []

    const tagsToAggregate = useTagFilter
      ? caseTagNames.filter(t => selectedTagSet.has(t))
      : caseTagNames

    if (useTagFilter && includeUntagged && caseTagNames.length === 0) {
      tagsToAggregate.push('未标记')
    }

    if (tagsToAggregate.length === 0) return

    const caseMetrics = caseItem.metrics || {}

    tagsToAggregate.forEach(tagName => {
      if (!accumulator[tagName]) accumulator[tagName] = {}

      if (Array.isArray(caseMetrics)) {
        caseMetrics.forEach(group => {
          if (!group || !group.resource || !Array.isArray(group.metrics)) return
          const resourceKey = group.resource
          if (!accumulator[tagName]![resourceKey]) accumulator[tagName]![resourceKey] = {}
          group.metrics.forEach(m => {
            if (!m || !m.metric) return
            const dim = m.metric
            if (!accumulator[tagName]![resourceKey]![dim]) {
              accumulator[tagName]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
            }
            const val = m.value
            if (val !== null && val !== undefined) {
              accumulator[tagName]![resourceKey]![dim]!.sum += Number(val)
              accumulator[tagName]![resourceKey]![dim]!.count += 1
              accumulator[tagName]![resourceKey]![dim]!.values.push(Number(val))
            }
          })
        })
      } else {
        Object.keys(caseMetrics).forEach(resourceKey => {
          if (!accumulator[tagName]![resourceKey]) accumulator[tagName]![resourceKey] = {}
          const metrics = caseMetrics[resourceKey] || {}
          Object.keys(metrics).forEach(dim => {
            if (!accumulator[tagName]![resourceKey]![dim]) {
              accumulator[tagName]![resourceKey]![dim] = { sum: 0, count: 0, values: [] }
            }
            const val = metrics[dim]
            if (val !== null && val !== undefined) {
              accumulator[tagName]![resourceKey]![dim]!.sum += Number(val)
              accumulator[tagName]![resourceKey]![dim]!.count += 1
              accumulator[tagName]![resourceKey]![dim]!.values.push(Number(val))
            }
          })
        })
      }
    })
  })

  const reconstructedData: TagMetricMatrix = {}
  Object.keys(accumulator).forEach(tag => {
    reconstructedData[tag] = {}
    Object.keys(accumulator[tag]!).forEach(resourceKey => {
      reconstructedData[tag]![resourceKey] = {}
      Object.keys(accumulator[tag]![resourceKey]!).forEach(dim => {
        const stats = accumulator[tag]![resourceKey]![dim]!
        if (stats.count > 0) {
          reconstructedData[tag]![resourceKey]![dim] = Number((stats.sum / stats.count).toFixed(4))
          reconstructedData[tag]![resourceKey]![`${dim}_raw`] = stats.values
        } else {
          reconstructedData[tag]![resourceKey]![dim] = 0
        }
      })
    })
  })

  return reconstructedData
}

/** 标签对比图表构建依赖 */
interface TagChartDeps {
  activeDisplayType: { value: string }
  devices: { value: string[] }
  filteredTags: { value: string[] }
  getRawDataValue: (tag: string, device: string, metricName: string) => unknown
  getMetricValue: (tag: string, device: string, metricName: string) => unknown
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

/** 标签对比图表构建（柱状/折线/雷达共用 + 正态分布模式） */
export function createTagChartData(deps: TagChartDeps) {
  const {
    activeDisplayType, devices, filteredTags, getRawDataValue, getMetricValue,
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
        filteredTags.value.forEach(tag => {
          const rawData = getRawDataValue(tag, device, metricName)
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
      labels: filteredTags.value,
      datasets: devices.value.map((device, index: number) => {
        const color = chartColors[index % chartColors.length]
        const borderColor = chartBorderColors[index % chartBorderColors.length]

        const data = filteredTags.value.map((tag) => {
          return parseFloat(getMetricValue(tag, device, metricName) as string)
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
