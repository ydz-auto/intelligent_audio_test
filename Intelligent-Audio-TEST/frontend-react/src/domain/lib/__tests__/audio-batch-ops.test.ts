/**
 * 音频列表批量工具纯函数测试（domain/lib/audio-batch-ops，11_用例域.md §5.1 工具栏）。
 * - interleaveByTags：标签交错（多标签每段各现一次、标签顺序分段、空标签不改序）
 * - assignRoundRobin：设备交叉（按列表顺序轮转、空设备不改）
 * - patchByTag：标签设备（仅命中标签的条目被改）
 * - patchScope：批量设备/批量声压（全部/勾选范围）
 */
import { describe, expect, it } from 'vitest'

import {
  assignRoundRobin,
  interleaveByTags,
  patchByTag,
  patchScope,
  type BatchScope,
} from '@/domain/lib/audio-batch-ops'

interface Row {
  id: string
  fileId: string
  deviceId: string
  spl: number
}

const row = (id: string, fileId: string, deviceId = 'dev-1', spl = 65): Row => ({
  id,
  fileId,
  deviceId,
  spl,
})

const TAGS_BY_FILE: Record<string, string[]> = {
  'au-01': ['客厅', '中文'],
  'au-02': ['车内', '导航'],
  'au-03': ['会议室', '中文'],
  'au-04': ['音乐背景'],
  'au-05': ['英文'],
}

const tagsOf = (r: Row) => TAGS_BY_FILE[r.fileId] ?? []

describe('interleaveByTags', () => {
  const rows = [
    row('a', 'au-01'),
    row('b', 'au-02'),
    row('c', 'au-03'),
    row('d', 'au-04'),
    row('e', 'au-05'),
  ]

  it('按所选标签顺序分段，多标签条目在每个命中段各现一次，未命中条目追加末尾', () => {
    const out = interleaveByTags(rows, tagsOf, ['中文', '客厅'])
    // 「中文」段：au-01（客厅/中文）、au-03（会议室/中文）；「客厅」段：au-01（客厅/中文）；
    // 未命中（au-02/au-04/au-05）按原序追加末尾
    expect(out.map((r) => r.fileId)).toEqual([
      'au-01',
      'au-03',
      'au-01',
      'au-02',
      'au-04',
      'au-05',
    ])
  })

  it('空标签列表返回原列表副本（顺序不变）', () => {
    expect(interleaveByTags(rows, tagsOf, [])).toEqual(rows)
  })

  it('未命中任何标签时返回原列表副本（排序不改丢数据）', () => {
    expect(interleaveByTags(rows, tagsOf, ['不存在'])).toEqual(rows)
  })
})

describe('assignRoundRobin', () => {
  it('按列表顺序轮转分配设备', () => {
    const rows = [row('a', 'au-01'), row('b', 'au-02'), row('c', 'au-03'), row('d', 'au-04')]
    const out = assignRoundRobin(rows, ['dev-1', 'dev-2'], (r, deviceId) => ({ ...r, deviceId }))
    expect(out.map((r) => r.deviceId)).toEqual(['dev-1', 'dev-2', 'dev-1', 'dev-2'])
  })

  it('空设备列表返回原列表副本', () => {
    const rows = [row('a', 'au-01'), row('b', 'au-02')]
    expect(assignRoundRobin(rows, [], (r, deviceId) => ({ ...r, deviceId }))).toEqual(rows)
  })
})

describe('patchByTag', () => {
  it('仅命中标签的条目应用补丁', () => {
    const rows = [row('a', 'au-01'), row('b', 'au-02'), row('c', 'au-03')]
    const out = patchByTag(rows, tagsOf, '中文', (r) => ({ ...r, deviceId: 'dev-2' }))
    expect(out.map((r) => r.deviceId)).toEqual(['dev-2', 'dev-1', 'dev-2'])
  })
})

describe('patchScope', () => {
  const rows = [row('a', 'au-01'), row('b', 'au-02'), row('c', 'au-03')]
  const selected = new Set(['a', 'c'])

  it.each<{ scope: BatchScope; expected: number[] }>([
    { scope: 'all', expected: [80, 80, 80] },
    { scope: 'selected', expected: [80, 65, 80] },
  ])('范围 $scope 应用到对应条目', ({ scope, expected }) => {
    const out = patchScope(
      rows,
      scope,
      (r) => selected.has(r.id),
      (r) => ({ ...r, spl: 80 })
    )
    expect(out.map((r) => r.spl)).toEqual(expected)
  })
})
