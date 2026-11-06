/**
 * 音频管理页常量（features/audio-import；16_设备域.md §9 中文文案源）。
 * 枚举/状态 + 展示文案直接存中文，组件直接渲染（AGENTS.md §3.1 全中文硬编码）。
 */
import type { AudioTagSource } from '@/infrastructure/api/audio-upload-api'

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

/**
 * 可见性 facet 选项（数据可见性设计文档 §八「全部/共享/私有」筛选 chips）。
 * 「全部」= 不传服务端参数（null），由 SingleFacet 的「全部」文案表达。
 */
export const VISIBILITY_OPTIONS = [
  { value: 'shared', label: '共享' },
  { value: 'private', label: '私有' },
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

/** 默认声压级（§6.16 上传 / §6.14 试听共用；后端允许区间 30-120，沿用旧版默认 65 dB） */
export const DEFAULT_SPL = 65

/** 上传音频类型（§6.16 radio） */
export const UPLOAD_AUDIO_TYPE_OPTIONS = AUDIO_TYPE_OPTIONS

/** 用例分组方式（§6.16/§6.17 radio：根目录/文件夹名/自定义；V9.7.10 groupNameType 对位） */
export const CASE_GROUP_OPTIONS = [
  { value: 'root', label: '根目录' },
  { value: 'folder', label: '文件夹名' },
  { value: 'custom', label: '自定义' },
] as const

/**
 * 导入标签来源三档（INT-1979；上传窗与文件夹导入窗共用，默认「两者都要」）。
 * value 与 infrastructure 的 AudioTagSource 一一对应，desc 是弹窗内逐档说明文案。
 */
export const TAG_SOURCE_OPTIONS = [
  {
    value: 'both',
    label: '两者都要',
    desc: '手填标签 + JSON 顶层 tags 一并提交，并按文件夹路径解析标签（默认）',
  },
  {
    value: 'json',
    label: '仅 JSON tags',
    desc: '手填标签 + JSON 顶层 tags 一并提交，不做路径解析',
  },
  {
    value: 'path',
    label: '仅路径解析',
    desc: '只提交手填标签，JSON 顶层 tags 不并入，按文件夹路径解析标签',
  },
] as const

/** 标签来源默认档（= 现状口径：JSON tags + 路径解析都做；弹窗重开回到此值） */
export const DEFAULT_TAG_SOURCE: AudioTagSource = 'both'
