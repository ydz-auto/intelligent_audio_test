/**
 * useE2eView —— 常量（constants）
 *
 * 设备列表展示字段、voice_llm 算法标识与提示文案、默认并发任务数等页面级常量。
 */

/** 设备列表展示字段 */
export const DEVICE_DISPLAY_FIELDS = [
  { label: '设备名称', key: 'name' },
  { label: '型号', key: 'model' },
  { label: '序列号', key: 'serialNumber' },
  { label: '状态', key: 'status', isStatus: true }
]

/** voice_llm 算法类型标识（后端算法类型值） */
export const VOICE_LLM_ALGORITHM_TYPE = 'voice_llm'

/** voice_llm 设备能力提示文案 */
export const VOICE_LLM_DEVICE_HINT = 'voice_llm 测试可能需要设备支持：音量控制、导轨控制、打断检测。请确认设备能力后再选择。'

/** voice_llm 并发数建议提示文案 */
export const VOICE_LLM_CONCURRENCY_HINT = 'voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。'

/** 默认并发任务数 */
export const DEFAULT_CONCURRENT_TASKS = 4