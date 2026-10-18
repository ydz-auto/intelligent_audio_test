/**
 * 音频管理页常量（features/audio-import；16_设备域.md §9 中文文案源）。
 * 枚举/状态 + 展示文案直接存中文，组件直接渲染（AGENTS.md §3.1 全中文硬编码）。
 */

/** 格式 facet 选项（§5.3.2 FORMAT_OPTIONS 实测；后端 format 存小写，value 用小写匹配、label 大写展示） */
export const FORMAT_OPTIONS = [
  { value: 'mp3', label: 'MP3' },
  { value: 'wav', label: 'WAV' },
  { value: 'flac', label: 'FLAC' },
  { value: 'aac', label: 'AAC' },
  { value: 'm4a', label: 'M4A' },
] as const

/** 音频类型 facet 选项（§5.3.2 AUDIO_TYPE_OPTIONS 实测） */
export const AUDIO_TYPE_OPTIONS = [
  { value: 'dry', label: '干声' },
  { value: 'noise', label: '噪声' },
  { value: 'prompt', label: '提示词音频' },
  { value: 'mixed', label: '混合音频' },
] as const

/** 采样率 facet 选项（§5.3.2 SAMPLE_RATE_OPTIONS 实测） */
export const SAMPLE_RATE_OPTIONS = [
  { value: '8000', label: '8 kHz' },
  { value: '16000', label: '16 kHz' },
  { value: '24000', label: '24 kHz' },
  { value: '44100', label: '44.1 kHz' },
  { value: '48000', label: '48 kHz' },
  { value: '96000', label: '96 kHz' },
] as const

/** 时长 facet 选项（§5.3.2 DURATION_OPTIONS 实测） */
export const DURATION_OPTIONS = [
  { value: 'short', label: '短（≤30秒）' },
  { value: 'medium', label: '中（30秒-5分钟）' },
  { value: 'long', label: '长（>5分钟）' },
] as const

/** 标签 facet 模式（§5.3.2 多选 + OR/AND 切换） */
export const TAG_MODE_OPTIONS = [
  { value: 'or', label: '任一（OR）' },
  { value: 'and', label: '全部（AND）' },
] as const

/** 列表分页每页条数选项（§3.9 PAGE_SIZE_OPTIONS 语义） */
export const PAGE_SIZE_OPTIONS = [10, 20, 30, 40, 50, 100]

/** 列表默认每页条数（§5.2 validateSearch pageSize catch 20） */
export const DEFAULT_PAGE_SIZE = 20

/** 搜索防抖毫秒（§5.2 search debounce 500ms） */
export const AUDIO_SEARCH_DEBOUNCE_MS = 500

/** 视图切换哨兵值（§5.1 列表视图/文件夹视图） */
export const VIEW_ALL = 'all'
export const VIEW_LIST = 'list'
export const VIEW_FOLDER = 'folder'

/** 批量操作类型（§5.6 批量移动/复制/删除/重命名 + §6.25 批量修改属性） */
export const BATCH_OPERATION_OPTIONS = [
  { value: 'move', label: '批量移动' },
  { value: 'copy', label: '批量复制' },
  { value: 'rename', label: '批量重命名' },
  { value: 'modify-properties', label: '批量修改属性' },
] as const

/** 批量修改属性字段（§6.25：元数据/音频类型/SPL值等） */
export const MODIFY_PROPERTY_OPTIONS = [
  { value: 'metadata', label: '元数据' },
  { value: 'audio-type', label: '音频类型' },
  { value: 'spl', label: 'SPL 值' },
] as const

/** 目标文件夹选择（§6.25：选择目标文件夹） */
export const FOLDER_TARGET_OPTIONS = [
  { value: 'test_data/dry', label: 'test_data/dry' },
  { value: 'test_data/noise', label: 'test_data/noise' },
  { value: 'test_data/prompt', label: 'test_data/prompt' },
  { value: 'test_data/mixed', label: 'test_data/mixed' },
] as const

/** 格式转换目标格式（§6.15 输出白名单） */
export const CONVERT_TARGET_FORMATS = ['MP3', 'WAV', 'FLAC', 'AAC'] as const

/** 格式转换参数（§6.15：目标采样率/声道数/位深度/比特率） */
export const CONVERT_SAMPLE_RATE_OPTIONS = [
  { value: '16000', label: '16 kHz' },
  { value: '24000', label: '24 kHz' },
  { value: '44100', label: '44.1 kHz' },
  { value: '48000', label: '48 kHz' },
] as const

export const CONVERT_CHANNEL_OPTIONS = [
  { value: '1', label: '单声道' },
  { value: '2', label: '双声道' },
] as const

export const CONVERT_BIT_DEPTH_OPTIONS = [
  { value: '16', label: '16 bit' },
  { value: '24', label: '24 bit' },
  { value: '32', label: '32 bit' },
] as const

export const CONVERT_BITRATE_OPTIONS = [
  { value: '128', label: '128 kbps' },
  { value: '192', label: '192 kbps' },
  { value: '256', label: '256 kbps' },
  { value: '320', label: '320 kbps' },
] as const

/** 上传音频类型（§6.16 radio） */
export const UPLOAD_AUDIO_TYPE_OPTIONS = AUDIO_TYPE_OPTIONS

/** 测试类型（§6.16 checkbox 组） */
export const UPLOAD_TEST_TYPE_OPTIONS = [
  { value: 'e2e', label: 'E2E 测试' },
  { value: 'api', label: 'API 测试' },
] as const

/** 评估维度（§6.16 DimensionConfigPanel 勾选必填） */
export const UPLOAD_EVALUATION_DIMENSIONS = [
  { id: 1, name: '唤醒成功率', required: true },
  { id: 2, name: '误唤醒率', required: false },
  { id: 3, name: '识别准确率', required: true },
  { id: 4, name: '平均WER', required: false },
  { id: 5, name: '平均响应时间', required: false },
] as const
