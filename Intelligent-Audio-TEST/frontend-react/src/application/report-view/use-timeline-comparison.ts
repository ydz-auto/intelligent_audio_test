/**
 * 时间轴对比（application 层，15_报告域.md §3.3.9 平移简化）。
 * parseTimelineData 支持数组/JSON/文本（parseRttmText/parseStmText）；说话人映射贪心
 * （computeOptimalSpeakerMapping 按重叠时间降序匹配，overlap ±0.5s 容差）。
 * 可视稿：以 mock segments 演示渲染；真实接入时按现前端 TimelineComparison.ts 平移。
 */
import { useState } from 'react'

export interface TimelineSegment {
  speaker: string
  start: number
  end: number
  text: string
  isMatch?: boolean
}

export interface TimelineResult {
  referenceSegments: TimelineSegment[]
  resultSegments: TimelineSegment[]
  effectiveDuration: number
  speakers: string[]
}

export const TIMELINE_PARAM_TYPES = ['rttm', 'stm', 'json']

/** 解析 RTTM 文本（NA 说话人/起止秒/文本） */
export function parseRttmText(text: string): TimelineSegment[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/\s+/)
      const start = Number(parts[2]) || 0
      const dur = Number(parts[3]) || 0
      const speaker = parts[7] ?? 'SPK'
      return { speaker, start, end: start + dur, text: parts.slice(8).join(' ') }
    })
}

/** 解析 STM 文本（speaker 起 止 文本） */
export function parseStmText(text: string): TimelineSegment[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/\s+/)
      const start = Number(parts[2]) || 0
      const end = Number(parts[3]) || start
      const speaker = parts[0] ?? 'SPK'
      return { speaker, start, end, text: parts.slice(4).join(' ') }
    })
}

export function parseTimelineData(value: unknown): TimelineSegment[] {
  if (Array.isArray(value)) return value as TimelineSegment[]
  if (typeof value === 'string') {
    const text = value.trim()
    if (text.startsWith('[') || text.startsWith('{')) {
      try {
        return parseTimelineData(JSON.parse(text))
      } catch {
        return []
      }
    }
    if (/^SPEAKER\s/.test(text) || /^SPK\s/.test(text)) return parseRttmText(text)
    return parseStmText(text)
  }
  return []
}

/** 贪心说话人映射（按重叠时间降序；±0.5s 容差匹配段） */
export function computeOptimalSpeakerMapping(
  reference: TimelineSegment[],
  result: TimelineSegment[]
): Map<string, string> {
  const mapping = new Map<string, string>()
  const used = new Set<string>()
  const overlaps: { ref: string; res: string; overlap: number }[] = []
  for (const r of reference) {
    for (const s of result) {
      const overlap = Math.max(
        0,
        Math.min(r.end, s.end) - Math.max(r.start, s.start)
      )
      if (overlap > 0.5) overlaps.push({ ref: r.speaker, res: s.speaker, overlap })
    }
  }
  overlaps.sort((a, b) => b.overlap - a.overlap)
  for (const { ref, res } of overlaps) {
    if (mapping.has(ref) || used.has(res)) continue
    mapping.set(ref, res)
    used.add(res)
  }
  return mapping
}

export function useTimelineComparison() {
  const [scale, setScale] = useState(1)
  const [selectedSpeaker, setSelectedSpeaker] = useState('全部')

  const zoom = (factor: number) =>
    setScale((s) => Math.min(100, Math.max(0.5, s * factor)))

  const resetZoom = () => setScale(1)

  const build = (
    algorithmResults: unknown[],
    referenceParams: Record<string, unknown> | undefined,
    fieldMappingRef?: string[]
  ): TimelineResult | null => {
    const resultRows = (algorithmResults ?? []).filter((row) => {
      const r = row as { paramType?: string }
      return r.paramType ? TIMELINE_PARAM_TYPES.includes(r.paramType) : false
    })
    const refKeys = fieldMappingRef ?? ['stmRef', 'rttmRef']
    const refRows = referenceParams
      ? refKeys.map((k) => referenceParams[k]).filter((v) => v !== undefined)
      : []
    const referenceSegments = refRows.flatMap((v) => parseTimelineData(v))
    const resultSegments = resultRows.flatMap((v) => parseTimelineData((v as { value?: unknown }).value))
    if (referenceSegments.length === 0 && resultSegments.length === 0) return null
    const speakers = [...new Set(referenceSegments.map((s) => s.speaker))]
    const maxEnd = Math.max(
      0,
      ...referenceSegments.map((s) => s.end),
      ...resultSegments.map((s) => s.end)
    )
    return {
      referenceSegments,
      resultSegments,
      effectiveDuration: maxEnd,
      speakers: ['全部', ...speakers],
    }
  }

  return { scale, setScale, zoom, resetZoom, selectedSpeaker, setSelectedSpeaker, build }
}
