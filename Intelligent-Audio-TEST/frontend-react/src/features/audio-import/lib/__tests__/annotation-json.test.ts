/** 「按 JSON 批量更新标注」纯逻辑单测。 */
import { describe, expect, it } from 'vitest'

import {
  buildAudioNameLookup,
  extractAnnotationAudioName,
  findAudioByName,
  isTopLevelJsonFile,
  normalizeAudioName,
  parseAnnotationJsonEntries,
} from '@/features/audio-import/lib/annotation-json'

describe('extractAnnotationAudioName', () => {
  it('优先读取顶层 audio_name 并去掉目录', () => {
    expect(
      extractAnnotationAudioName({
        audio_name: 'recordings/audio1.wav',
        segments: [{ audio: 'other.wav', text: '你好' }],
      })
    ).toBe('audio1.wav')
  })

  it('支持 rounds[].segments[].audio 结构', () => {
    expect(
      extractAnnotationAudioName({
        rounds: [
          {
            segments: [{ audio: 'round1.wav', text: 'a' }],
          },
        ],
      })
    ).toBe('round1.wav')
  })

  it('支持 data 包装的 audioName', () => {
    expect(
      extractAnnotationAudioName({
        data: { audioName: 'nested/audio2.mp3', annotations: [] },
      })
    ).toBe('audio2.mp3')
  })

  it('没有音频名称时返回空串', () => {
    expect(extractAnnotationAudioName({ segments: [{ text: '无音频名' }] })).toBe('')
  })

  it('顶层 name 只有音频扩展名时才作为音频名', () => {
    expect(
      extractAnnotationAudioName({ name: 'audio3.wav', segments: [{ text: 'a' }] })
    ).toBe('audio3.wav')
    expect(
      extractAnnotationAudioName({ name: '普通用例名', segments: [{ text: 'a' }] })
    ).toBe('')
  })
})

describe('文件夹第一层 JSON 过滤', () => {
  it('根目录下的 JSON 保留，嵌套目录 JSON 忽略', () => {
    expect(isTopLevelJsonFile('标注/audio1.json')).toBe(true)
    expect(isTopLevelJsonFile('标注/子目录/audio2.json')).toBe(false)
  })

  it('只看 .json 扩展名', () => {
    expect(isTopLevelJsonFile('标注/audio1.txt')).toBe(false)
    expect(isTopLevelJsonFile('标注/audio1.JSON')).toBe(true)
  })
})

describe('按音频名称匹配', () => {
  const lookup = buildAudioNameLookup([
    { id: 11, name: 'audio1.wav' },
    { id: 12, name: '语音/audio2.mp3' },
  ])

  it('全名精确匹配', () => {
    expect(findAudioByName('audio1.wav', lookup)?.id).toBe(11)
  })

  it('JSON 只有文件名时按叶文件名匹配', () => {
    expect(findAudioByName('audio2.mp3', lookup)?.id).toBe(12)
  })

  it('无扩展名时按基名兜底', () => {
    expect(findAudioByName('audio1', lookup)?.id).toBe(11)
  })

  it('找不到时返回 undefined', () => {
    expect(findAudioByName('missing.wav', lookup)).toBeUndefined()
  })

  it('normalizeAudioName 同时兼容反斜杠目录', () => {
    expect(normalizeAudioName('C:\\标注\\audio1.wav')).toBe('audio1.wav')
  })
})

describe('parseAnnotationJsonEntries', () => {
  it('多轮 JSON 按每个 segment 的音频拆分标注条目', () => {
    const entries = parseAnnotationJsonEntries('case.json', {
      rounds: [
        {
          round_number: 1,
          segments: [
            {
              audio: 'round1.wav',
              query: '问题一',
              correctAnswer: '答案一',
              text: ' ',
            },
          ],
        },
        {
          round_number: 2,
          segments: [
            {
              audio: 'round2.wav',
              query: '问题二',
              correctAnswer: '答案二',
              text: ' ',
            },
          ],
        },
      ],
    })

    expect(entries).toHaveLength(2)
    expect(entries[0].audioName).toBe('round1.wav')
    expect(entries[0].segmentLabel).toBe('第 1 轮')
    expect(entries[1].audioName).toBe('round2.wav')
    const data = entries[0].annotations[0].data as {
      segments: Array<Record<string, unknown>>
    }
    expect(data.segments[0].query).toBe('问题一')
    expect(data.segments[0].audio).toBeUndefined()
  })

  it('单音频标注 JSON 沿用原有标注解析', () => {
    const entries = parseAnnotationJsonEntries('audio1.json', {
      audio_name: 'audio1.wav',
      segments: [{ start: 0, end: 1, text: '你好' }],
    })

    expect(entries).toHaveLength(1)
    expect(entries[0].audioName).toBe('audio1.wav')
    const data = entries[0].annotations[0].data as {
      segments: Array<Record<string, unknown>>
    }
    expect(data.segments[0].text).toBe('你好')
  })
})
