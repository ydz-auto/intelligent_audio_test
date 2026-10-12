import { describe, it, expect } from 'vitest'
import { formatDurationSeconds, formatDurationText } from '../durationFormat'

describe('formatDurationSeconds（与后端 _format_duration 同语义，INT-203）', () => {
  it('<=0 → 0分钟', () => {
    expect(formatDurationSeconds(0)).toBe('0分钟')
    expect(formatDurationSeconds(-5)).toBe('0分钟')
    expect(formatDurationSeconds(NaN)).toBe('0分钟')
  })

  it('<60 → 秒', () => {
    expect(formatDurationSeconds(1)).toBe('1秒')
    expect(formatDurationSeconds(59)).toBe('59秒')
  })

  it('<3600 → 分钟（余秒保留，与后端一致）', () => {
    expect(formatDurationSeconds(60)).toBe('1分钟')
    expect(formatDurationSeconds(90)).toBe('1分钟30秒')
    expect(formatDurationSeconds(300)).toBe('5分钟')
    expect(formatDurationSeconds(3599)).toBe('59分钟59秒')
  })

  it('>=3600 → 小时分钟', () => {
    expect(formatDurationSeconds(3600)).toBe('1小时')
    expect(formatDurationSeconds(3660)).toBe('1小时1分钟')
    expect(formatDurationSeconds(7320)).toBe('2小时2分钟')
  })

  it('小数向下取整', () => {
    expect(formatDurationSeconds(59.9)).toBe('59秒')
    expect(formatDurationSeconds(119.9)).toBe('1分钟59秒')
  })
})

describe('formatDurationText（两通道统一出口）', () => {
  it('数字按秒解释（start 响应契约）', () => {
    expect(formatDurationText(300)).toBe('5分钟')
    expect(formatDurationText(45)).toBe('45秒')
    expect(formatDurationText(0)).toBe('0分钟')
  })

  it('字符串透传（Socket 通道已格式化文本）', () => {
    expect(formatDurationText('5分钟30秒')).toBe('5分钟30秒')
    expect(formatDurationText('1小时')).toBe('1小时')
    expect(formatDurationText(' 2分钟 ')).toBe('2分钟')
  })

  it('空值 → 空串', () => {
    expect(formatDurationText(null)).toBe('')
    expect(formatDurationText(undefined)).toBe('')
  })
})
