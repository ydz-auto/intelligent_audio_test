/**
 * features/tasks/lib/date-time 纯函数测试（INT-2201：裸 UTC 串按 UTC 解析后转本地展示）。
 * 断言以本地时区换算为基准，不写死 +08:00，避免时区环境差异导致假红。
 */
import { describe, expect, it } from 'vitest'

import {
  formatDateTime,
  formatDateTimeSeconds,
  formatElapsed,
  formatTaskUsedTime,
  parseApiDateTime,
} from '@/features/tasks/lib/date-time'

function expectedLocal(isoUtc: string, withSeconds = false): string {
  const date = new Date(isoUtc)
  const pad = (value: number) => String(value).padStart(2, '0')
  const base = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  return withSeconds ? `${base}:${pad(date.getSeconds())}` : base
}

describe('parseApiDateTime', () => {
  it('无时区后缀的串按 UTC 解释（INT-2201 后端口径）', () => {
    expect(
      parseApiDateTime('2026-10-23T05:11:14.017258')?.toISOString()
    ).toBe('2026-10-23T05:11:14.017Z')
    expect(parseApiDateTime('2026-10-23 05:11:14')?.toISOString()).toBe(
      '2026-10-23T05:11:14.000Z'
    )
  })

  it('带 Z / 偏移量的串保持原语义', () => {
    expect(parseApiDateTime('2026-10-23T05:11:14Z')?.toISOString()).toBe(
      '2026-10-23T05:11:14.000Z'
    )
    expect(parseApiDateTime('2026-10-23T13:11:14+08:00')?.toISOString()).toBe(
      '2026-10-23T05:11:14.000Z'
    )
  })

  it('空值 / 不可解析返回 null', () => {
    expect(parseApiDateTime(null)).toBeNull()
    expect(parseApiDateTime(undefined)).toBeNull()
    expect(parseApiDateTime('')).toBeNull()
    expect(parseApiDateTime('   ')).toBeNull()
    expect(parseApiDateTime('not-a-date')).toBeNull()
  })
})

describe('formatDateTime / formatDateTimeSeconds', () => {
  it('裸 UTC 串转本地时区展示，不再是 UTC 原样切片', () => {
    expect(formatDateTime('2026-10-23T05:11:14.017258')).toBe(
      expectedLocal('2026-10-23T05:11:14.017Z')
    )
    // 与显式 Z 的同一时刻输出一致（口径统一）
    expect(formatDateTime('2026-10-23T05:11:14.017258')).toBe(
      formatDateTime('2026-10-23T05:11:14.017Z')
    )
  })

  it('带秒版本输出 YYYY-MM-DD HH:mm:ss', () => {
    expect(formatDateTimeSeconds('2026-10-31T03:49:37')).toBe(
      expectedLocal('2026-10-31T03:49:37Z', true)
    )
  })

  it('空值 / 不可解析 → —', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined)).toBe('—')
    expect(formatDateTime('oops')).toBe('—')
    expect(formatDateTimeSeconds(null)).toBe('—')
  })
})

describe('formatElapsed', () => {
  it('按量级给出秒 / 分钟 / 小时 / 天', () => {
    expect(formatElapsed(null)).toBe('—')
    expect(formatElapsed(5_000)).toBe('5 秒')
    expect(formatElapsed(90_000)).toBe('1 分钟')
    expect(formatElapsed(120_000)).toBe('2 分钟')
    expect(formatElapsed(60_000)).toBe('1 分钟')
    expect(formatElapsed(3_600_000)).toBe('1 小时')
    expect(formatElapsed(4_320_000)).toBe('1 小时 12 分钟')
    expect(formatElapsed(90_000_000)).toBe('1 天 1 小时')
  })
})

describe('formatTaskUsedTime', () => {
  const base = {
    created_at: '2026-10-23T04:55:00',
    started_at: '2026-10-23T05:00:00',
    completed_at: '2026-10-23T05:01:00',
    execution_status: 'completed' as const,
  }

  it('以起止时间推算（不采用后端 used_time 异常值）', () => {
    expect(formatTaskUsedTime(base)).toBe('1 分钟')
  })

  it('进行中按当前时间实时推算', () => {
    expect(
      formatTaskUsedTime(
        { ...base, completed_at: null, execution_status: 'running' },
        new Date('2026-10-23T05:02:00Z')
      )
    ).toBe('2 分钟')
  })

  it('无有效开始时间 → —', () => {
    expect(formatTaskUsedTime({ ...base, started_at: null })).toBe('—')
  })

  it('已结束但无完成时间 → —（不拿当前时间冒充）', () => {
    expect(
      formatTaskUsedTime({ ...base, completed_at: null })
    ).toBe('—')
  })

  // INT-2210：started_at 早于 created_at 的脏数据（真实库 173/408 条）视为无有效开始时间。
  it('started_at 早于 created_at 16 小时（真实库任务 789）→ —', () => {
    expect(
      formatTaskUsedTime({
        created_at: '2026-10-31T01:08:22',
        started_at: '2026-10-30T09:08:32',
        completed_at: '2026-10-31T01:20:22',
        execution_status: 'completed',
      })
    ).toBe('—')
  })

  it('started_at 早于 created_at 8 小时 → —', () => {
    expect(
      formatTaskUsedTime({
        created_at: '2026-10-31T04:05:08',
        started_at: '2026-10-30T20:05:08',
        completed_at: '2026-10-31T04:20:08',
        execution_status: 'completed',
      })
    ).toBe('—')
  })

  it('脏数据 + 进行中同样 → —（不按 now 推算出一个大数）', () => {
    expect(
      formatTaskUsedTime(
        {
          ...base,
          created_at: '2026-10-23T05:00:00',
          started_at: '2026-10-22T13:00:00',
          completed_at: null,
          execution_status: 'running',
        },
        new Date('2026-10-23T05:02:00Z')
      )
    ).toBe('—')
  })

  it('started_at 与 created_at 相同视为有效（守卫只挡严格早于）', () => {
    expect(
      formatTaskUsedTime({
        ...base,
        created_at: '2026-10-23T05:00:00',
        started_at: '2026-10-23T05:00:00',
      })
    ).toBe('1 分钟')
  })

  it('created_at 缺失时不启用守卫（无可比基准，沿用原口径）', () => {
    expect(formatTaskUsedTime({ ...base, created_at: null })).toBe('1 分钟')
    expect(formatTaskUsedTime({ ...base, created_at: 'oops' })).toBe('1 分钟')
  })
})
