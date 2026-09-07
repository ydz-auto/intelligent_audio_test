/**
 * audioUtils.format 单元测试 —— 文件大小/音频时长格式化纯函数
 */
import { describe, it, expect } from 'vitest'
import {
  formatFileSize,
  formatDuration,
  parseDuration,
  formatDurationLong,
  formatAudioData,
} from '../audioUtils.format'

describe('formatFileSize', () => {
  it('字符串输入原样返回', () => {
    expect(formatFileSize('1.2 GB')).toBe('1.2 GB')
  })

  it('字节级大小', () => {
    expect(formatFileSize(0)).toBe('0.00 B')
    expect(formatFileSize(999)).toBe('999.00 B')
  })

  it('KB/MB 换算（基数 1024）', () => {
    expect(formatFileSize(1024)).toBe('1.00 KB')
    expect(formatFileSize(1536)).toBe('1.50 KB')
    expect(formatFileSize(1024 * 1024)).toBe('1.00 MB')
    expect(formatFileSize(1024 * 1024 * 1024)).toBe('1.00 GB')
  })

  it('超大值停在最大单位 TB', () => {
    // 1 PB = 1024 TB，超出单位数组后停在 TB
    expect(formatFileSize(1024 ** 5)).toBe('1024.00 TB')
  })
})

describe('formatDuration', () => {
  it('空值返回 0:00', () => {
    expect(formatDuration(null)).toBe('0:00')
    expect(formatDuration(undefined)).toBe('0:00')
    expect(formatDuration(0)).toBe('0:00')
  })

  it('秒数格式化为 分:秒', () => {
    expect(formatDuration(59)).toBe('0:59')
    expect(formatDuration(59.9)).toBe('0:59')
    expect(formatDuration(65)).toBe('1:05')
    expect(formatDuration(600)).toBe('10:00')
  })
})

describe('parseDuration', () => {
  it('数字直接返回', () => {
    expect(parseDuration(45)).toBe(45)
  })

  it('分:秒 字符串', () => {
    expect(parseDuration('1:30')).toBe(90)
  })

  it('时:分:秒 字符串', () => {
    expect(parseDuration('1:02:03')).toBe(3723)
  })

  it('纯数字字符串', () => {
    expect(parseDuration('90')).toBe(90)
  })

  it('空值/非法值返回 0', () => {
    expect(parseDuration('')).toBe(0)
    expect(parseDuration(null)).toBe(0)
    expect(parseDuration(undefined)).toBe(0)
    expect(parseDuration('abc')).toBe(0)
  })
})

describe('formatDurationLong', () => {
  it('空值返回 0秒', () => {
    expect(formatDurationLong(null)).toBe('0秒')
    expect(formatDurationLong(0)).toBe('0秒')
  })

  it('各时间单位组合', () => {
    expect(formatDurationLong(59)).toBe('59秒')
    expect(formatDurationLong(60)).toBe('1分')
    expect(formatDurationLong(90)).toBe('1分30秒')
    expect(formatDurationLong(3661)).toBe('1时1分1秒')
    expect(formatDurationLong(90061)).toBe('1天1时1分1秒')
  })
})

describe('formatAudioData', () => {
  it('字段名兼容映射（name/filePath/audioType）', () => {
    const result = formatAudioData({
      id: 1,
      name: 'a.wav',
      filePath: '/x/a.wav',
      format: 'wav',
      size: 1024,
      duration: 65,
      audioType: 'noise',
    })
    expect(result.filename).toBe('a.wav')
    expect(result.filepath).toBe('/x/a.wav')
    expect(result.path).toBe('/x/a.wav')
    expect(result.size).toBe('1.00 KB')
    expect(result.duration).toBe('1:05')
    expect(result.type).toBe('noise')
    expect(result.status).toBe('active')
    expect(result.tags).toEqual([])
  })

  it('path 优先于 filePath', () => {
    const result = formatAudioData({
      id: 2,
      name: 'b.wav',
      path: '/p/b.wav',
      filePath: '/fp/b.wav',
    })
    expect(result.filepath).toBe('/p/b.wav')
  })

  it('缺省字段兜底', () => {
    const result = formatAudioData({ id: 3 })
    expect(result.format).toBe('unknown')
    expect(result.type).toBe('dry')
    expect(result.duration).toBe('0:00')
  })

  it('originalFilename 作为 filename 兜底', () => {
    const result = formatAudioData({ id: 4, originalFilename: 'c.wav' })
    expect(result.filename).toBe('c.wav')
  })
})
