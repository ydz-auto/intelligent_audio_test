/**
 * 浏览器端 MD5 单测（INT-1582 批量更新标注按内容 MD5 匹配音频）。
 * 覆盖 RFC 1321 标准向量、跨 64 字节块边界、分块 append 与整只 append 等价、
 * 以及 md5OfFile 按 Blob 切片流式读取的摘要与字节序列一致。
 */
import { createHash } from 'node:crypto'

import { describe, expect, it } from 'vitest'

import { Md5, md5Hex, md5OfFile } from '@/features/audio-import/lib/md5'

const utf8 = (text: string) => new TextEncoder().encode(text)

/** 参照实现：node:crypto（测试环境专用，产物不引用） */
const nodeMd5 = (bytes: Uint8Array) => createHash('md5').update(bytes).digest('hex')

describe('md5Hex 标准向量', () => {
  it('空串', () => {
    expect(md5Hex(utf8(''))).toBe('d41d8cd98f00b204e9800998ecf8427e')
  })

  it('"abc"', () => {
    expect(md5Hex(utf8('abc'))).toBe('900150983cd24fb0d6963f7d28e17f72')
  })

  it('"The quick brown fox jumps over the lazy dog"', () => {
    expect(md5Hex(utf8('The quick brown fox jumps over the lazy dog'))).toBe(
      '9e107d9d372bb6826bd81d3542a419d6'
    )
  })

  it('中文 UTF-8 文本与 node:crypto 一致', () => {
    const bytes = utf8('接线测试_INT1582_批量标注_第01轮')
    expect(md5Hex(bytes)).toBe(nodeMd5(bytes))
  })

  it('跨 56/64 字节补位边界的多档长度与 node:crypto 一致', () => {
    for (const size of [55, 56, 57, 63, 64, 65, 119, 120, 121, 1000]) {
      const bytes = new Uint8Array(size)
      for (let i = 0; i < size; i += 1) bytes[i] = (i * 37 + 11) & 0xff
      expect(md5Hex(bytes)).toBe(nodeMd5(bytes))
    }
  })
})

describe('Md5 增量 append', () => {
  it('任意切分 append 与整只 append 结果一致', () => {
    const bytes = new Uint8Array(4096)
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = (i * 91 + 7) & 0xff
    const expected = nodeMd5(bytes)
    for (const chunkSize of [1, 13, 64, 65, 100, 1024]) {
      const hasher = new Md5()
      for (let offset = 0; offset < bytes.length; offset += chunkSize) {
        hasher.append(bytes.subarray(offset, Math.min(offset + chunkSize, bytes.length)))
      }
      expect(hasher.digest()).toBe(expected)
    }
  })
})

describe('md5OfFile', () => {
  it('Blob 摘要与字节序列一致，并按块回报进度', async () => {
    const head = utf8('audio-batch-annotation-dialog')
    const bytes = new Uint8Array(head.length + 70)
    bytes.set(head)
    const blob = new Blob([bytes])
    const progress: Array<[number, number]> = []
    const digest = await md5OfFile(blob, (loaded, total) => progress.push([loaded, total]))
    expect(digest).toBe(nodeMd5(bytes))
    expect(progress.at(-1)).toEqual([blob.size, blob.size])
  })
})
