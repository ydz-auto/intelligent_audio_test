/**
 * 文件夹导入 JSON 用例解析 / 分组 / 轮次推断单测（INT-1613，§5.7.6 恢复多轮导入）。
 * 覆盖：rounds 多轮 JSON → 升序连续 1..N + 每轮 audios；flat / txt 数组单轮；
 * 按 JSON 引用分组 + 未引用音频回退；无 JSON 时按文件夹推断（1 音频 1 轮 / 多音频 1 轮多音频）；
 * merge 后 audio_id 回填。
 * INT-1979：三种 JSON 形态的顶层 `tags` 解析 + 畸形 tags 的宽容降级。
 */
import { describe, expect, it } from 'vitest'

import type { UploadRoundConfig } from '@/infrastructure/api/audio-upload-api'
import {
  applyMergedAudioId,
  buildAudioImportGroups,
  buildCaseGroups,
  inferRounds,
  leafFolderName,
  parseCaseJson,
  type CaseGroup,
} from '@/features/audio-import/lib/case-rounds'

function makeFile(name: string, relativePath: string, content = ''): File {
  const file = new File([content], name, { type: 'application/octet-stream' })
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath })
  return file
}

function groupsOf(entries: Array<[string, CaseGroup]>): Map<string, CaseGroup> {
  return new Map(entries)
}

describe('parseCaseJson', () => {
  it('rounds 多轮 JSON → 轮次升序连续 1..N、每轮 audios 按 play_order 1..n', () => {
    const raw = JSON.stringify({
      rounds: [
        { round_number: 7, segments: [{ audio: 'a.wav', spl: 66 }] },
        { round_number: 3, segments: [{ audio: 'b.wav' }, { audio: 'c.wav' }] },
        { segments: [{ audio: 'd.wav', background_noise: { audio: 'noise.wav' } }] },
      ],
    })
    const group = parseCaseJson(raw, 'folder/三轮回放.json')
    expect(group).not.toBeNull()
    expect(group?.groupKey).toBe('三轮回放')
    expect(group?.rounds.map((r) => r.round_number)).toEqual([1, 2, 3])
    expect(group?.rounds[0].audios).toEqual([
      { audio_name: 'a.wav', play_order: 1, spl: 66 },
    ])
    expect(group?.rounds[1].audios.map((a) => [a.audio_name, a.play_order])).toEqual([
      ['b.wav', 1],
      ['c.wav', 2],
    ])
    // 噪声音频也计入分组引用，便于把音频文件归到本组
    expect(group?.audioNames).toContain('noise.wav')
  })

  it('flat 单轮 JSON（顶层即 segment）→ 1 轮', () => {
    const group = parseCaseJson(JSON.stringify({ audio: 'a.wav', spl: 70 }), 'x/flat.json')
    expect(group?.rounds).toHaveLength(1)
    expect(group?.rounds[0]).toMatchObject({
      round_number: 1,
      audios: [{ audio_name: 'a.wav', play_order: 1, spl: 70 }],
    })
  })

  it('txt 数组 JSON → 1 轮多音频', () => {
    const group = parseCaseJson(
      JSON.stringify({ txt: [{ audio: 'a.wav' }, { audio: 'b.wav' }] }),
      'x/txt.json'
    )
    expect(group?.rounds).toHaveLength(1)
    expect(group?.rounds[0].audios.map((a) => [a.audio_name, a.play_order])).toEqual([
      ['a.wav', 1],
      ['b.wav', 2],
    ])
  })

  it('非用例 JSON（segments 标注）/ 非法 JSON → null', () => {
    expect(parseCaseJson(JSON.stringify({ segments: [{ text: 'hi' }] }), 'ann.json')).toBeNull()
    expect(parseCaseJson('{bad json', 'bad.json')).toBeNull()
  })
})

describe('buildCaseGroups', () => {
  it('读取多个 JSON 用例文件 → 分组键 = 文件名去扩展名', async () => {
    const groups = await buildCaseGroups([
      makeFile('1.json', 'root/1.json', JSON.stringify({ rounds: [{ segments: [{ audio: 'a.wav' }] }] })),
      makeFile('2.json', 'root/2.json', JSON.stringify({ rounds: [{ segments: [{ audio: 'b.wav' }] }] })),
      makeFile('bad.json', 'root/bad.json', '{oops'),
    ])
    expect(Array.from(groups.keys()).sort()).toEqual(['1', '2'])
  })
})

describe('inferRounds', () => {
  it('1 个音频 → 1 轮；多个音频 → 1 轮多音频（都是单轮）', () => {
    const one = inferRounds([makeFile('a.wav', 'r/a.wav')])
    expect(one).toEqual([{ round_number: 1, audios: [{ audio_name: 'a.wav', play_order: 1 }] }])

    const many = inferRounds([
      makeFile('a.wav', 'r/a.wav'),
      makeFile('b.wav', 'r/b.wav'),
    ])
    expect(many).toHaveLength(1)
    expect(many[0].audios.map((a) => a.play_order)).toEqual([1, 2])
  })
})

describe('buildAudioImportGroups', () => {
  it('JSON 引用的音频归入该 JSON 分组，轮次用 JSON rounds', () => {
    const group = parseCaseJson(
      JSON.stringify({
        rounds: [
          { segments: [{ audio: 'a.wav' }] },
          { segments: [{ audio: 'b.wav' }] },
          { segments: [{ audio: 'c.wav' }] },
        ],
      }),
      'root/多轮用例.json'
    )
    const files = [
      makeFile('a.wav', 'root/多轮用例/a.wav'),
      makeFile('b.wav', 'root/多轮用例/b.wav'),
      makeFile('c.wav', 'root/多轮用例/c.wav'),
    ]
    const groups = buildAudioImportGroups(files, groupsOf([['多轮用例', group!]]))
    expect(groups).toHaveLength(1)
    expect(groups[0].files).toHaveLength(3)
    expect(groups[0].rounds).toHaveLength(3)
    expect(groups[0].rounds.map((r) => r.round_number)).toEqual([1, 2, 3])
  })

  it('无 JSON → 按最子级文件夹分组（同文件夹多音频 = 1 组 1 轮多音频）', () => {
    const files = [
      makeFile('a.wav', 'root/子目录/a.wav'),
      makeFile('b.wav', 'root/子目录/b.wav'),
      makeFile('c.wav', 'root/另一个/c.wav'),
    ]
    const groups = buildAudioImportGroups(files, new Map())
    expect(groups).toHaveLength(2)
    const byKey = new Map(groups.map((g) => [g.groupKey, g]))
    expect(byKey.get('子目录')?.files).toHaveLength(2)
    expect(byKey.get('子目录')?.rounds).toHaveLength(1)
    expect(byKey.get('子目录')?.rounds[0].audios.map((a) => a.audio_name)).toEqual([
      'a.wav',
      'b.wav',
    ])
    expect(byKey.get('另一个')?.rounds).toHaveLength(1)
    expect(byKey.get('另一个')?.rounds[0].audios).toHaveLength(1)
  })

  it('有 JSON 时未被引用的音频各自成组（轮次按单文件推断）', () => {
    const group = parseCaseJson(
      JSON.stringify({ rounds: [{ segments: [{ audio: 'a.wav' }] }] }),
      'root/case.json'
    )
    const files = [
      makeFile('a.wav', 'root/case/a.wav'),
      makeFile('loose.wav', 'root/case/loose.wav'),
    ]
    const groups = buildAudioImportGroups(files, groupsOf([['case', group!]]))
    expect(groups).toHaveLength(2)
    const loose = groups.find((g) => g.groupKey === 'loose')
    expect(loose?.files).toHaveLength(1)
    expect(loose?.rounds).toHaveLength(1)
  })
})

describe('parseCaseJson（顶层 tags，INT-1979）', () => {
  it('rounds 多轮形态读取顶层 tags', () => {
    const group = parseCaseJson(
      JSON.stringify({ rounds: [{ segments: [{ audio: 'a.wav' }] }], tags: ['A', 'B'] }),
      'root/多轮.json'
    )
    expect(group?.tags).toEqual(['A', 'B'])
    expect(group?.rounds).toHaveLength(1)
  })

  it('flat 单轮形态读取顶层 tags', () => {
    const group = parseCaseJson(
      JSON.stringify({ audio: 'a.wav', tags: ['A', 'B'] }),
      'root/flat.json'
    )
    expect(group?.tags).toEqual(['A', 'B'])
    expect(group?.rounds).toHaveLength(1)
  })

  it('txt 数组单轮形态读取顶层 tags', () => {
    const group = parseCaseJson(
      JSON.stringify({ txt: [{ audio: 'a.wav' }], tags: ['A', 'B'] }),
      'root/txt.json'
    )
    expect(group?.tags).toEqual(['A', 'B'])
    expect(group?.rounds).toHaveLength(1)
  })

  it('无 tags / 非数组 / 含非字符串项 → tags 为空数组，分组与轮次照常解析', () => {
    const cases = [
      { rounds: [{ segments: [{ audio: 'a.wav' }] }] },
      { rounds: [{ segments: [{ audio: 'a.wav' }] }], tags: '不是数组' },
      { rounds: [{ segments: [{ audio: 'a.wav' }] }], tags: { a: 1 } },
      { rounds: [{ segments: [{ audio: 'a.wav' }] }], tags: ['A', 2] },
      { rounds: [{ segments: [{ audio: 'a.wav' }] }], tags: [null] },
    ]
    for (const raw of cases) {
      const group = parseCaseJson(JSON.stringify(raw), 'root/x.json')
      expect(group).not.toBeNull()
      expect(group?.tags).toEqual([])
      expect(group?.rounds).toHaveLength(1)
      expect(group?.rounds[0].audios.map((a) => a.audio_name)).toEqual(['a.wav'])
    }
  })
})

describe('buildAudioImportGroups（分组 tags 透传，INT-1979）', () => {
  it('JSON 分组的顶层 tags 挂到该组；无 JSON 分组的 tags 为空数组', () => {
    const group = parseCaseJson(
      JSON.stringify({ rounds: [{ segments: [{ audio: 'a.wav' }] }], tags: ['组标签'] }),
      'root/case.json'
    )
    const groups = buildAudioImportGroups(
      [
        makeFile('a.wav', 'root/case/a.wav'),
        makeFile('loose.wav', 'root/散文件/loose.wav'),
      ],
      groupsOf([['case', group!]])
    )
    expect(groups.find((g) => g.groupKey === 'case')?.tags).toEqual(['组标签'])
    expect(groups.find((g) => g.groupKey === 'loose')?.tags).toEqual([])
  })
})

describe('applyMergedAudioId', () => {
  it('按音频名回填 audio_id（跨轮次同名的都回填）', () => {
    const rounds: UploadRoundConfig[] = [
      { round_number: 1, audios: [{ audio_name: 'a.wav', play_order: 1 }] },
      { round_number: 2, audios: [{ audio_name: 'a.wav', play_order: 1 }] },
      { round_number: 3, audios: [{ audio_name: 'b.wav', play_order: 1 }] },
    ]
    applyMergedAudioId(rounds, 'a.wav', 42)
    expect(rounds[0].audios[0].audio_id).toBe(42)
    expect(rounds[1].audios[0].audio_id).toBe(42)
    expect(rounds[2].audios[0].audio_id).toBeUndefined()
  })
})

describe('leafFolderName', () => {
  it('取相对路径倒数第二段，无目录时按文件名去扩展名', () => {
    expect(leafFolderName(makeFile('a.wav', 'root/sub/a.wav'))).toBe('sub')
    expect(leafFolderName(makeFile('only.wav', ''))).toBe('only')
  })
})
