/**
 * 标注解析单元测试（annotation.ts）。
 * 覆盖 P2-1 审计项：标准 {segments:[...]} 四形态 + rttm/stm 段级解析，均不得双层嵌套。
 */
import { describe, expect, it } from 'vitest'

import {
  determineAnnotationName,
  parseAnnotationFile,
  parseAnnotationFormat,
  parseAnnotationsForAudios,
  parseAudioTxt,
} from '@/features/audio-import/lib/annotation'

describe('parseAudioTxt（txt 首行 ASR + 翻译语向）', () => {
  it('首行作 ASR，后续 文本\t语向 行作翻译', () => {
    const parsed = parseAudioTxt('今天的天气很好\n今天天气不错\tzh-CN\nHow are you\ten-US')
    expect(parsed.asrText).toBe('今天的天气很好')
    expect(parsed.translations).toEqual([
      { text: '今天天气不错', direction: 'zh-cn' },
      { text: 'How are you', direction: 'en-us' },
    ])
  })

  it('空内容返回空结果', () => {
    expect(parseAudioTxt('')).toEqual({ asrText: '', translations: [] })
  })
})

describe('parseAnnotationFile json（P2-1 标准形态）', () => {
  it('{segments:[...]} 解析出正确 segments，不双层嵌套', () => {
    const result = parseAnnotationFile(
      'audio1.json',
      JSON.stringify({
        segments: [
          { start: 0, end: 1.2, text: '你好', speaker: 'A' },
          { start: 1.2, end: 2.5, text: '谢谢', speaker: 'B' },
        ],
      })
    )
    expect(result).toHaveLength(1)
    const data = result[0].data as { segments: Array<Record<string, unknown>> }
    expect(data.segments).toHaveLength(2)
    expect(data.segments[0].text).toBe('你好')
    expect(data.segments[0].speaker).toBe('A')
    expect(data.segments[1].start).toBe(1.2)
    expect(result[0].source_language).toBe('')
    expect(result[0].code).toBe('reference')
  })

  it('裸数组 JSON 解析为 segments', () => {
    const result = parseAnnotationFile(
      'audio1.json',
      JSON.stringify([{ start: 0, end: 1, text: 'a' }, { start: 1, end: 2, text: 'b' }])
    )
    const data = result[0].data as { segments: Array<Record<string, unknown>> }
    expect(data.segments).toHaveLength(2)
    expect(data.segments[1].text).toBe('b')
  })

  it('{annotations:[...]} 逐条解析', () => {
    const result = parseAnnotationFile(
      'audio1.json',
      JSON.stringify({
        annotations: [
          { code: 'asr', segments: [{ start: 0, end: 1, text: 'a' }] },
          { code: 'translation', segments: [{ start: 0, end: 1, text: 'b' }] },
        ],
      })
    )
    expect(result).toHaveLength(2)
    expect(result[0].code).toBe('asr')
    expect(result[1].code).toBe('translation')
    const data = result[1].data as { segments: Array<Record<string, unknown>> }
    expect(data.segments[0].text).toBe('b')
  })

  it('{txt:[...]} 与平铺对象兜底', () => {
    const fromTxt = parseAnnotationFile('audio1.json', JSON.stringify({ txt: [{ start: 0, end: 1, text: 'x' }] }))
    const data = fromTxt[0].data as { segments: Array<Record<string, unknown>> }
    expect(data.segments).toHaveLength(1)
    expect(data.segments[0].text).toBe('x')

    const flat = parseAnnotationFile('audio1.json', JSON.stringify({ query: 'q1', correctAnswer: 'a1' }))
    const flatData = flat[0].data as { segments: Array<Record<string, unknown>> }
    expect(flatData.segments[0].query).toBe('q1')
    expect(flatData.segments[0].correctAnswer).toBe('a1')
  })

  it('顶层 source_language / target_language / code 透出', () => {
    const result = parseAnnotationFile(
      'audio1.json',
      JSON.stringify({ source_language: 'zh-CN', target_language: 'en-US', code: 'translation', segments: [{ start: 0, end: 1, text: '你好' }] })
    )
    expect(result[0].source_language).toBe('zh-CN')
    expect(result[0].target_language).toBe('en-US')
    expect(result[0].code).toBe('translation')
  })

  it('fallbackCode 优先于 JSON 内 code', () => {
    const result = parseAnnotationFile(
      'audio1.json',
      JSON.stringify({ code: 'asr', segments: [{ start: 0, end: 1, text: 'a' }] }),
      'diarization'
    )
    expect(result[0].code).toBe('diarization')
  })
})

describe('parseAnnotationFile jsonl', () => {
  it('逐行 JSON 为段', () => {
    const result = parseAnnotationFile(
      'audio1.jsonl',
      '{ "start": 0, "end": 1, "text": "一" }\n{ "start": 1, "end": 2, "text": "二" }'
    )
    const data = result[0].data as { segments: Array<Record<string, unknown>> }
    expect(data.segments).toHaveLength(2)
    expect(data.segments[0].text).toBe('一')
  })
})

describe('parseAnnotationFile rttm / stm（段级解析）', () => {
  it('rttm SPEAKER 行转 start/end/speaker', () => {
    const rttm =
      'SPEAKER audio1 1 0.000 1.200 <NA> <NA> speaker_A <NA>\nSPEAKER audio1 1 1.200 1.300 <NA> <NA> speaker_B <NA>'
    const result = parseAnnotationFile('audio1.rttm', rttm)
    expect(result).toHaveLength(1)
    expect(result[0].code).toBe('diarization')
    const data = result[0].data as { segments: Array<Record<string, unknown>> }
    expect(data.segments).toHaveLength(2)
    expect(data.segments[0].speaker).toBe('speaker_A')
    expect(data.segments[0].end).toBeCloseTo(1.2)
    expect(data.segments[1].speaker).toBe('speaker_B')
  })

  it('stm 行转段（V9.7.10 字段位：parts[1] 说话人 / [2] 起始 / [3] 结束 / [5:] 文本）', () => {
    const stm = 'audio1 speaker_A 0.000 1.200 <O> 你好 <$>\naudio1 speaker_B 1.200 2.000 <O> 谢谢 <$>'
    const result = parseAnnotationFile('audio1.stm', stm)
    const data = result[0].data as { segments: Array<Record<string, unknown>> }
    expect(data.segments).toHaveLength(2)
    expect(data.segments[0].speaker).toBe('speaker_A')
    expect(data.segments[0].text).toContain('你好')
  })
})

describe('parseAnnotationFile txt', () => {
  it('ASR + 翻译标注，source/target 从语向拆分', () => {
    const result = parseAnnotationFile('audio1.txt', 'ASR文本内容\n翻译文本\tzh-CN')
    expect(result).toHaveLength(2)
    expect(result[0].code).toBe('asr')
    expect((result[0].data as { text: string }).text).toBe('ASR文本内容')
    expect(result[1].code).toBe('translation')
    expect(result[1].source_language).toBe('zh')
    expect(result[1].target_language).toBe('cn')
  })
})

describe('parseAnnotationFormat', () => {
  it('返回四形态之一的 {segments:[...]} 标准形态', () => {
    const parsed = parseAnnotationFormat(JSON.stringify({ segments: [{ start: 0, end: 1, text: 'a' }] }), 'json')
    expect(parsed.segments).toHaveLength(1)
    expect(parsed.segments[0].text).toBe('a')
  })
})

describe('determineAnnotationName', () => {
  it('按文件名与格式推断', () => {
    expect(determineAnnotationName('audio_asr.json', 'json')).toBe('asr')
    expect(determineAnnotationName('audio_trans.json', 'json')).toBe('translation')
    expect(determineAnnotationName('audio1.rttm', 'rttm')).toBe('diarization')
    expect(determineAnnotationName('audio1.json', 'json')).toBe('reference')
  })
})

describe('parseAnnotationsForAudios（按 baseKey / 叶文件名匹配音频与标注）', () => {
  /** jsdom File 无 webkitRelativePath，用 defineProperty 补充（模拟 webkitdirectory 选文件夹） */
  function fileWithRel(name: string, rel: string, content = '{}'): File {
    const f = new File([content], name, { type: 'text/plain' })
    Object.defineProperty(f, 'webkitRelativePath', {
      value: rel,
      configurable: true,
    })
    return f
  }

  it('同目录 baseKey 匹配 + 叶文件名回退匹配', async () => {
    const annJson = fileWithRel(
      'audio1.json',
      'round_a/audio1.json',
      JSON.stringify({ code: 'asr', segments: [{ start: 0, end: 1, text: 'a' }] })
    )
    const annOther = fileWithRel(
      'audio2.json',
      'round_b/audio2.json',
      JSON.stringify({ code: 'asr', segments: [{ start: 0, end: 1, text: 'b' }] })
    )
    // audio1 同目录 baseKey 命中；audioX 不同目录但叶名 audio1 → 叶文件名回退命中；
    // audio3 无同名标注 → 空
    const audio1 = fileWithRel('audio1.wav', 'round_a/audio1.wav')
    const audioX = fileWithRel('audio1.wav', 'round_c/audio1.wav')
    const audio3 = fileWithRel('audio3.wav', 'round_c/audio3.wav')
    const result = await parseAnnotationsForAudios(
      [annJson, annOther],
      [audio1, audioX, audio3],
      'asr'
    )
    expect(result).toHaveLength(3)
    const data1 = result[0][0].data as { segments: Array<Record<string, unknown>> }
    expect(data1.segments[0].text).toBe('a')
    expect(result[1][0].data).toEqual(data1)
    expect(result[2]).toHaveLength(0)
  })

  it('fallbackCode 不覆盖 txt 的 asr/translation', async () => {
    const txt = fileWithRel(
      'audio1.txt',
      'audio1.txt',
      'ASR行\n翻译行\tzh-CN'
    )
    const audio1 = fileWithRel('audio1.wav', 'audio1.wav')
    const result = await parseAnnotationsForAudios([txt], [audio1], 'diarization')
    expect(result[0].map((a) => a.code)).toEqual(['asr', 'translation'])
  })
})
