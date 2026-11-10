/**
 * 「按 JSON 批量更新标注」的纯逻辑：
 * - 递归读取所选文件夹的 .json（含子目录；是否递归由弹窗开关控制）；
 * - 从 JSON 内的音频名称字段提取音频文件名；
 * - 用文件名建立音频库索引（全名优先、去扩展名兜底）；
 * - 标签来源三档组装（VEGA-64：JSON 顶层 tags / 路径目录段 / 两者都要）。
 *
 * 音频名称兼容 `audio` / `audio_name` / `audioName` / `audio_file` / `audioFile`，
 * 既支持顶层直出，也支持 `data`、`rounds[].segments[]`、`audios[]` 等常见嵌套结构。
 */

import {
  determineAnnotationName,
  parseAnnotationFile,
  type AnnotationItem,
} from '@/features/audio-import/lib/annotation'
import { parseTopLevelTags } from '@/features/audio-import/lib/case-rounds'
import type { AudioTagSource } from '@/infrastructure/api/audio-upload-api'

const AUDIO_NAME_KEYS = [
  'audio',
  'audio_name',
  'audioName',
  'audio_file',
  'audioFile',
  'audio_filename',
  'audioFilename',
  'audio_path',
  'audioPath',
] as const

const AUDIO_FILE_EXTS = ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg'] as const

export type NamedAudio = {
  id: number
  name: string
}

export type AnnotationJsonEntry = {
  audioName: string
  annotations: AnnotationItem[]
  /** 多轮 JSON 中该音频所属轮次；单音频 JSON 为空 */
  segmentLabel: string
  /**
   * JSON 顶层 tags（VEGA-64；宽容解析，畸形降级空数组）。同一 JSON 的所有条目
   * 共享同一数组引用（解析一次），供标签来源组装使用。
   */
  jsonTags: string[]
}

export function normalizeAudioName(value: string): string {
  const trimmed = value.trim().replace(/\\/g, '/')
  return trimmed.split('/').pop() ?? trimmed
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function directAudioName(value: unknown): string {
  const obj = asRecord(value)
  if (!obj) return ''
  for (const key of AUDIO_NAME_KEYS) {
    const raw = obj[key]
    if (typeof raw === 'string' && raw.trim()) return normalizeAudioName(raw)
  }
  return ''
}

function arrayAudioName(value: unknown): string {
  if (!Array.isArray(value)) return ''
  for (const item of value) {
    const name = directAudioName(item)
    if (name) return name
  }
  return ''
}

function looksLikeAudioFile(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const lower = value.trim().toLowerCase()
  return AUDIO_FILE_EXTS.some((ext) => lower.endsWith(ext))
}

/**
 * 提取 JSON 内的音频名称（返回叶文件名）。
 * 顺序：顶层直出 → data/annotation → rounds[].segments[] → audios[] / segments[] →
 * 其余嵌套字段兜底。
 */
export function extractAnnotationAudioName(raw: unknown): string {
  if (Array.isArray(raw)) return arrayAudioName(raw)

  const root = asRecord(raw)
  if (!root) return ''

  const direct = directAudioName(root)
  if (direct) return direct

  // 部分标注 JSON 把音频文件名放在顶层 name；仅当扩展名明确是音频时才采用，
  // 避免误把用例名/标注名当成音频。
  if (looksLikeAudioFile(root.name)) return normalizeAudioName(root.name)

  for (const wrapperKey of ['data', 'annotation', 'result']) {
    const wrapped = directAudioName(root[wrapperKey])
    if (wrapped) return wrapped
  }

  if (Array.isArray(root.rounds)) {
    for (const round of root.rounds) {
      const roundObj = asRecord(round)
      if (!roundObj) continue
      const name = arrayAudioName(roundObj.segments)
      if (name) return name
    }
  }

  for (const listKey of ['audios', 'segments', 'annotations']) {
    const name = arrayAudioName(root[listKey])
    if (name) return name
  }

  const queue: unknown[] = [root]
  while (queue.length > 0) {
    const current = queue.shift()
    if (Array.isArray(current)) {
      queue.push(...current)
      continue
    }
    const obj = asRecord(current)
    if (!obj) continue
    for (const [key, value] of Object.entries(obj)) {
      if (
        (AUDIO_NAME_KEYS as readonly string[]).includes(key) &&
        typeof value === 'string' &&
        value.trim()
      ) {
        return normalizeAudioName(value)
      }
      if (value != null && typeof value === 'object') queue.push(value)
    }
  }
  return ''
}

/** 所选文件夹第一层（根目录 → 文件）的 JSON；手动多选单文件也视为第一层。 */
export function isTopLevelJsonFile(relativePath: string): boolean {
  const parts = relativePath
    .replace(/\\/g, '/')
    .split('/')
    .filter((part) => part.length > 0)
  if (parts.length === 0 || parts.length > 2) return false
  return parts[parts.length - 1].toLowerCase().endsWith('.json')
}

/**
 * 目录段标签提取（VEGA-64）：与后端 merge_mixin._process_audio_tags 同规则——
 * 按 `/` 拆、去最后一段（文件名）、去空段、按序去重，含所选根目录名段。
 * 反斜杠按分隔符归一（与本文件 normalizeAudioName / isTopLevelJsonFile 口径一致）。
 */
export function pathDirectoryTags(relativePath: string): string[] {
  const parts = relativePath.replace(/\\/g, '/').split('/')
  const directories = parts.slice(0, -1)
  const tags: string[] = []
  for (const part of directories) {
    if (part && !tags.includes(part)) tags.push(part)
  }
  return tags
}

/**
 * 标签来源三档组装（VEGA-64，对齐导入 resolveSubmitTags 的口径，但本窗无手填标签）：
 * both = JSON tags 与路径目录段并集去重（JSON 在前、路径段在后）；json = 仅 JSON tags；
 * path = 仅路径目录段。返回的是提交给 items[].tags 的最终列表。
 */
export function resolveAnnotationTags(
  jsonTags: string[],
  relativePath: string,
  tagSource: AudioTagSource
): string[] {
  if (tagSource === 'json') return [...jsonTags]
  if (tagSource === 'path') return pathDirectoryTags(relativePath)
  return Array.from(new Set([...jsonTags, ...pathDirectoryTags(relativePath)]))
}

function baseNameWithoutExt(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

function addLookupKey(
  lookup: Map<string, NamedAudio>,
  key: string,
  audio: NamedAudio
): void {
  const normalized = key.trim().toLowerCase()
  if (normalized && !lookup.has(normalized)) lookup.set(normalized, audio)
}

/** 音频库索引：全名、叶文件名、去扩展名三者均映射到音频。 */
export function buildAudioNameLookup(
  audios: NamedAudio[]
): Map<string, NamedAudio> {
  const lookup = new Map<string, NamedAudio>()
  for (const audio of audios) {
    const leaf = normalizeAudioName(audio.name)
    addLookupKey(lookup, leaf, audio)
    addLookupKey(lookup, baseNameWithoutExt(leaf), audio)
  }
  return lookup
}

/** 按 JSON 内音频名称查音频；全名优先，去扩展名兜底。 */
export function findAudioByName(
  rawName: string,
  lookup: Map<string, NamedAudio>
): NamedAudio | undefined {
  const leaf = normalizeAudioName(rawName)
  if (!leaf) return undefined
  return (
    lookup.get(leaf.toLowerCase()) ??
    lookup.get(baseNameWithoutExt(leaf).toLowerCase())
  )
}

function segmentAnnotation(
  fileName: string,
  segment: Record<string, unknown>
): AnnotationItem {
  const cleaned: Record<string, unknown> = { ...segment }
  for (const key of AUDIO_NAME_KEYS) delete cleaned[key]
  return {
    format: 'json',
    code: determineAnnotationName(fileName, 'json'),
    data: { segments: [cleaned] },
    source_language: String(segment.source_language ?? ''),
    target_language: String(segment.target_language ?? ''),
  }
}

/**
 * 把一个 JSON 拆成「音频 + 标注」条目。
 * - 多轮用例 JSON：rounds[].segments[] 每个 segment 对应一个音频，各自生成一条标注；
 * - 单音频标注 JSON：沿用 parseAnnotationFile 的既有解析。
 * 顶层 tags 经 parseTopLevelTags 解析一次，同一 JSON 的所有条目共享（VEGA-64）。
 */
export function parseAnnotationJsonEntries(
  fileName: string,
  raw: unknown
): AnnotationJsonEntry[] {
  const root = asRecord(raw)
  if (!root) return []

  const jsonTags = parseTopLevelTags(root.tags)

  if (Array.isArray(root.rounds)) {
    const entries: AnnotationJsonEntry[] = []
    root.rounds.forEach((round, roundIndex) => {
      const roundObj = asRecord(round)
      if (!roundObj || !Array.isArray(roundObj.segments)) return
      roundObj.segments.forEach((segment) => {
        const segmentObj = asRecord(segment)
        if (!segmentObj) return
        const audioName = directAudioName(segmentObj)
        if (!audioName) return
        entries.push({
          audioName,
          annotations: [segmentAnnotation(fileName, segmentObj)],
          segmentLabel: `第 ${roundIndex + 1} 轮`,
          jsonTags,
        })
      })
    })
    if (entries.length > 0) return entries
  }

  const audioName = extractAnnotationAudioName(raw)
  return [
    {
      audioName,
      annotations: parseAnnotationFile(fileName, JSON.stringify(raw)),
      segmentLabel: '',
      jsonTags,
    },
  ]
}
