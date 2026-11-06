/**
 * 导出包条目读取（INT-2196「包含音频文件」核对）。
 * 只读 ZIP 中央目录条目名：勾选音频后据此判断包内到底有没有 `audios/` 文件。
 */
import { describe, expect, it } from 'vitest'

import {
  countAudioEntries,
  countZipAudioEntries,
  zipEntryNames,
} from '@/features/testcases/lib/zip-audio-entries'

const encoder = new TextEncoder()

function u16(value: number): number[] {
  return [value & 0xff, (value >> 8) & 0xff]
}

function u32(value: number): number[] {
  return [value & 0xff, (value >> 8) & 0xff, (value >> 16) & 0xff, (value >> 24) & 0xff]
}

/** 造一个 stored（不压缩）的最小合法 ZIP，供解析用；Crc 置 0，解析侧不校验 */
function buildZip(entries: Array<{ name: string; data?: string }>): Uint8Array<ArrayBuffer> {
  const body: number[] = []
  const central: number[] = []
  for (const entry of entries) {
    const name = Array.from(encoder.encode(entry.name))
    const data = Array.from(encoder.encode(entry.data ?? ''))
    const localOffset = body.length
    body.push(
      ...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0),
      ...u32(0), ...u32(data.length), ...u32(data.length),
      ...u16(name.length), ...u16(0), ...name, ...data
    )
    central.push(
      ...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(0),
      ...u16(0), ...u16(0), ...u32(0), ...u32(data.length), ...u32(data.length),
      ...u16(name.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0),
      ...u32(0), ...u32(localOffset), ...name
    )
  }
  const centralOffset = body.length
  const eocd = [
    ...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(entries.length),
    ...u16(entries.length), ...u32(central.length), ...u32(centralOffset), ...u16(0),
  ]
  return new Uint8Array([...body, ...central, ...eocd])
}

describe('zip-audio-entries（INT-2196 导出包音频条目）', () => {
  it('读出全部条目名（含参考参数与音频）', () => {
    const bytes = buildZip([
      { name: 'manifest.json', data: '{}' },
      { name: 'testcases.json', data: '{}' },
      { name: 'audios/audio-1.wav', data: 'wav' },
    ])

    expect(zipEntryNames(bytes)).toEqual([
      'manifest.json',
      'testcases.json',
      'audios/audio-1.wav',
    ])
  })

  it('countAudioEntries 只数 audios/ 下的文件，不数目录条目', () => {
    expect(
      countAudioEntries([
        'manifest.json',
        'audios/',
        'audios/a.wav',
        'audios/b.mp3',
        'reference_params/tc-1/round_1.json',
      ])
    ).toBe(2)
  })

  it('countZipAudioEntries：Blob 内无 audios/ → 0', async () => {
    const blob = new Blob([buildZip([{ name: 'manifest.json', data: '{}' }])])
    await expect(countZipAudioEntries(blob)).resolves.toBe(0)
  })

  it('countZipAudioEntries：Blob 内有两个音频 → 2', async () => {
    const blob = new Blob([
      buildZip([
        { name: 'manifest.json', data: '{}' },
        { name: 'audios/a.wav', data: 'wav' },
        { name: 'audios/b.flac', data: 'flac' },
      ]),
    ])
    await expect(countZipAudioEntries(blob)).resolves.toBe(2)
  })

  it('不是 ZIP（无 EOCD）→ 不误报，返回 0', async () => {
    await expect(countZipAudioEntries(new Blob(['zip-bytes']))).resolves.toBe(0)
  })

  it('环境读不出 Blob 内容 → null（调用方不提示）', async () => {
    const blob = { size: 1 } as unknown as Blob
    await expect(countZipAudioEntries(blob)).resolves.toBeNull()
  })
})
