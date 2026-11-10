/** 「按 JSON 批量更新标注」纯逻辑单测。 */
import { describe, expect, it } from 'vitest'

import {
  buildAudioNameLookup,
  extractAnnotationAudioName,
  findAudioByName,
  isTopLevelJsonFile,
  normalizeAudioName,
  parseAnnotationJsonEntries,
  pathDirectoryTags,
  resolveAnnotationTags,
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

describe('pathDirectoryTags（VEGA-64 目录段标签）', () => {
  it('普通嵌套路径逐段提取（含根目录名，去文件名）', () => {
    expect(pathDirectoryTags('root/tagA/sub/x.json')).toEqual(['root', 'tagA', 'sub'])
  })

  it('无目录（纯文件名）返回空数组', () => {
    expect(pathDirectoryTags('x.json')).toEqual([])
  })

  it('反斜杠按分隔符归一，空段忽略', () => {
    expect(pathDirectoryTags('root\\tagA//x.json')).toEqual(['root', 'tagA'])
    expect(pathDirectoryTags('root//tagA/x.json')).toEqual(['root', 'tagA'])
  })

  it('重复目录段按序去重', () => {
    expect(pathDirectoryTags('root/tagA/root/x.json')).toEqual(['root', 'tagA'])
  })
})

describe('resolveAnnotationTags（标签来源三档矩阵）', () => {
  const jsonTags = ['t1']
  const nestedPath = 'root/d1/x.json'

  it('both = JSON tags 在前 + 路径段在后，并集去重', () => {
    expect(resolveAnnotationTags(['t1', 'd1'], nestedPath, 'both')).toEqual([
      't1',
      'd1',
      'root',
    ])
  })

  it('both 无重复时全量保留', () => {
    expect(resolveAnnotationTags(jsonTags, nestedPath, 'both')).toEqual([
      't1',
      'root',
      'd1',
    ])
  })

  it('json 档仅取 JSON tags（路径段不并入）', () => {
    expect(resolveAnnotationTags(jsonTags, nestedPath, 'json')).toEqual(['t1'])
    expect(resolveAnnotationTags([], nestedPath, 'json')).toEqual([])
  })

  it('path 档仅取路径目录段（JSON tags 不并入）', () => {
    expect(resolveAnnotationTags(jsonTags, nestedPath, 'path')).toEqual(['root', 'd1'])
  })

  it('path 档无目录段时为空', () => {
    expect(resolveAnnotationTags(jsonTags, 'x.json', 'path')).toEqual([])
  })

  it('both 档 JSON 无 tags 且路径无目录段时为空', () => {
    expect(resolveAnnotationTags([], 'x.json', 'both')).toEqual([])
  })
})

describe('parseAnnotationJsonEntries 的 jsonTags（VEGA-64）', () => {
  it('顶层 tags 全字符串数组时每条 entry 共享同一数组', () => {
    const entries = parseAnnotationJsonEntries('case.json', {
      tags: ['t1', 't2'],
      rounds: [
        { segments: [{ audio: 'a.wav' }, { audio: 'b.wav' }] },
        { segments: [{ audio: 'c.wav' }] },
      ],
    })

    expect(entries).toHaveLength(3)
    expect(entries[0].jsonTags).toEqual(['t1', 't2'])
    expect(entries[1].jsonTags).toBe(entries[0].jsonTags)
    expect(entries[2].jsonTags).toBe(entries[0].jsonTags)
  })

  it('畸形 tags 降级空数组，不丢条目', () => {
    const entries = parseAnnotationJsonEntries('case.json', {
      tags: ['t1', 42],
      rounds: [{ segments: [{ audio: 'a.wav' }] }],
    })

    expect(entries).toHaveLength(1)
    expect(entries[0].jsonTags).toEqual([])
  })

  it('无 tags 字段时 jsonTags 为空数组', () => {
    const entries = parseAnnotationJsonEntries('case.json', {
      rounds: [{ segments: [{ audio: 'a.wav' }] }],
    })

    expect(entries[0].jsonTags).toEqual([])
  })

  it('单音频标注 JSON 同样带 jsonTags', () => {
    const entries = parseAnnotationJsonEntries('audio1.json', {
      audio_name: 'audio1.wav',
      tags: ['t1'],
    })

    expect(entries).toHaveLength(1)
    expect(entries[0].jsonTags).toEqual(['t1'])
  })
})

describe('两路径同构断言（VEGA-64：picker 拼装 vs webkitRelativePath）', () => {
  it('同一目录结构下两路径产出同一目录段集合（递归开档）', () => {
    // picker 拼装值：相对路径定义以所选根目录 handle.name 为首段
    const pickerAssembled = 'root/tagA/sub/x.json'
    // webkitdirectory 兜底路径：webkitRelativePath 原值（天然含所选根目录名）
    const webkitRelative = 'root/tagA/sub/x.json'

    expect(pathDirectoryTags(pickerAssembled)).toEqual(['root', 'tagA', 'sub'])
    expect(pathDirectoryTags(webkitRelative)).toEqual(pathDirectoryTags(pickerAssembled))
  })

  it('递归关档两路径同为 根/文件.json，目录段同为 [根]', () => {
    const pickerAssembled = 'root/x.json'
    const webkitRelative = 'root/x.json'

    expect(pathDirectoryTags(pickerAssembled)).toEqual(['root'])
    expect(pathDirectoryTags(webkitRelative)).toEqual(pathDirectoryTags(pickerAssembled))
  })
})
