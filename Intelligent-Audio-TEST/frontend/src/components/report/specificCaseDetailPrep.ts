import { toMetricsMap, toTextMap } from './specificCaseDataHelpers'

export function createCaseDetailPrep(deps: {
  props: any
  allDevices: any
}) {
  const { props, allDevices } = deps

  function prepareComparisonData(caseItem: any) {
    const data: any = {}
    const metricsMap = toMetricsMap(caseItem)
    const asrMap = toTextMap(caseItem.asr)
    const tranMap = toTextMap(caseItem.translation)

    const isFlatFormat = !Object.keys(metricsMap).some(k => allDevices.value.includes(k))

    allDevices.value.forEach((device: string) => {
      if (isFlatFormat) {
        data[device] = {
          metrics: metricsMap,
          asr: { text: asrMap?.[device]?.text || '-' },
          trans: { text: tranMap?.[device]?.text || '-' }
        }
      } else {
        data[device] = {
          metrics: metricsMap[device] || {},
          asr: { text: asrMap?.[device]?.text || '-' },
          trans: { text: tranMap?.[device]?.text || '-' }
        }
      }
    })
    return data
  }

  function _inferParamType(paramKey: string) {
    const lower = paramKey.toLowerCase();
    if (lower.includes('rttm')) return 'rttm';
    if (lower.includes('stm')) return 'stm';
    if (lower.includes('audio')) return 'audio';
    return 'text';
  }

  function getAlgorithmResults(caseItem: any) {
    const algoResults = caseItem.algorithm_results;

    if (Array.isArray(algoResults)) {
      return algoResults;
    }

    const result: any[] = [];
    const excludedKeys = new Set([
      'evaluation_data', 'eval_data', 'raw_response', 'result_type',
      'error_message', 'status', 'duration', 'adjusted_reference_params',
      'reference_params', 'config'
    ]);

    if (algoResults && typeof algoResults === 'object') {
      for (const [resource, data] of Object.entries(algoResults)) {
        if (data && typeof data === 'object') {
          for (const [paramKey, paramValue] of Object.entries(data as any)) {
            if (paramValue && !excludedKeys.has(paramKey)) {
              result.push({
                device: resource,
                param_code: paramKey,
                param_type: _inferParamType(paramKey),
                label: paramKey,
                value: paramValue
              });
            }
          }
        }
      }
    }

    const directKeys = ['rttmRes', 'stmRes', 'rttm_res', 'stm_res', 'rttm_hyp', 'stm_hyp', 'rttmHyp', 'stmHyp'];
    for (const key of directKeys) {
      if (caseItem[key]) {
        result.push({
          device: 'default',
          param_code: key,
          param_type: _inferParamType(key),
          label: key,
          value: caseItem[key]
        });
      }
    }

    return result;
  }

  function prepareAudioList(caseItem: any) {
    const taskType = props.reportData?.task_type || 'all'

    if (!caseItem.audioList || !Array.isArray(caseItem.audioList) || caseItem.audioList.length === 0) {
      return []
    }

    return caseItem.audioList.filter((audio: any) => {
      if (taskType === 'api') {
        return audio.type === 'api'
      } else if (taskType === 'e2e') {
        return audio.type === 'e2e' || audio.type === 'noise'
      } else {
        return true
      }
    })
  }

  /**
   * 从 reportData.summary.fieldMappings 中按 algorithmType 获取 field_mapping 快照
   */
  function getFieldMapping(caseItem: any) {
    const algoType = caseItem.algorithm_type || '';
    if (!algoType) return { result: [], reference: [] };
    const fieldMappings = props.reportData?.summary?.field_mappings || {};
    return fieldMappings[algoType] || { result: [], reference: [] };
  }

  function prepareCaseItem(caseItem: any) {
    return {
      ...caseItem,
      _preparedComparisonData: prepareComparisonData(caseItem),
      _preparedAudioList: prepareAudioList(caseItem),
      _preparedReferenceAsr: caseItem.asr?.reference_text || '',
      _preparedReferenceTrans: caseItem.translation?.reference_text || '',
      _preparedAlgorithmResults: getAlgorithmResults(caseItem),
      _preparedReferenceParams: caseItem.reference_params || {},
      _preparedAlgorithmType: caseItem.algorithm_type || '',
      _preparedFieldMapping: getFieldMapping(caseItem)
    }
  }

  return { prepareComparisonData, getAlgorithmResults, prepareAudioList, prepareCaseItem, getFieldMapping }
}
