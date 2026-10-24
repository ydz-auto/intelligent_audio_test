/**
 * 日志选项中文标签回显（interfaces 层；INT-1654 导出摘要不外露后端枚举）。
 * 已知原值 → 工具栏 Select 同款中文标签；未知原值（后端新增枚举 / 算法 id）→ 回落原值。
 */
import { describe, expect, it } from 'vitest'

import {
  LOG_CATEGORY_OPTIONS,
  LOG_MARK_FILTER_OPTIONS,
  LOG_MODULE_OPTIONS,
  getLogOptionLabel,
} from '@/features/logs/constants'

describe('getLogOptionLabel', () => {
  it('分类原值映射中文标签', () => {
    expect(getLogOptionLabel(LOG_CATEGORY_OPTIONS, 'system')).toBe('系统日志')
    expect(getLogOptionLabel(LOG_CATEGORY_OPTIONS, 'test')).toBe('测试日志')
    expect(getLogOptionLabel(LOG_CATEGORY_OPTIONS, 'error')).toBe('错误日志')
  })

  it('模块原值映射中文标签', () => {
    expect(getLogOptionLabel(LOG_MODULE_OPTIONS, 'api')).toBe('API模块')
    expect(getLogOptionLabel(LOG_MODULE_OPTIONS, 'e2e')).toBe('E2E测试')
    expect(getLogOptionLabel(LOG_MODULE_OPTIONS, 'device')).toBe('设备管理')
  })

  it('标记原值映射中文标签', () => {
    expect(getLogOptionLabel(LOG_MARK_FILTER_OPTIONS, 'yellow')).toBe('黄色标记')
    expect(getLogOptionLabel(LOG_MARK_FILTER_OPTIONS, 'red')).toBe('红色标记')
  })

  it('未知原值回落原值，不显示空白', () => {
    expect(getLogOptionLabel(LOG_CATEGORY_OPTIONS, 'unknown')).toBe('unknown')
    expect(getLogOptionLabel(LOG_MARK_FILTER_OPTIONS, 'flagged')).toBe('flagged')
  })
})
