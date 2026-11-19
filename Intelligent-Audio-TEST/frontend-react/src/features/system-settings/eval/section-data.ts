/**
 * 评估服务域分区常量（interfaces 层）：
 * LLM 裁判 / ASR 识别 / 第三方评估中转；域门槛 option:write（管理员口径）。
 */
export const EVAL_SECTIONS = [
  { id: 'llm', title: 'LLM 裁判' },
  { id: 'asr', title: 'ASR 识别' },
  { id: 'relay', title: '第三方评估' },
] as const

export type EvalSectionId = (typeof EVAL_SECTIONS)[number]['id']

export const EVAL_SECTION_IDS = EVAL_SECTIONS.map((s) => s.id) as [
  EvalSectionId,
  ...EvalSectionId[],
]

export const EVAL_DEFAULT_SECTION = 'llm'
