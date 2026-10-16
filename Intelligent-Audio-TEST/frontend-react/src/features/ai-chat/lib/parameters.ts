/**
 * 生成参数纯函数（interfaces 层 lib/parameters；照 newAPI lib/parameters/playground-parameters 平移，
 * 六参数中文文案见 constants.AGENT_PARAMETER_CONTROLS）。
 */
import type { ChatParameterKey } from '@/domain/models/aiChat'
import { AGENT_PARAMETER_CONTROLS } from '@/features/ai-chat/constants'

export function normalizeParameterNumberValue(
  key: ChatParameterKey,
  value: string | number
): number | null {
  if (value === '') {
    return key === 'seed' ? null : 0
  }

  const control = AGENT_PARAMETER_CONTROLS.find((item) => item.key === key)
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value)

  if (!control || Number.isNaN(parsed)) {
    return key === 'seed' ? null : 0
  }

  const clamped = Math.min(control.max, Math.max(control.min, parsed))

  if (control.step >= 1) {
    return Math.trunc(clamped)
  }

  const precision = Math.max(0, String(control.step).split('.')[1]?.length ?? 0)
  return Number(clamped.toFixed(precision))
}

export function getParameterControlValueText(
  key: ChatParameterKey,
  value: number | null
): string {
  if (key === 'seed' && value === null) {
    return '未设置'
  }
  return String(value)
}
