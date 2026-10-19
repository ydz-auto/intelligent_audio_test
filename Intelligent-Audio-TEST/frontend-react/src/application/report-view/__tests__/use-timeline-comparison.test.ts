/**
 * 时间轴对比解析单测（接线卡 INT-951）：
 * parseTimelineData / isTimelineSegment / hasTimelineData 对 `rounds`(json 多轮结果数组)
 * 与真实 rttm/stm 段结构做结构校验——rounds 不产生段、不出现 undefined speaker、无 NaN 时长。
 */
import { describe, expect, it } from 'vitest'

import {
  TIMELINE_PARAM_TYPES,
  hasTimelineData,
  isTimelineSegment,
  parseTimelineData,
  parseRttmText,
  parseStmText,
} from '@/application/report-view/use-timeline-comparison'

/** 报告 65/INT321 实测 `rounds` json 多轮结果数组形态（round_number/input/output/latency…，无 speaker/start/end） */
const roundsArray = [
  {
    round_number: 1,
    input: '',
    input_type: 'text',
    output: '你好，有什么可以帮助你的？',
    latency: 10.111,
    response_metrics: { latency: 0.342 },
    success: true,
  },
  {
    round_number: 2,
    input: '',
    input_type: 'text',
    output: '你好，有什么可以帮助你的？',
    latency: 0.429,
    response_metrics: { latency: 0.251 },
    success: true,
  },
]

/** 真实 rttm/stm json 段数组形态 */
const timelineSegments = [
  { speaker: 'SPK_00', start: 0, end: 1.2, text: '你好' },
  { speaker: 'SPK_01', start: 1.5, end: 3.0, text: '请问有什么可以帮助' },
]

describe('parseTimelineData（INT-951 结构校验）', () => {
  it('rounds 多轮结果数组 → 空段（不再透传为时间轴）', () => {
    expect(parseTimelineData(roundsArray)).toEqual([])
  })

  it('含 speaker/start/end 的时间轴数组 → 段透出', () => {
    expect(parseTimelineData(timelineSegments)).toEqual(timelineSegments)
  })

  it('rounds 数组的 JSON 字符串 → 空段', () => {
    expect(parseTimelineData(JSON.stringify(roundsArray))).toEqual([])
  })

  it('时间轴数组的 JSON 字符串 → 段透出', () => {
    expect(parseTimelineData(JSON.stringify(timelineSegments))).toEqual(timelineSegments)
  })

  it('start/end 数字字符串 → 归一化为数值', () => {
    const mixed = [{ speaker: 'A', start: '1.5', end: '3', text: 'x' }]
    expect(parseTimelineData(mixed)).toEqual([{ speaker: 'A', start: 1.5, end: 3, text: 'x' }])
  })

  it('RTTM 文本仍按行解析', () => {
    const segs = parseTimelineData('SPEAKER A 0 3.0 0 0 0 SPK_00 你好')
    expect(segs.length).toBe(1)
    expect(segs[0].speaker).toBe('SPK_00')
    expect(segs[0].start).toBe(0)
    expect(segs[0].end).toBe(3)
  })
})

describe('isTimelineSegment', () => {
  it('rounds 轮对象（无 speaker/start/end）→ false', () => {
    expect(isTimelineSegment(roundsArray[0])).toBe(false)
  })
  it('时间轴段对象 → true', () => {
    expect(isTimelineSegment(timelineSegments[0])).toBe(true)
  })
  it('非对象 / 空 speaker / 非数值 start → false', () => {
    expect(isTimelineSegment(null)).toBe(false)
    expect(isTimelineSegment('x')).toBe(false)
    expect(isTimelineSegment({ speaker: '', start: 0, end: 1 })).toBe(false)
    expect(isTimelineSegment({ speaker: 'A', start: 'x', end: 1 })).toBe(false)
  })
})

describe('hasTimelineData（hasTimeline 二次校验用）', () => {
  it('rounds 多轮数组 → false（不触发时间轴对比）', () => {
    expect(hasTimelineData(roundsArray)).toBe(false)
  })
  it('时间轴段数组 → true', () => {
    expect(hasTimelineData(timelineSegments)).toBe(true)
  })
  it('rounds JSON 字符串 → false；时间轴 JSON 字符串 → true', () => {
    expect(hasTimelineData(JSON.stringify(roundsArray))).toBe(false)
    expect(hasTimelineData(JSON.stringify(timelineSegments))).toBe(true)
  })
  it('空 / 纯文本 → false', () => {
    expect(hasTimelineData('')).toBe(false)
    expect(hasTimelineData('  ')).toBe(false)
    expect(hasTimelineData('普通文本')).toBe(false)
  })
})

/** build() 同款过滤逻辑（无 speaker/start/end 的 json 行不产出段 → 无 NaN 时长、无 undefined 说话人） */
function buildResultSegments(algorithmResults: Array<{ paramType?: string; value?: unknown }>) {
  const resultRows = algorithmResults.filter((row) => {
    return row.paramType ? TIMELINE_PARAM_TYPES.includes(row.paramType) : false
  })
  const resultSegments = resultRows.flatMap((v) => {
    const segs = parseTimelineData(v.value)
    return segs.map((s) => ({ ...s, resource: undefined as string | undefined }))
  })
  const speakers = [...new Set(resultSegments.map((s) => s.speaker))]
  const maxEnd = Math.max(0, ...resultSegments.map((s) => s.end))
  return { resultSegments, speakers, maxEnd }
}

describe('build 消费侧（INT-951 端到端）', () => {
  it('rounds json 结果行 → 空段、无 undefined speaker、时长 0（不 NaN）', () => {
    const { resultSegments, speakers, maxEnd } = buildResultSegments([
      { paramType: 'json', value: roundsArray },
    ])
    expect(resultSegments).toEqual([])
    expect(speakers).toEqual([])
    expect(Number.isNaN(maxEnd)).toBe(false)
    expect(maxEnd).toBe(0)
  })

  it('真实时间轴 json 结果行 → 段完整、speaker 去 undefined、时长为末段 end', () => {
    const { resultSegments, speakers, maxEnd } = buildResultSegments([
      { paramType: 'json', value: timelineSegments },
    ])
    expect(resultSegments).toHaveLength(2)
    expect(speakers).toEqual(['SPK_00', 'SPK_01'])
    expect(maxEnd).toBe(3.0)
  })

  it('rttm/stm 文本行不受影响', () => {
    expect(parseRttmText('SPEAKER A 1 0.0 1.0 0 0 0 你好').length).toBe(1)
    expect(parseStmText('A 0.0 2.0 你好').length).toBe(1)
  })
})
