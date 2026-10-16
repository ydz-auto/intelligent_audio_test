/**
 * 全局算法 → 报告列表 algorithm_type 联动（规范 §2.2：全局算法切换器在导航栏右上角
 * 切换一次全局生效；报告列表请求自动附 algorithm_type。全局 store 的算法 id 与报告
 * 枚举名不同源（algorithm.py 算法定义 vs 报告快照字段），此处映射消费。
 * TODO(API 接线): 后端统一算法 id 后移除映射，直传 globalAlgorithmId）。
 */
import { getAlgorithmLabel } from '@/features/reports/constants'

const GLOBAL_ALGORITHM_TO_REPORT_TYPE: Record<string, string> = {
  'asr-v3': 'asr_streaming',
  'asr-stream': 'asr_streaming',
  'eval-ensemble': 'tts_eval',
}

/** 全局算法 id → 报告 algorithm_type（未知映射返回 undefined → 不带筛选） */
export function toReportAlgorithmType(globalAlgorithmId?: string): string | undefined {
  if (!globalAlgorithmId) return undefined
  return GLOBAL_ALGORITHM_TO_REPORT_TYPE[globalAlgorithmId]
}

const REPORT_TYPE_TO_GLOBAL_ALGORITHM: Record<string, string> = {
  asr_streaming: 'asr-v3',
  tts_eval: 'eval-ensemble',
}

/** 报告 algorithm_type → 全局算法 id（反向映射；URL 分享链首入写回 store 用） */
export function toGlobalAlgorithmId(reportAlgorithmType?: string): string | undefined {
  if (!reportAlgorithmType) return undefined
  return REPORT_TYPE_TO_GLOBAL_ALGORITHM[reportAlgorithmType]
}

/** 联动 chip 文案（算法类型中文标签；无映射回退全局算法名） */
export function getLinkedAlgorithmLabel(globalAlgorithmId?: string): string | undefined {
  const type = toReportAlgorithmType(globalAlgorithmId)
  if (!type) return undefined
  const label = getAlgorithmLabel(type)
  return label === '—' ? type : label
}
