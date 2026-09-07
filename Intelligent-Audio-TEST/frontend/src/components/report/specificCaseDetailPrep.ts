import { toMetricsMap, toTextMap } from './specificCaseDataHelpers'
import { inferParamType } from '@/domain'

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

  function getAlgorithmResults(caseItem: any) {
    const algoResults = caseItem.algorithmResults;

    if (Array.isArray(algoResults)) {
      return algoResults;
    }

    const result: any[] = [];
    const excludedKeys = new Set([
      'evaluationData', 'evalData', 'rawResponse', 'resultType',
      'errorMessage', 'status', 'duration', 'adjustedReferenceParams',
      'referenceParams', 'config'
    ]);

    if (algoResults && typeof algoResults === 'object') {
      for (const [resource, data] of Object.entries(algoResults)) {
        if (data && typeof data === 'object') {
          for (const [paramKey, paramValue] of Object.entries(data as any)) {
            if (paramValue && !excludedKeys.has(paramKey)) {
              result.push({
                device: resource,
                paramCode: paramKey,
                paramType: inferParamType(paramKey),
                label: paramKey,
                value: paramValue
              });
            }
          }
        }
      }
    }

    const directKeys = ['rttmRes', 'stmRes', 'rttmHyp', 'stmHyp'];
    for (const key of directKeys) {
      if (caseItem[key]) {
        result.push({
          device: 'default',
          paramCode: key,
          paramType: inferParamType(key),
          label: key,
          value: caseItem[key]
        });
      }
    }

    return result;
  }

  // 原按 reportData.taskType 过滤音频的逻辑已移除：Report domain 无 taskType 字段（adapter 不产出），该分支恒为 'all'（全量返回），属死代码
  function prepareAudioList(caseItem: any) {
    if (!caseItem.audioList || !Array.isArray(caseItem.audioList) || caseItem.audioList.length === 0) {
      return []
    }

    return caseItem.audioList
  }

  /**
   * 从 reportData.summary.fieldMappings 中按 algorithmType 获取 field_mapping 快照
   */
  function getFieldMapping(caseItem: any) {
    const algoType = caseItem.algorithmType || '';
    if (!algoType) return { result: [], reference: [] };
    const fieldMappings = props.reportData?.summary?.fieldMappings || {};
    return fieldMappings[algoType] || { result: [], reference: [] };
  }

  function prepareCaseItem(caseItem: any) {
    return {
      ...caseItem,
      _preparedComparisonData: prepareComparisonData(caseItem),
      _preparedAudioList: prepareAudioList(caseItem),
      _preparedReferenceAsr: caseItem.asr?.referenceText || '',
      _preparedReferenceTrans: caseItem.translation?.referenceText || '',
      _preparedAlgorithmResults: getAlgorithmResults(caseItem),
      _preparedReferenceParams: caseItem.referenceParams || {},
      _preparedAlgorithmType: caseItem.algorithmType || '',
      _preparedFieldMapping: getFieldMapping(caseItem)
    }
  }

  return { prepareComparisonData, getAlgorithmResults, prepareAudioList, prepareCaseItem, getFieldMapping }
}
