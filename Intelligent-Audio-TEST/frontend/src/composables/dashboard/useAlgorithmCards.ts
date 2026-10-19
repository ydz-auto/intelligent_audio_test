// -*- coding: utf-8 -*-
/**
 * 工作台算法卡片网格数据（INT-736 / React 04_控制台 §3.4）
 *
 * - 数据源 = GET /algorithm/definitions（全量，含描述/参数摘要，不用 /options）；
 * - 按 display_order 排序；仅在线算法可点（离线卡置灰，对齐 options 仅在线语义）；
 * - 选中态读/写 useGlobalAlgorithmStore（与右上角切换器/报告展示页双向联动）；
 * - 无 algorithm:read（device_admin/guest）→ 只读降级条（网格不渲染）。
 */
import { ref, computed } from 'vue'
import { algorithmPort } from '../algorithm/algorithmPort'
import { useGlobalAlgorithmStore } from '../../store/globalAlgorithmStore'
import { toUserErrorMessage, toUserErrorDetail } from '../../utils/errorMessage'
import type { AlgorithmDefinition } from '../../domain/model/algorithm'

export function useAlgorithmCards() {
  const definitions = ref<AlgorithmDefinition[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** 原始 RPC 异常详情（INT-899：详情仅进 Toast 折叠区，不渲染进页面） */
  const errorDetail = ref('')
  const store = useGlobalAlgorithmStore()

  async function load() {
    loading.value = true
    error.value = null
    errorDetail.value = ''
    try {
      const result = await algorithmPort.getDefinitions({})
      definitions.value = [...(result?.data ?? [])].sort(
        (a, b) => (a.displayOrder ?? 0) - (b.displayOrder ?? 0)
      )
    } catch (e: any) {
      // INT-899（INT-858 N1）：原始 gRPC 异常文本不直出——固定文案 + 原始详情进 Toast
      error.value = toUserErrorMessage(e, '算法服务暂不可用，请稍后重试')
      errorDetail.value = toUserErrorDetail(e)
    } finally {
      loading.value = false
    }
  }

  /** 当前选中算法类型（null = 全部算法） */
  const selectedType = computed(() => store.algorithmType)

  /** 点击卡片直选（null = 全部算法首卡） */
  function select(type: string | null) {
    store.setAlgorithm(type)
  }

  return { definitions, loading, error, errorDetail, selectedType, select, load }
}

/** 参数摘要文本：设备参数 n · API 参数 m · 用例参数 k（三项全 0/缺失时为空） */
export function getAlgorithmParamSummary(algo: AlgorithmDefinition): string {
  const device = algo.deviceParams?.length ?? algo.params?.length ?? 0
  const api = algo.apiParams?.length ?? 0
  const caseCount = algo.caseParams?.length ?? 0
  if (device === 0 && api === 0 && caseCount === 0) return ''
  return `设备参数 ${device} · API 参数 ${api} · 用例参数 ${caseCount}`
}
