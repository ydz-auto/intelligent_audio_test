/**
 * INT-769 报告类型/状态元信息兜底测试：未知/遗留 report.type / report.status
 * 不再读取 undefined（整页 500），回退「未知报告类型」「未知状态」（对齐旧 Vue
 * ReportHeaderComponent typeMap || '未知报告类型'、statusMap || '未知状态'）。
 */
import { describe, expect, it } from 'vitest'

import {
  getReportStatusMeta,
  getReportTypeMeta,
  REPORT_STATUS_META,
  REPORT_TYPE_META,
} from '@/features/reports/constants'

describe('getReportTypeMeta 兜底', () => {
  it('已知类型返回原元信息', () => {
    for (const [type, meta] of Object.entries(REPORT_TYPE_META)) {
      expect(getReportTypeMeta(type)).toEqual(meta)
    }
  })

  it('未知/遗留类型（e2e / standard / detailed）不抛错，回退「未知报告类型」', () => {
    for (const type of ['e2e', 'standard', 'detailed', 'historical']) {
      const meta = getReportTypeMeta(type)
      expect(meta.label).toBe('未知报告类型')
      expect(meta.variant).toBe('neutral')
    }
  })

  it('缺省类型回退「未知报告类型」', () => {
    expect(getReportTypeMeta(undefined).label).toBe('未知报告类型')
  })
})

describe('getReportStatusMeta 兜底', () => {
  it('已知状态返回原元信息', () => {
    for (const [status, meta] of Object.entries(REPORT_STATUS_META)) {
      expect(getReportStatusMeta(status)).toEqual(meta)
    }
  })

  it('未知状态不抛错，回退「未知状态」', () => {
    const meta = getReportStatusMeta('archived' as never)
    expect(meta.label).toBe('未知状态')
    expect(meta.variant).toBe('neutral')
  })

  it('缺省状态回退「未知状态」', () => {
    expect(getReportStatusMeta(undefined).label).toBe('未知状态')
  })
})
