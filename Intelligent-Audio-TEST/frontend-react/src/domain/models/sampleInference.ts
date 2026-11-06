/**
 * 「贴一段样例 JSON → 自动生成我们的模板」的前端推断器（纯函数，无网络）。
 *
 * 覆盖两个入口：
 * - 请求模板：样例请求 JSON → `body_template`（音频 base64 等长串替换成占位符）；
 * - 响应解析：样例响应 JSON → `result_parser`（asr_text_path / trans_text_path /
 *   session_id_path）。
 *
 * 推断是**启发式**：只按字段名与路径深度挑最像的一个，结果一律回填到输入框让用户
 * 复核，不直接保存（避免"猜错还静默生效"）。
 */

export type SampleKind = 'request' | 'response'

export interface InferredField {
  /** 语义字段：asr_text / trans_text / session_id */
  code: string
  /** 响应/请求里的路径，形如 data.items[0].text */
  path: string
  /** 命中的原始键名（回显给用户看为什么这么猜） */
  key: string
}

export interface InferResult {
  /** 可直接写进 meta.result_parser 的对象 */
  parser: Record<string, string>
  /** 命中的字段（含未直接可用的，用于提示） */
  fields: InferredField[]
  /** 请求模板：替换占位符后的 JSON 文本 */
  bodyTemplate?: string
  /** 识别到的音频字段路径（请求模板用） */
  audioPath?: string
}

/** 语义 → 候选键名（按优先级；命中即取，后者只在前面没有时兜底） */
const KEY_CANDIDATES: Record<string, string[]> = {
  session_id: ['session_id', 'sessionId', 'sid', 'conversation_id'],
  asr_text: ['asr_text', 'asrText', 'asr_result', 'asr', 'transcript', 'text'],
  trans_text: [
    'trans_text',
    'transText',
    'translation',
    'translated_text',
    'translate_text',
    'target_text',
  ],
}

/** 音频载荷候选键（请求方向） */
const AUDIO_KEY_CANDIDATES = ['audio', 'audio_b64', 'audio_data', 'pcm', 'data']

const MAX_DEPTH = 6
const MAX_ARRAY_INDEX = 3

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function childPath(parent: string, key: string): string {
  return parent ? `${parent}.${key}` : key
}

function indexPath(parent: string, index: number): string {
  return `${parent}[${index}]`
}

/** 像 base64 音频的长串（>200 字符且只含 base64 字符） */
function looksLikeBase64Audio(value: unknown): boolean {
  if (typeof value !== 'string' || value.length < 200) return false
  return /^[A-Za-z0-9+/=\r\n]+$/.test(value)
}

interface WalkHit {
  code: string
  path: string
  key: string
  depth: number
}

/**
 * 深度优先遍历，给每个语义挑「路径最短、层级最浅」的候选。
 * 同一语义多个命中时优先层级浅的（报告里的字段一般都在外层）。
 */
function walk(
  value: unknown,
  path: string,
  depth: number,
  hits: Map<string, WalkHit>,
  audioHit: { path?: string }
): void {
  if (depth > MAX_DEPTH) return
  if (Array.isArray(value)) {
    value.slice(0, MAX_ARRAY_INDEX).forEach((item, index) => {
      walk(item, indexPath(path, index), depth + 1, hits, audioHit)
    })
    return
  }
  if (!isPlainObject(value)) return

  for (const [key, child] of Object.entries(value)) {
    const current = childPath(path, key)
    for (const [code, candidates] of Object.entries(KEY_CANDIDATES)) {
      if (!candidates.includes(key)) continue
      const previous = hits.get(code)
      if (previous && previous.depth <= depth) continue
      hits.set(code, { code, path: current, key, depth })
    }
    if (!audioHit.path && AUDIO_KEY_CANDIDATES.includes(key) && looksLikeBase64Audio(child)) {
      audioHit.path = current
    }
    walk(child, current, depth + 1, hits, audioHit)
  }
}

function parseSample(text: string): unknown {
  const trimmed = (text || '').trim()
  if (!trimmed) throw new Error('先粘贴一段 JSON')
  try {
    return JSON.parse(trimmed)
  } catch {
    throw new Error('不是合法 JSON，请检查引号/逗号')
  }
}

/** 响应样例 → result_parser 草稿（返回可直接回填的 JSON 文本 + 命中说明） */
export function inferResponseParser(text: string): {
  parserText: string
  fields: InferredField[]
} {
  const sample = parseSample(text)
  const hits = new Map<string, WalkHit>()
  const audioHit: { path?: string } = {}
  walk(sample, '', 0, hits, audioHit)

  const parser: Record<string, string> = {}
  for (const code of ['asr_text', 'trans_text', 'session_id']) {
    const hit = hits.get(code)
    if (hit) parser[`${code}_path`] = hit.path
  }
  if (Object.keys(parser).length === 0) {
    throw new Error('没识别出文本字段：样例里需要 asr/transcript/translation/text 这类键')
  }
  return {
    parserText: JSON.stringify(parser, null, 2),
    fields: Array.from(hits.values())
      .sort((a, b) => a.depth - b.depth)
      .map(({ code, path, key }) => ({ code, path, key })),
  }
}

/**
 * 请求样例 → body_template 草稿：整份 JSON 原样做模板，
 * 只把「看起来像 base64 音频」的长串替换成 `{{audio_b64}}` 占位符。
 */
export function inferBodyTemplate(text: string): { templateText: string; audioPath?: string } {
  const sample = parseSample(text)
  const hits = new Map<string, WalkHit>()
  const audioHit: { path?: string } = {}
  walk(sample, '', 0, hits, audioHit)

  const replaced = JSON.parse(JSON.stringify(sample), (key, value) =>
    looksLikeBase64Audio(value) && AUDIO_KEY_CANDIDATES.includes(key) ? '{{audio_b64}}' : value
  )
  return {
    templateText: JSON.stringify(replaced, null, 2),
    audioPath: audioHit.path,
  }
}
