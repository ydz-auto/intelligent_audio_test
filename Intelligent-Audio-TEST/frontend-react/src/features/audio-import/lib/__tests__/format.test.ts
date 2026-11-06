/**
 * 音频展示格式化单测（features/audio-import/lib）。
 * 覆盖 formatFileSize/formatDuration/durationBucket（§5.3 列渲染口径）。
 */
import { describe, expect, it } from 'vitest'

import {
  durationBucket,
  formatDuration,
  formatFileSize,
} from '@/features/audio-import/lib/format'

describe('audio-import formatFileSize', () => {
  it('null 返回「—」', () => {
    expect(formatFileSize(null)).toBe('—')
  })

  it('字节 < 1KB 直接带单位', () => {
    expect(formatFileSize(512)).toBe('512 B')
  })

  it('KB 档一位小数', () => {
    expect(formatFileSize(2048)).toBe('2.0 KB')
  })

  it('MB 档一位小数', () => {
    expect(formatFileSize(3_352_064)).toBe('3.2 MB')
  })

  it('GB 档两位小数', () => {
    expect(formatFileSize(3 * 1024 * 1024 * 1024)).toBe('3.00 GB')
  })
})

describe('audio-import formatDuration', () => {
  it('null 返回「—」', () => {
    expect(formatDuration(null)).toBe('—')
  })

  it('42.3 秒 → 00:42（就近取整到秒）', () => {
    expect(formatDuration(42.3)).toBe('00:42')
  })

  it('65.2 秒 → 01:05', () => {
    expect(formatDuration(65.2)).toBe('01:05')
  })

  it('150.8 秒 → 02:31', () => {
    expect(formatDuration(150.8)).toBe('02:31')
  })

  it('0 秒 → 00:00', () => {
    expect(formatDuration(0)).toBe('00:00')
  })
})

describe('audio-import durationBucket', () => {
  it('null 返回 null', () => {
    expect(durationBucket(null)).toBeNull()
  })

  it('≤30 秒为短', () => {
    expect(durationBucket(18.9)).toBe('short')
    expect(durationBucket(30)).toBe('short')
  })

  it('30 秒-5 分钟为中', () => {
    expect(durationBucket(65.2)).toBe('medium')
    expect(durationBucket(300)).toBe('medium')
  })

  it('>5 分钟为长', () => {
    expect(durationBucket(320.1)).toBe('long')
  })
})
