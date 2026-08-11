import { reportsApi } from '../../utils/api'

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

export function normalizeAudioFields(caseItem: any, taskType: string) {
  if (!caseItem || typeof caseItem !== 'object') return caseItem
  const normalized = { ...caseItem }

  if (normalized.audios && Array.isArray(normalized.audios) && normalized.audios.length > 0) {
    normalized.audioList = normalized.audios.map((audio: any, idx: number) => {
      let typeLabel = '测试音频'
      const audioType = audio.testType ?? audio.audioType ?? audio.test_type ?? audio.audio_type ?? 'api'
      if (audioType === 'api') {
        typeLabel = 'API测试音频'
      } else if (audioType === 'e2e') {
        typeLabel = 'E2E测试音频'
      } else if (audioType === 'noise') {
        typeLabel = '噪声'
      } else if (audioType === 'dry') {
        typeLabel = '干声'
      }

      return {
        id: audio.id,
        path: audio.url ?? audio.path,
        label: audio.label ?? audio.filename ?? `${typeLabel} ${idx + 1}`,
        type: audioType,
        filename: audio.filename,
        duration: audio.duration,
        spl: audio.spl,
        playOrder: audio.playOrder ?? audio.play_order,
        noiseSpl: audio.noiseSpl ?? audio.noise_spl,
        deviceId: audio.playbackDeviceId ?? audio.deviceId ?? audio.device_id,
        deviceName: audio.playbackDeviceName ?? audio.deviceName ?? audio.device_name
      }
    })
  }

  return normalized
}

const _metricsMapCache = new WeakMap()
const _textMapCache = new WeakMap()

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
            map[resource][m.metric] = m.value
          })
        }
      })
      result = map
    } else {
      const flatMap: any = {}
      metrics.forEach((m: any) => {
        if (!m || !m.metric) return
        flatMap[m.metric] = m.value
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
  casesLoading: any
  casesLoadError: any
  processTags: (tags: any) => any[]
}) {
  const { props, cases, casesLoading, casesLoadError, processTags } = deps

  function extractCasesFromReportData(reportData: any) {
    // 优先级1: 使用 test_reports_cases 字段（新格式）
    if (reportData.testReportsCases && Array.isArray(reportData.testReportsCases) && reportData.testReportsCases.length > 0) {
      console.log('从 testReportsCases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.testReportsCases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级2: 使用 reportData.cases
    if (reportData.cases && Array.isArray(reportData.cases) && reportData.cases.length > 0) {
      console.log('从 reportData.cases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.cases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级3: 使用 summary.cases
    if (reportData.summary?.cases && Array.isArray(reportData.summary.cases) && reportData.summary.cases.length > 0) {
      console.log('从 summary.cases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.summary.cases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级4: 使用 detailedResults
    if (reportData.detailedResults && Array.isArray(reportData.detailedResults) && reportData.detailedResults.length > 0) {
      console.log('从 detailedResults 提取用例数据')
      const casesMap = new Map();

      reportData.detailedResults.forEach((result: any) => {
        const testCaseId = result.testCaseId ?? result.test_case_id ?? result.testCase?.id;
        const testCaseName = result.testCaseName ?? result.test_case_name ?? result.testCase?.name ?? '未知用例';

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
          const asrRef = result.asr?.referenceText ?? result.asr?.reference_text ?? ''
          const tranRef = result.translation?.referenceText ?? result.translation?.reference_text ?? ''

          caseItem = {
            id: testCaseId,
            name: testCaseName,
            category: result.testCaseGroup?.name ?? result.test_case_group?.name ?? result.testCaseType ?? result.test_case_type ?? '其他',
            description: result.description || '',
            tags: processTags(result.testCaseTags ?? result.test_case_tags ?? []),
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
          caseItem.asr.results[resourceKey] = {text: result.asr.resultText ?? result.asr.result_text ?? '', score: 0};
        }

        if (result.translation) {
          caseItem.translation.results[resourceKey] = {text: result.translation.resultText ?? result.translation.result_text ?? '', score: 0};
        }

        if (!caseItem.metrics[resourceKey]) {
          caseItem.metrics[resourceKey] = {};
        }

        const dimensionScores = result.dimensionScores ?? result.dimension_scores;
        if (Array.isArray(dimensionScores)) {
          dimensionScores.forEach((dim: any) => {
            const dimName = dim.dimensionName ?? dim.dimension_name;
            if (dimName) {
              caseItem.metrics[resourceKey][dimName] = dim.score;
            }
          });
        } else if (result.metrics) {
          Object.entries(result.metrics).forEach(([dimName, value]) => {
            caseItem.metrics[resourceKey][dimName] = value;
          });
        }

        const createdAt = result.createdAt ?? result.created_at ?? 0;
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

        const algoResults = c.algorithmResults || c.algorithm_results || c.algorithmResults || []
        const refParams = c.referenceParams || c.reference_params || c.referenceParams || {}

        return {
          ...c,
          metrics: metricsMap,
          asr: c.asr ? { ...c.asr, results: asrMap } : c.asr,
          translation: c.translation ? { ...c.translation, results: tranMap } : c.translation,
          algorithm_results: algoResults,
          algorithmType: c.algorithmType || c.algorithm_type || '',
          reference_params: refParams,
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

  async function loadCasesFromApi(reportId: any) {
    casesLoading.value = true
    casesLoadError.value = ''
    try {
      const perPage = 200
      let page = 1
      let pages = 1
      const allItems: any[] = []
      while (page <= pages) {
        const data = await reportsApi.searchCases(reportId, { page, per_page: perPage })
        const items = data?.items || []
        pages = data?.pages || 1
        allItems.push(...items)
        page += 1
        if (allItems.length >= 5000) break
      }
      cases.value = normalizeCasesForUi(allItems)
    } catch (e: any) {
      console.error('加载报告用例失败:', e)
      casesLoadError.value = e?.message || '加载用例失败'
    } finally {
      casesLoading.value = false
    }
  }

  return { extractCasesFromReportData, normalizeCasesForUi, loadCasesFromApi }
}
