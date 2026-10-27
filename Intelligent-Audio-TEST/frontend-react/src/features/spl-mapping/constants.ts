/**
 * 声压级映射管理页常量（features/spl-mapping；16_设备域.md §9 中文文案源）。
 * 枚举/状态 + 展示文案直接存中文，组件直接渲染（AGENTS.md §3.1 全中文硬编码）。
 */

/** 口径页签（§4.1：设备 SPL（E2E）｜API/Realtime RMS-SPL） */
export const DOMAIN_TABS = [
  { value: 'device', label: '设备 SPL（E2E）' },
  { value: 'digital', label: 'API/Realtime RMS-SPL' },
] as const

/** 校准状态 facet 选项（§4.1.1：全部/已校准/未校准，singleSelect） */
export const CALIBRATION_STATUS_OPTIONS = [
  { value: 'calibrated', label: '已校准' },
  { value: 'uncalibrated', label: '未校准' },
] as const

/** 播放设备类型（device_type dry/noise → 干声/噪声，§4.2 徽章） */
export const DEVICE_TYPE_OPTIONS = [
  { value: 'dry', label: '干声' },
  { value: 'noise', label: '噪声' },
] as const

/** 数字域协议（§4.3 协议徽章：websocket→WebSocket/HTTP） */
export const DIGITAL_PROTOCOL_OPTIONS = [
  { value: 'websocket', label: 'WebSocket' },
  { value: 'http', label: 'HTTP' },
] as const

/** 列表分页每页条数选项（§3.9 PAGE_SIZE_OPTIONS 语义） */
export const PAGE_SIZE_OPTIONS = [10, 20, 30, 40, 50, 100]

/** 列表默认每页条数（§4.1 validateSearch pageSize catch 20） */
export const DEFAULT_PAGE_SIZE = 20

/** 搜索防抖毫秒（§4.1.1 search debounce 500ms） */
export const SPL_SEARCH_DEBOUNCE_MS = 500

/** 数字域校准：目标声压级范围（§6.10 0~120 step 0.5） */
export const CALIBRATION_TARGET_SPL_MIN = 0
export const CALIBRATION_TARGET_SPL_MAX = 120

/** 数字域校准：实测 RMS 范围（§6.10 -120~0 dBFS；INT-2081 起为必填主输入） */
export const CALIBRATION_RMS_MIN = -120
export const CALIBRATION_RMS_MAX = 0

/** 参考基准默认值（§6.12：参考声压级 30-120 默认 65 + 参考线性增益正数默认 1.0） */
export const DEFAULT_REFERENCE_SPL = 65
export const DEFAULT_REFERENCE_GAIN_LINEAR = 1.0
export const DEFAULT_MIN_GAIN_LINEAR = 0.001
export const DEFAULT_MAX_GAIN_LINEAR = 10.0

/** 三口径对称提示文案（§4.4，现状 SPLMapping.vue:399 文案保留） */
export const SPL_SYMMETRY_ALERT_TEXT =
  '三口径对称：E2E 物理映射挂播放设备（spl_mappings）；API/Realtime 数字 RMS 映射挂被测 API（api_rms_spl_mappings）；用例轮次级声压级独立配置——三者共同构成平台声压级标定体系。'

/** 数字域校准弹窗顶部说明（§6.10，INT-2081 口径：目标声压级↔实测 dBFS，逐字保留） */
export const DIGITAL_CALIBRATION_INFO_TEXT =
  '数字域校准（API/Realtime 口径）：为被测 API 配置「目标声压级↔实测 dBFS」点集，线性增益由 dBFS 与基础电平 -30 dBFS 推导，提交后全量替换既有校准点并置为已校准。与设备 SPL 校准（物理域）对称；未校准时按参考基准线性近似 gain = {refGain} × 10^((target - {refSpl}) / 20)。'

/** 数字域校准互斥提示（§6.10） */
export const DIGITAL_CALIBRATION_LOCK_TEXT =
  '同一 API 并发校准互斥（分布式锁），冲突时后端返回 409，请稍后重试。'
