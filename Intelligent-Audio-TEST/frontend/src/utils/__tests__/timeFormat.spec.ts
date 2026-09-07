/**
 * timeFormat 单元测试 —— 日志时间格式化
 * 断言方式与运行环境 locale 无关（仅比较模式差异与边界行为）
 */
import { describe, it, expect } from 'vitest'
import { formatLogTime } from '../timeFormat'

describe('formatLogTime', () => {
  it('空值返回空字符串', () => {
    expect(formatLogTime(undefined, 'time')).toBe('')
    expect(formatLogTime(null, 'datetime')).toBe('')
  })

  it('非法日期按原字符串返回', () => {
    expect(formatLogTime('not-a-date', 'time')).toBe('not-a-date')
  })

  it('time 模式不包含年份', () => {
    const result = formatLogTime('2024-01-15T08:30:00', 'time')
    expect(typeof result).toBe('string')
    expect(result).not.toContain('2024')
  })

  it('datetime 模式包含年份', () => {
    const result = formatLogTime('2024-01-15T08:30:00', 'datetime')
    expect(typeof result).toBe('string')
    expect(result).toContain('2024')
    expect(result).toContain('15')
  })

  it('合法日期两种模式产出不同文本', () => {
    const time = formatLogTime('2024-01-15T08:30:00', 'time')
    const datetime = formatLogTime('2024-01-15T08:30:00', 'datetime')
    expect(time).not.toBe(datetime)
  })
})