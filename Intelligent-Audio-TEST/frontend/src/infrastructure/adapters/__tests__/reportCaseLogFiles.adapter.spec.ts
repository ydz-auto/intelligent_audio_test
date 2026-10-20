/**
 * 报告用例日志文件列表 Adapter 契约测试（INT-1071）
 * 覆盖：ReportCaseLogFilesDto(snake_case) → CaseLogFile[](camelCase) 映射，
 * 含 updated_at 缺省省略与 items 非数组回退空列表。
 */
import { describe, it, expect } from 'vitest'
import { toCaseLogFiles } from '../report.mapping'
import type { ReportCaseLogFilesDto } from '../../dto/reportDto'

describe('toCaseLogFiles', () => {
  it('转换 items 元素字段名（name/size 保留，updated_at → updatedAt）', () => {
    const dto: ReportCaseLogFilesDto = {
      items: [
        { name: 'api/result_data.json', size: 2019, updated_at: '2026-10-20T12:00:00Z' },
        { name: 'business_logs/common/shared/execution.task_service.log', size: 59248 },
      ],
    }
    expect(toCaseLogFiles(dto)).toEqual([
      { name: 'api/result_data.json', size: 2019, updatedAt: '2026-10-20T12:00:00Z' },
      { name: 'business_logs/common/shared/execution.task_service.log', size: 59248 },
    ])
  })

  it('updated_at 缺省/为 null 时省略 updatedAt（后端无 mtime 省略）', () => {
    const dto: ReportCaseLogFilesDto = {
      items: [
        { name: 'a.log', size: 10, updated_at: null },
        { name: 'b.log', size: 20 },
      ],
    }
    const result = toCaseLogFiles(dto)
    expect(result[0]).toEqual({ name: 'a.log', size: 10 })
    expect(result[1]).toEqual({ name: 'b.log', size: 20 })
    expect('updatedAt' in result[0]).toBe(false)
  })

  it('items 非数组 / 缺省时回退空列表', () => {
    expect(toCaseLogFiles({ items: [] as never })).toEqual([])
    expect(toCaseLogFiles({} as ReportCaseLogFilesDto)).toEqual([])
  })
})
