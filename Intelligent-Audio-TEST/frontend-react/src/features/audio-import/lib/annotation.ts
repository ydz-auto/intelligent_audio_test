/**
 * 标注文件解析（V9.7.10 audioUtils.ts parseAudioTxtFile / parseAnnotationFormat 平移；
 * 音频管理各模态窗共用：批量更新标注、文件夹导入、上传音频）。
 * 标注协议（与 V9.7.31 后端 BatchUpdateAnnotationsRequest / merge 载荷 annotations 一致）：
 *   { format, code, data: { segments, ...extra }, source_language, target_language }
 * 四形态 JSON 均能解析出正确 segments：{segments:[...]} / {annotations:[...]} / 裸数组 / JSONL；
 * rttm/stm 按行段解析而非存原文。
 */

export interface AnnotationItem {
  format: string
  code: string
  data: Record<string, unknown>
  source_language: string
  target_language: string
}

/** txt 解析结果（parseAudioTxtFile 平移：首行 ASR + 其余行翻译语向） */
export interface ParsedTxt {
  asrText: string
  translations: Array<{ text: string; direction: string }>
}

export function parseAudioTxt(content: string): ParsedTxt {
  const result: ParsedTxt = { asrText: '', translations: [] }
  if (!content) return result
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
  if (lines.length === 0) return result

  result.asrText = lines[0]

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i]
    let parts = line.split('\t').map((p) => p.trim())
    if (parts.length < 2) {
      const lastSpaceIndex = line.lastIndexOf(' ')
      if (lastSpaceIndex !== -1) {
        const text = line.substring(0, lastSpaceIndex).trim()
        const direction = line.substring(lastSpaceIndex + 1).trim()
        parts = [text, direction]
      }
    }
    if (parts.length >= 2) {
      const [text, direction] = parts
      if (text && direction) {
        const normalizedDirection = direction
          .replace(/_/g, '-')
          .replace(/\//g, '-')
          .replace(/2/g, '-')
          .toLowerCase()
        result.translations.push({ text, direction: normalizedDirection })
      }
    }
  }
  return result
}

/** 已知的顶层字段名，不属于此集合的字段会被收入 extra_fields */
const KNOWN_TOP_KEYS = new Set([
  'name',
  'code',
  'type',
  'source_language',
  'target_language',
  'text',
  'txt',
  'annotations',
  'timestamps',
  'timestamps_global',
])
/** 已知的 txt/segment 字段名 */
const KNOWN_SEG_KEYS = new Set(['speaker', 'start', 'end', 'text', 'confidence'])
/** 已知的 annotation 子字段名 */
const KNOWN_ANN_KEYS = new Set([
  'name',
  'code',
  'type',
  'source_language',
  'target_language',
  'text',
  'txt',
])

export interface ParsedAnnotationSegment {
  speaker: string
  start: number
  end: number
  text: string
  confidence: number
  [key: string]: unknown
}

export interface ParsedAnnotationSub {
  name: string
  code: string
  type: string
  source_language: string
  target_language: string
  segments: ParsedAnnotationSegment[]
  extra_fields: Record<string, unknown>
}

export interface ParsedAnnotation {
  format: string
  name: string
  code: string
  type: string
  source_language: string
  target_language: string
  segments: ParsedAnnotationSegment[]
  timestamps: number[][]
  timestamps_global: number[][]
  extra_fields: Record<string, unknown>
  annotations: ParsedAnnotationSub[]
}

/** 归一化一段（V9.7.10 KNOWN_SEG_KEYS 过滤：未知字段平铺进 segment） */
function normalizeSegment(item: Record<string, unknown>): ParsedAnnotationSegment {
  const segExtra: Record<string, unknown> = {}
  for (const k of Object.keys(item)) {
    if (!KNOWN_SEG_KEYS.has(k)) segExtra[k] = item[k]
  }
  return {
    speaker: String(item.speaker ?? ''),
    start: Number.parseFloat(String(item.start ?? '0')) || 0,
    end: Number.parseFloat(String(item.end ?? '0')) || 0,
    text: String(item.text ?? ''),
    confidence: Number.parseFloat(String(item.confidence ?? '1')) || 1,
    ...segExtra,
  }
}

/**
 * 解析标注文件内容（parseAnnotationFormat 平移）。
 * json/jsonl 支持 {segments:[...]} / {annotations:[...]} / {txt:[...]} / 裸数组 / 平铺对象；
 * rttm/stm 按行段解析。
 */
export function parseAnnotationFormat(content: string, format: string): ParsedAnnotation {
  const result: ParsedAnnotation = {
    format,
    name: '',
    code: '',
    type: '',
    source_language: '',
    target_language: '',
    segments: [],
    timestamps: [],
    timestamps_global: [],
    extra_fields: {},
    annotations: [],
  }

  const formatLower = format.toLowerCase()

  if (formatLower === 'json' || formatLower === 'jsonl') {
    try {
      let data: Record<string, unknown>
      if (formatLower === 'jsonl') {
        const lines = content.trim().split('\n').filter((line) => line.trim())
        const segments: ParsedAnnotationSegment[] = []
        for (const line of lines) {
          try {
            const obj = JSON.parse(line)
            if (obj && typeof obj === 'object') segments.push(normalizeSegment(obj as Record<string, unknown>))
          } catch {
            continue
          }
        }
        data = { txt: segments }
      } else {
        const parsed = JSON.parse(content)
        data = (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : { txt: parsed }
      }

      if (data.code) result.code = String(data.code)
      if (data.source_language) result.source_language = String(data.source_language)
      if (data.target_language) result.target_language = String(data.target_language)

      if (Array.isArray(data.txt) && (data.txt as unknown[]).length > 0) {
        // {txt: [...]} 分支：多段标注
        const txtList = data.txt as unknown[]
        for (const item of txtList) {
          if (item && typeof item === 'object') {
            result.segments.push(normalizeSegment(item as Record<string, unknown>))
          }
        }
        delete data.txt
        data.segments = result.segments as unknown as Record<string, unknown>
      } else if (Array.isArray(data.segments)) {
        // {segments:[...]} 分支：标准形态，逐段归一化
        const segments = data.segments as unknown[]
        for (const item of segments) {
          if (item && typeof item === 'object') {
            result.segments.push(normalizeSegment(item as Record<string, unknown>))
          }
        }
      } else if (!Array.isArray(data.annotations) || data.annotations.length === 0) {
        // 平铺 JSON 分支：{query, text, correctAnswer, ...}（无 segments/txt/annotations 时）→ 包装成单段
        const segExtra: Record<string, unknown> = {}
        for (const k of Object.keys(data)) {
          if (!KNOWN_SEG_KEYS.has(k) && !KNOWN_TOP_KEYS.has(k)) {
            segExtra[k] = data[k]
          }
        }
        result.segments.push({
          speaker: '',
          start: 0,
          end: 0,
          text: String(data.text ?? ''),
          confidence: 1,
          ...segExtra,
        })
        for (const k of Object.keys(data)) {
          if (!KNOWN_TOP_KEYS.has(k) && k !== 'segments') {
            delete data[k]
          }
        }
        data.segments = result.segments as unknown as Record<string, unknown>
      }

      if (Array.isArray(data.annotations)) {
        for (const ann of data.annotations as unknown[]) {
          if (!ann || typeof ann !== 'object') continue
          const annObj = ann as Record<string, unknown>
          const annSegments: ParsedAnnotationSegment[] = []
          if (Array.isArray(annObj.segments)) {
            // {annotations:[{code, segments:[...]}]} 形态：逐段归一化
            for (const item of annObj.segments as unknown[]) {
              if (item && typeof item === 'object') {
                annSegments.push(normalizeSegment(item as Record<string, unknown>))
              }
            }
          } else if (typeof annObj.text === 'string') {
            annSegments.push({
              speaker: '',
              start: 0,
              end: 0,
              text: annObj.text,
              confidence: 1,
            })
          } else if (Array.isArray(annObj.txt)) {
            for (const item of annObj.txt as unknown[]) {
              if (item && typeof item === 'object') {
                const obj = item as Record<string, unknown>
                if (obj.speaker || obj.text || obj.start !== undefined) {
                  annSegments.push(normalizeSegment(obj))
                }
              }
            }
          }
          if (annSegments.length > 0) {
            const annExtra: Record<string, unknown> = {}
            for (const k of Object.keys(annObj)) {
              if (!KNOWN_ANN_KEYS.has(k)) annExtra[k] = annObj[k]
            }
            result.annotations.push({
              name: '',
              code: String(annObj.code ?? 'asr'),
              type: '',
              source_language: String(annObj.source_language ?? ''),
              target_language: String(annObj.target_language ?? ''),
              segments: annSegments,
              extra_fields: annExtra,
            })
          }
        }
      }

      if (Array.isArray(data.timestamps)) result.timestamps = data.timestamps as number[][]
      if (Array.isArray(data.timestamps_global)) result.timestamps_global = data.timestamps_global as number[][]

      for (const k of Object.keys(data)) {
        if (!KNOWN_TOP_KEYS.has(k)) result.extra_fields[k] = data[k]
      }
    } catch {
      // JSON 解析失败返回空 segments（与 V9.7.10 一致，不抛错）
    }
  } else if (formatLower === 'rttm' || formatLower === 'stm') {
    const lines = content.trim().split('\n')
    for (const line of lines) {
      const parts = line.trim().split(/\s+/)
      if (formatLower === 'rttm' && parts[0] === 'SPEAKER' && parts.length >= 8) {
        const start = Number.parseFloat(parts[3]) || 0
        result.segments.push({
          speaker: parts[7] || '',
          start,
          end: start + (Number.parseFloat(parts[4]) || 0),
          text: '',
          confidence: 1,
        })
      } else if (formatLower === 'stm' && parts.length >= 6) {
        result.segments.push({
          speaker: parts[1] || '',
          start: Number.parseFloat(parts[2]) || 0,
          end: Number.parseFloat(parts[3]) || 0,
          text: parts.slice(5).join(' ') || '',
          confidence: 1,
        })
      }
    }
    result.name = 'diarization'
    result.code = 'diarization'
    result.type = 'diarization'
  }

  return result
}

/** 根据标注文件名推断标注代码（determineAnnotationName 平移） */
export function determineAnnotationName(fileName: string, format: string): string {
  const lowerName = fileName.toLowerCase()
  if (lowerName.includes('asr') || lowerName.includes('result')) return 'asr'
  if (lowerName.includes('trans') || lowerName.includes('翻译')) return 'translation'
  if (lowerName.includes('ref') || lowerName.includes('reference')) return 'reference'
  if (lowerName.includes('diar') || lowerName.includes('speaker')) return 'diarization'
  if (format === 'rttm' || format === 'stm') return 'diarization'
  return 'reference'
}

/**
 * 解析单个标注文件 → 标注数组（parseAnnotationContent 平移）。
 * txt：首行 ASR + 翻译语向；json/jsonl/rttm/stm：按 parseAnnotationFormat 段级解析。
 * fallbackCode 优先于 JSON 内 code / 文件名推断。
 */
export function parseAnnotationFile(
  fileName: string,
  content: string,
  fallbackCode?: string
): AnnotationItem[] {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? ''
  const trimmed = content.trim()
  if (!trimmed) return []

  if (ext === 'txt') {
    const parsed = parseAudioTxt(content)
    const annotations: AnnotationItem[] = []
    if (parsed.asrText) {
      annotations.push({
        format: 'text',
        code: 'asr',
        data: { text: parsed.asrText },
        source_language: '',
        target_language: '',
      })
    }
    for (const trans of parsed.translations) {
      const [source = '', target = ''] = trans.direction.split('-')
      annotations.push({
        format: 'text',
        code: 'translation',
        data: { text: trans.text },
        source_language: source,
        target_language: target,
      })
    }
    return annotations
  }

  let format = 'json'
  if (ext === 'rttm') format = 'rttm'
  else if (ext === 'stm') format = 'stm'
  else if (ext === 'jsonl') format = 'jsonl'

  const parsed = parseAnnotationFormat(trimmed, format)
  const fallback = fallbackCode || parsed.code || determineAnnotationName(fileName, format)
  const annotations: AnnotationItem[] = []

  if (parsed.annotations.length > 0) {
    for (const ann of parsed.annotations) {
      annotations.push({
        format: parsed.format,
        code: fallbackCode || ann.code || fallback,
        data: { segments: ann.segments, ...ann.extra_fields },
        source_language: ann.source_language || parsed.source_language || '',
        target_language: ann.target_language || parsed.target_language || '',
      })
    }
  } else if (parsed.segments.length > 0) {
    annotations.push({
      format: parsed.format,
      code: fallback,
      data: { segments: parsed.segments, ...parsed.extra_fields },
      source_language: parsed.source_language || '',
      target_language: parsed.target_language || '',
    })
  }

  return annotations
}

/** 标注/txt 文件扩展名（各模态窗 accept 与匹配共用） */
export const ANNOTATION_FILE_EXTS = ['.json', '.jsonl', '.rttm', '.stm', '.txt']

/** 是否标注/txt 文件（按扩展名） */
export function isAnnotationFile(name: string): boolean {
  const lower = name.toLowerCase()
  return ANNOTATION_FILE_EXTS.some((e) => lower.endsWith(e))
}

/** 标注 ↔ 音频匹配键（相对路径去扩展名 + 叶文件名，与 parseAnnotationsForAudios 同口径） */
function matchKeys(file: File): { baseKey: string; leafKey: string } {
  const rel = file.webkitRelativePath || file.name
  const baseKey = rel.replace(/\.[^.]+$/, '').toLowerCase()
  return { baseKey, leafKey: baseKey.split('/').pop() ?? '' }
}

/**
 * 找出没有命中任何音频的标注/txt 文件（INT-2192）。
 * 上传前对这类文件逐条提示「未匹配到同名音频文件，已忽略」——此前它们被静默丢弃：
 * 统计里计入「文本文件」，上传回执却只有音频数，既不报错也不说明。
 */
export function findUnmatchedAnnotationFiles(allFiles: File[], audioFiles: File[]): File[] {
  const baseKeys = new Set<string>()
  const leafKeys = new Set<string>()
  for (const audioFile of audioFiles) {
    const { baseKey, leafKey } = matchKeys(audioFile)
    baseKeys.add(baseKey)
    leafKeys.add(leafKey)
  }
  return allFiles
    .filter((f) => isAnnotationFile(f.name))
    .filter((annotationFile) => {
      const { baseKey, leafKey } = matchKeys(annotationFile)
      return !baseKeys.has(baseKey) && !leafKeys.has(leafKey)
    })
}

/**
 * 从选中文件集中解析标注/txt 文件并按文件名（baseKey 优先、叶文件名回退）匹配音频，
 * 返回与 audioFiles 平行的每音频标注数组。供文件夹导入 / 上传弹窗复用。
 */
export async function parseAnnotationsForAudios(
  allFiles: File[],
  audioFiles: File[],
  fallbackCode?: string
): Promise<AnnotationItem[][]> {
  const annotationFiles = allFiles.filter((f) => isAnnotationFile(f.name))
  if (annotationFiles.length === 0) return audioFiles.map(() => [])

  const byBaseKey = new Map<string, AnnotationItem[]>()
  const byLeafName = new Map<string, AnnotationItem[]>()

  const readText = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result ?? ''))
      reader.onerror = () => reject(new Error(`读取文件失败: ${file.name}`))
      reader.readAsText(file)
    })

  for (const annFile of annotationFiles) {
    try {
      const content = await readText(annFile)
      const annotations = parseAnnotationFile(annFile.name, content, fallbackCode)
      const rel = annFile.webkitRelativePath || annFile.name
      const baseKey = rel.replace(/\.[^.]+$/, '').toLowerCase()
      const leafName = baseKey.split('/').pop() ?? ''
      if (annotations.length > 0) {
        byBaseKey.set(baseKey, annotations)
        byLeafName.set(leafName, annotations)
      }
    } catch {
      // 单个标注文件解析失败跳过，其余照常
    }
  }

  return audioFiles.map((audioFile) => {
    const rel = audioFile.webkitRelativePath || audioFile.name
    const baseKey = rel.replace(/\.[^.]+$/, '').toLowerCase()
    const leafName = baseKey.split('/').pop() ?? ''
    const byLeaf = byBaseKey.get(baseKey)
    if (byLeaf) return byLeaf
    // 叶文件名回退匹配（同一 basename 的标注文件）
    for (const [mapKey, mapVal] of byLeafName) {
      if (mapKey.split('/').pop() === leafName) return mapVal
    }
    return []
  })
}
