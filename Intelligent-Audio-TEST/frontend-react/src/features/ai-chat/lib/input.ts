/**
 * 输入控制态纯函数（interfaces 层 lib/input；照 newAPI lib/input/input-control-utils 平移，
 * 去模型项——canSubmit 仅依赖文本非空，§3.5）。
 */

type InputControlStateParams = {
  disabled?: boolean
  isGenerating?: boolean
  hasStopHandler?: boolean
  text: string
}

export function getInputControlState({
  disabled,
  isGenerating = false,
  hasStopHandler = false,
  text,
}: InputControlStateParams): {
  canSubmit: boolean
  shouldShowStop: boolean
} {
  const canSubmit = !disabled && text.trim().length > 0
  const shouldShowStop = isGenerating && hasStopHandler
  return { canSubmit, shouldShowStop }
}

/** 提交文本清洗：空白折叠 + 首尾去空（照 getSubmittableInputText 语义） */
export function getSubmittableInputText(
  text: string,
  disabled?: boolean
): string {
  if (disabled) return ''
  const trimmed = text.trim().replace(/\s+/g, ' ')
  return trimmed.length > 0 ? trimmed : ''
}
