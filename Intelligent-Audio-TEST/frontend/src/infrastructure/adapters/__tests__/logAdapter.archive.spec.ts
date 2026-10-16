/**
 * INT-548 日志归档 adapter 契约测试
 *
 * 覆盖 DTO(snake_case wire / status 端点 camelCase raw dict) → Domain(camelCase)
 * 的显式映射，以及 Domain → DTO（查询参数/请求体）转换。防「复用已有 DTO 后
 * 适配器读不到真实后端字段」的接线回归。
 */
import { describe, it, expect } from 'vitest';
import {
  toLogArchiveStatus,
  toLogArchiveResult,
  toLogArchiveList,
  toLogArchiveQueryDto,
  toLogArchiveRequestDto,
} from '../logAdapter';

describe('toLogArchiveStatus（GET /logs/archive/status 后端 camelCase raw dict）', () => {
  it('映射全部字段为 camelCase Domain', () => {
    const dto = {
      totalLogs: 100,
      hotLogs: 60,
      coldLogs: 40,
      archiveDir: 'oss://archives',
      taskArchives: 3,
      caseArchives: 2,
      otherArchives: 1,
    };
    expect(toLogArchiveStatus(dto)).toEqual({
      totalLogs: 100,
      hotLogs: 60,
      coldLogs: 40,
      archiveDir: 'oss://archives',
      taskArchives: 3,
      caseArchives: 2,
      otherArchives: 1,
    });
  });

  it('空值兜底为 0 / 空串，不产生 undefined', () => {
    const result = toLogArchiveStatus(null);
    expect(result).toEqual({
      totalLogs: 0,
      hotLogs: 0,
      coldLogs: 0,
      archiveDir: '',
      taskArchives: 0,
      caseArchives: 0,
      otherArchives: 0,
    });
  });

  it('缺字段时逐字段兜底', () => {
    const result = toLogArchiveStatus({ totalLogs: 5 });
    expect(result.totalLogs).toBe(5);
    expect(result.taskArchives).toBe(0);
    expect(result.archiveDir).toBe('');
  });
});

describe('toLogArchiveList（GET /logs/archive/logs）', () => {
  it('items 逐条复用 toLog 映射，保留 total/source', () => {
    const dto = {
      items: [
        {
          id: 1,
          time: '2026-10-15 10:00:00',
          level: 'error',
          category: 'system',
          module: 'task',
          source: 'system',
          content: 'boom',
          task_id: 493,
        },
      ],
      total: 1,
      source: 'archive',
    };
    const result = toLogArchiveList(dto as any);
    expect(result.total).toBe(1);
    expect(result.source).toBe('archive');
    expect(result.items[0]).toMatchObject({
      id: 1,
      taskId: 493,
      level: 'error',
      content: 'boom',
    });
  });

  it('null 兜底为空列表', () => {
    const result = toLogArchiveList(null);
    expect(result.items).toEqual([]);
    expect(result.total).toBe(0);
    expect(result.source).toBe('archive');
  });
});

describe('toLogArchiveResult（POST /logs/archive 两形态）', () => {
  it('真实归档形态：snake_case → camelCase', () => {
    const result = toLogArchiveResult({
      archived_count: 30,
      deleted_count: 30,
      archive_file: 'task_case/493/case-1/2026-10-15.json',
      remaining_count: 999,
    });
    expect(result).toEqual({
      message: undefined,
      archivedCount: 30,
      deletedCount: 30,
      archiveFile: 'task_case/493/case-1/2026-10-15.json',
      remainingCount: 999,
      coldLogsCount: undefined,
      cutoffDate: undefined,
    });
  });

  it('dry_run 预览形态：cold_logs_count / cutoff_date', () => {
    const result = toLogArchiveResult({
      message: '将归档 42 条日志（7天前的数据）',
      cold_logs_count: 42,
      cutoff_date: '2026-10-08T00:00:00',
    });
    expect(result.message).toBe('将归档 42 条日志（7天前的数据）');
    expect(result.coldLogsCount).toBe(42);
    expect(result.cutoffDate).toBe('2026-10-08T00:00:00');
    expect(result.archivedCount).toBe(0);
  });
});

describe('Domain → DTO 转换', () => {
  it('toLogArchiveQueryDto：taskId/testCaseId → task_id/test_case_id，忽略空值', () => {
    expect(toLogArchiveQueryDto({ taskId: 493, testCaseId: 'case-1' })).toEqual({
      task_id: 493,
      test_case_id: 'case-1',
    });
    expect(toLogArchiveQueryDto({})).toEqual({});
    expect(toLogArchiveQueryDto({ taskId: undefined, testCaseId: '' })).toEqual({});
  });

  it('toLogArchiveRequestDto：默认 days=7 / dry_run=false', () => {
    expect(toLogArchiveRequestDto({})).toEqual({ days: 7, dry_run: false });
    expect(toLogArchiveRequestDto({ days: 30, dryRun: true })).toEqual({ days: 30, dry_run: true });
  });
});
