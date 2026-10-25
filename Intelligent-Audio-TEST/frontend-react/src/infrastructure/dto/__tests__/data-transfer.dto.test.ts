/**
 * 任务数据搬运 DTO 映射测试（INT-1765 增量回导）：
 * 锁定 D3（INT-1761）实际契约——1.1 增量包经整包预检端点返回后，
 * 源任务取 manifest.tasks[0]、覆盖行数取 stats.tableRows 实际行数；
 * 增量导入回执为 camelCase（taskId/mergedDimensions/…/batchId/rollbackAvailable）；
 * 进度 step 新增 merging_dimensions / replacing_reports 两个增量段。
 */
import { describe, expect, it } from 'vitest'

import {
  toIncrementalImportPreview,
  toIncrementalImportResult,
  toImportProgress,
  type TaskIncrementalImportResultDto,
  type TaskImportPreviewDto,
} from '@/infrastructure/dto/data-transfer.dto'

function makePreviewDto(overrides: Partial<TaskImportPreviewDto> = {}): TaskImportPreviewDto {
  return {
    manifest: {
      version: '1.1',
      exportedAt: '2026-10-25T12:00:00+08:00',
      serverInfo: { source: 'B-host' },
      tasks: [
        { id: 12, name: '任务A', type: '', status: 'completed', resultCount: 5 },
      ],
      options: { include: ['dimensions', 'reports'] },
    },
    stats: {
      taskCount: 1,
      resultCount: 0,
      dimensionCount: 40,
      reportCount: 1,
      fileCount: 0,
      totalFileSize: 0,
      tableRows: { test_result_dimensions: 38, test_reports: 1 },
    },
    conflicts: [],
    warnings: ['任务名与包内不一致'],
    ...overrides,
  }
}

describe('data-transfer.dto 增量回导', () => {
  it('整包预检响应 → IncrementalImportPreview（源任务取 tasks[0]，行数取 tableRows）', () => {
    const preview = toIncrementalImportPreview(makePreviewDto())
    expect(preview).toEqual({
      version: '1.1',
      exportedAt: '2026-10-25T12:00:00+08:00',
      source: 'B-host',
      sourceTaskId: 12,
      sourceTaskName: '任务A',
      sourceTaskStatus: 'completed',
      sourceTaskResultCount: 5,
      dimensionCount: 38,
      reportCount: 1,
      warnings: ['任务名与包内不一致'],
    })
  })

  it('tableRows 缺失时回落 manifest stats 的维度/报告数', () => {
    const dto = makePreviewDto({
      stats: { dimensionCount: 7, reportCount: 2 },
    })
    const preview = toIncrementalImportPreview(dto)
    expect(preview.dimensionCount).toBe(7)
    expect(preview.reportCount).toBe(2)
  })

  it('空 tasks[] → 源任务 id 为 null（调用方据此拒绝非增量包）', () => {
    const dto = makePreviewDto()
    dto.manifest.tasks = []
    const preview = toIncrementalImportPreview(dto)
    expect(preview.sourceTaskId).toBeNull()
    expect(preview.sourceTaskName).toBe('')
  })

  it('增量导入回执 → Domain（逐字段映射，不 spread 透传）', () => {
    const dto: TaskIncrementalImportResultDto = {
      taskId: 12,
      mergedDimensions: 38,
      deletedDimensions: 36,
      skippedDimensions: [601, 602],
      insertedReports: 1,
      replacedReportId: 9001,
      targetResolvedBy: 'source_map',
      warnings: ['跳过 1 行未命中维度映射的评分'],
      batchId: 'b0a1c2d3e4f5',
      rollbackAvailable: true,
    }
    const result = toIncrementalImportResult(dto)
    expect(result).toEqual({
      taskId: 12,
      mergedDimensions: 38,
      deletedDimensions: 36,
      skippedDimensions: [601, 602],
      insertedReports: 1,
      replacedReportId: 9001,
      targetResolvedBy: 'source_map',
      warnings: ['跳过 1 行未命中维度映射的评分'],
      batchId: 'b0a1c2d3e4f5',
      rollbackAvailable: true,
    })
  })

  it('回执缺字段 → 安全默认（0 / null / 空数组 / false）', () => {
    const result = toIncrementalImportResult({})
    expect(result).toEqual({
      taskId: 0,
      mergedDimensions: 0,
      deletedDimensions: 0,
      skippedDimensions: [],
      insertedReports: 0,
      replacedReportId: null,
      targetResolvedBy: '',
      warnings: [],
      batchId: '',
      rollbackAvailable: false,
    })
  })

  it('进度快照支持增量两段 step（不被回落成 parsing）', () => {
    const merging = toImportProgress({
      step: 'merging_dimensions',
      percentage: 40,
      message: '合并维度评分',
      batch_id: 'b1',
    })
    expect(merging?.step).toBe('merging_dimensions')
    expect(merging?.batchId).toBe('b1')
    const replacing = toImportProgress({ step: 'replacing_reports', percentage: 80 })
    expect(replacing?.step).toBe('replacing_reports')
    expect(toImportProgress(null)).toBeNull()
  })
})
