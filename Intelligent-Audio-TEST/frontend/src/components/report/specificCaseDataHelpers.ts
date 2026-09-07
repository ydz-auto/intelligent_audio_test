import { reportsPort } from '@/composables/report/reportsPort'
import { normalizeAudioFields } from '../../utils/audioUtils'

export function getValidResources(data: any) {
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

const _metricsMapCache = new WeakMap()
const _textMapCache = new WeakMap()

/** 指标条目对象值形态（保留维度归组信息；前端视图模型 camelCase，输入兼容后端 metrics 条目双形态） */
export interface MetricEntryValue {
  value: number | string | null
  dimensionType: string
  parentDimensionId: number | string | null
  parentDimensionName: string | null
}

function toMetricEntry(m: { value?: unknown; dimension_type?: unknown; dimensionType?: unknown; parent_dimension_id?: unknown; parentDimensionId?: unknown; parent_dimension_name?: unknown; parentDimensionName?: unknown }): MetricEntryValue {
  return {
    value: (m.value ?? null) as MetricEntryValue['value'],
    dimensionType: String(m.dimensionType || m.dimension_type || 'main'),
    parentDimensionId: (m.parentDimensionId ?? m.parent_dimension_id ?? null) as MetricEntryValue['parentDimensionId'],
    parentDimensionName: (m.parentDimensionName ?? m.parent_dimension_name ?? null) as MetricEntryValue['parentDimensionName']
  }
}

/** 解包指标值：对象值形态 { value } 取内层，裸值原样返回 */
export function unwrapMetricValue(raw: unknown): number | string | null | undefined {
  if (raw !== null && typeof raw === 'object' && 'value' in (raw as Record<string, unknown>)) {
    return (raw as MetricEntryValue).value
  }
  return raw as number | string | null | undefined
}

export function toMetricsMap(caseItem: any) {
  if (!caseItem || typeof caseItem !== 'object') return {}
  if (_metricsMapCache.has(caseItem)) {
    return _metricsMapCache.get(caseItem)
  }
  const metrics = caseItem?.metrics
  let result: any = {}
  if (Array.isArray(metrics)) {
    if (metrics.length > 0 && metrics[0]?.resource) {
      const map: any = {}
      metrics.forEach((group: any) => {
        if (!group || !group.resource) return
        const resource = group.resource
        if (!map[resource]) map[resource] = {}
        if (Array.isArray(group.metrics)) {
          group.metrics.forEach((m: any) => {
            if (!m || !m.metric) return
            map[resource][m.metric] = toMetricEntry(m)
          })
        }
      })
      result = map
    } else {
      const flatMap: any = {}
      metrics.forEach((m: any) => {
        if (!m || !m.metric) return
        flatMap[m.metric] = toMetricEntry(m)
      })
      result = flatMap
    }
  } else {
    result = metrics || {}
  }
  _metricsMapCache.set(caseItem, result)
  return result
}

export function toTextMap(objWithResults: any) {
  if (!objWithResults || typeof objWithResults !== 'object') return {}
  if (_textMapCache.has(objWithResults)) {
    return _textMapCache.get(objWithResults)
  }
  const results = objWithResults?.results
  let result: any = {}
  if (Array.isArray(results)) {
    const map: any = {}
    results.forEach((r: any) => {
      if (!r || !r.resource) return
      map[r.resource] = { text: r.text || '' }
    })
    result = map
  } else {
    result = results || {}
  }
  _textMapCache.set(objWithResults, result)
  return result
}

export function createCaseDataHelpers(deps: {
  props: any
  cases: any
  totalCases: any
  currentPage: any
  pageSize: any
  casesLoading: any
  casesLoadError: any
  searchKeyword: any
  selectedCategories: any
  selectedTags: any
  selectedMetrics: any
  sortDimension: any
  selectedSortMetric: any
  sortOrder: any
  processTags: (tags: any) => any[]
}) {
  const {
    props, cases, totalCases, currentPage, pageSize,
    casesLoading, casesLoadError,
    searchKeyword, selectedCategories, selectedTags, selectedMetrics,
    sortDimension, selectedSortMetric, sortOrder,
    processTags
  } = deps

  function extractCasesFromReportData(reportData: any) {
    // 优先级1: 使用 cases 字段（新格式）
    if (reportData.cases && Array.isArray(reportData.cases) && reportData.cases.length > 0) {
      console.log('从 cases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.cases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级2: 使用 summary.cases
    if (reportData.summary?.cases && Array.isArray(reportData.summary.cases) && reportData.summary.cases.length > 0) {
      console.log('从 summary.cases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.summary.cases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级3: 使用 detailedResults
    if (reportData.detailedResults && Array.isArray(reportData.detailedResults) && reportData.detailedResults.length > 0) {
      console.log('从 detailedResults 提取用例数据')
      const casesMap = new Map();

      reportData.detailedResults.forEach((result: any) => {
        const testCaseId = result.testCaseId ?? result.testCase?.id;
        const testCaseName = result.testCaseName ?? result.testCase?.name ?? '未知用例';

        if (!testCaseId) return;

        let resourceName = '';
        let resourceKey = '';
        if (result.device) {
          resourceName = result.device.name;
          resourceKey = `${result.device.id}_${resourceName}`;
        } else if (result.api) {
          resourceName = result.api.name;
          resourceKey = `${result.api.id}_${resourceName}`;
        } else {
          resourceName = '默认资源';
          resourceKey = `default_${resourceName}`;
        }

        let caseItem: any = casesMap.get(testCaseId);
        if (!caseItem) {
          const asrRef = result.asr?.referenceText ?? ''
          const tranRef = result.translation?.referenceText ?? ''

          caseItem = {
            id: testCaseId,
            name: testCaseName,
            category: result.testCaseGroup?.name ?? result.testCaseType ?? '其他',
            description: result.description || '',
            tags: processTags(result.testCaseTags ?? []),
            audios: result.audios ?? [],
            asr: {
              referenceText: asrRef,
              results: {}
            },
            translation: {
              referenceText: tranRef,
              results: {}
            },
            metrics: {},
            results: [],
            logs: result.logs ?? ''
          };
          casesMap.set(testCaseId, caseItem);
        }

        if ((!caseItem.audios || caseItem.audios.length === 0) && Array.isArray(result.audios) && result.audios.length > 0) {
          caseItem.audios = result.audios;
        }

        if (result.asr) {
          caseItem.asr.results[resourceKey] = {text: result.asr.resultText ?? '', score: 0};
        }

        if (result.translation) {
          caseItem.translation.results[resourceKey] = {text: result.translation.resultText ?? '', score: 0};
        }

        if (!caseItem.metrics[resourceKey]) {
          caseItem.metrics[resourceKey] = {};
        }

        const dimensionScores = result.dimensionScores;
        if (Array.isArray(dimensionScores)) {
          dimensionScores.forEach((dim: any) => {
            const dimName = dim.dimensionName;
            if (dimName) {
              caseItem.metrics[resourceKey][dimName] = dim.score;
            }
          });
        } else if (result.metrics) {
          Object.entries(result.metrics).forEach(([dimName, value]) => {
            caseItem.metrics[resourceKey][dimName] = value;
          });
        }

        const createdAt = result.createdAt ?? 0;
        if (!Array.isArray(caseItem.results)) {
          caseItem.results = [];
        }
        const existing = caseItem.results.find((r: any) => r.resource === resourceKey);
        const row = { resource: resourceKey, status: result.status || '未知', startTime: createdAt, endTime: createdAt };
        if (existing) {
          Object.assign(existing, row);
        } else {
          caseItem.results.push(row);
        }
      });

      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return Array.from(casesMap.values()).map((c: any) => normalizeAudioFields(c, taskType));
    }

    // 备选方案：使用reportData中的cases或summary中的cases
    if (reportData.cases) {
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return (reportData.cases || []).map((c: any) => normalizeAudioFields(c, taskType));
    } else if (reportData.summary?.cases) {
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return (reportData.summary.cases || []).map((c: any) => normalizeAudioFields(c, taskType));
    }

    return [];
  }

  function normalizeCasesForUi(caseItems: any) {
    const taskType = props.reportData?.taskType || 'all'
    try {
      return (caseItems || []).map((c0: any) => {
        const c = normalizeAudioFields(c0, taskType)
        if (!c || typeof c !== 'object') return c
        const metricsMap = toMetricsMap(c)
        const asrMap = toTextMap(c.asr)
        const tranMap = toTextMap(c.translation)

        const algoResults = c.algorithmResults || []
        const refParams = c.referenceParams || {}

        return {
          ...c,
          metrics: metricsMap,
          asr: c.asr ? { ...c.asr, results: asrMap } : c.asr,
          translation: c.translation ? { ...c.translation, results: tranMap } : c.translation,
          algorithmResults: algoResults,
          algorithmType: c.algorithmType || '',
          referenceParams: refParams,
          rttmRes: c.rttmRes,
          stmRes: c.stmRes,
          rttmRef: c.rttmRef,
          stmRef: c.stmRef
        }
      })
    } catch (e) {
      console.error('normalizeCasesForUi error:', e)
      return caseItems || []
    }
  }

  // 后端分页加载当前页用例（排序也由后端处理）
  async function loadCasesPage(reportId: any) {
    casesLoading.value = true
    casesLoadError.value = ''
    try {
      const params: any = {
        page: currentPage.value,
        perPage: pageSize.value,
      }
      if (searchKeyword.value) params.keyword = searchKeyword.value
      if (selectedCategories.value.length > 0) params.categories = selectedCategories.value
      if (selectedTags.value.length > 0) params.tags = selectedTags.value
      if (selectedMetrics.value.length > 0) params.metrics = selectedMetrics.value
      if (sortDimension.value === '评估维度' && selectedSortMetric.value) {
        params.sortBy = 'metric'
        params.sortMetric = selectedSortMetric.value
        params.sortOrder = sortOrder.value
      } else {
        params.sortBy = sortDimension.value
        params.sortOrder = sortOrder.value
      }
      const data = await reportsPort.searchCases(reportId, params)
      const items = data?.items || []
      totalCases.value = data?.total || 0
      cases.value = normalizeCasesForUi(items)
    } catch (e: any) {
      console.error('加载报告用例失败:', e)
      casesLoadError.value = e?.message || '加载用例失败'
    } finally {
      casesLoading.value = false
    }
  }

  // 导出模式：拉取全量用例数据
  async function loadAllCasesForExport(reportId: any) {
    casesLoading.value = true
    casesLoadError.value = ''
    try {
      const params: any = { page: 1, perPage: 999999 }
      if (searchKeyword.value) params.keyword = searchKeyword.value
      if (selectedCategories.value.length > 0) params.categories = selectedCategories.value
      if (selectedTags.value.length > 0) params.tags = selectedTags.value
      if (selectedMetrics.value.length > 0) params.metrics = selectedMetrics.value
      if (sortDimension.value === '评估维度' && selectedSortMetric.value) {
        params.sortBy = 'metric'
        params.sortMetric = selectedSortMetric.value
        params.sortOrder = sortOrder.value
      } else {
        params.sortBy = sortDimension.value
        params.sortOrder = sortOrder.value
      }
      const data = await reportsPort.searchCases(reportId, params)
      const items = data?.items || []
      totalCases.value = data?.total || 0
      cases.value = normalizeCasesForUi(items)
    } catch (e: any) {
      console.error('加载全量用例失败:', e)
      casesLoadError.value = e?.message || '加载用例失败'
    } finally {
      casesLoading.value = false
    }
  }

  return { extractCasesFromReportData, normalizeCasesForUi, loadCasesPage, loadAllCasesForExport }
}
