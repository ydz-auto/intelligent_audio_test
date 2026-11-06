/**
 * 日志导出文件名（application 层；INT-1947 P3）。
 * 旧实现 `new Date().toISOString().slice(0, 10)` 取 UTC 日期，CST 00:00–08:00 导出
 * 落到前一天（实测 2026-10-26 04:0x CST → logs_2026-10-25.txt）。现按本地日期。
 */
import { describe, expect, it } from 'vitest'

import {
  formatLogsExportFilename,
  toLocalDateString,
} from '@/application/logs/log-export-filename'

describe('toLocalDateString', () => {
  it('补零到 YYYY-MM-DD', () => {
    expect(toLocalDateString(new Date(2026, 0, 5, 12, 0, 0))).toBe('2026-01-05')
    expect(toLocalDateString(new Date(2026, 11, 31, 23, 59, 59))).toBe('2026-12-31')
  })

  it('凌晨时刻取本地当日，不落前一天', () => {
    // 本地 2026-10-26 04:05（CST 的 UTC 时刻是 2026-10-25T20:05Z）
    const localEarlyMorning = new Date(2026, 9, 26, 4, 5, 0)
    expect(toLocalDateString(localEarlyMorning)).toBe('2026-10-26')
  })
})

describe('formatLogsExportFilename', () => {
  it('格式 logs_{本地日期}.{format}', () => {
    const date = new Date(2026, 9, 26, 4, 5, 0)
    expect(formatLogsExportFilename(date, 'txt')).toBe('logs_2026-10-26.txt')
    expect(formatLogsExportFilename(date, 'json')).toBe('logs_2026-10-26.json')
    expect(formatLogsExportFilename(date, 'csv')).toBe('logs_2026-10-26.csv')
  })

  it('回归：东八区凌晨旧实现（UTC）会落前一天，新实现不落', () => {
    const localEarlyMorning = new Date(2026, 9, 26, 4, 5, 0)
    // 仅在本地时区快于 UTC 的机器上（如 CST）能复现旧行为
    if (localEarlyMorning.getTimezoneOffset() < 0) {
      expect(localEarlyMorning.toISOString().slice(0, 10)).toBe('2026-10-25')
      expect(formatLogsExportFilename(localEarlyMorning, 'txt')).not.toBe(
        'logs_2026-10-25.txt'
      )
    }
  })
})
