/**
 * INT-806 日志 user_id 查询参数接线测试
 *
 * 旧 Vue /logs 高级筛选「用户ID」字段（domain userId，camelCase）此前
 * 静默失效——toLogQueryDto 未映射。本卡补 `userId → user_id`（后端
 * LogListQuery.user_id 按 created_by_user_id 过滤）。
 */
import { describe, it, expect } from 'vitest';
import { toLogQueryDto } from '../logAdapter';

describe('toLogQueryDto（INT-806 user_id 过滤）', () => {
  it('userId → user_id 查询参数，字符串原样', () => {
    expect(toLogQueryDto({ userId: '368' })).toEqual({ user_id: '368' });
  });

  it('userId 为空串 / undefined 时不带 user_id（不过滤）', () => {
    expect(toLogQueryDto({ userId: '' })).toEqual({});
    expect(toLogQueryDto({})).toEqual({});
    expect(toLogQueryDto({ userId: undefined })).toEqual({});
  });

  it('与其他查询条件共存时一并输出', () => {
    const result = toLogQueryDto({
      userId: '368',
      page: 1,
      perPage: 50,
      keyword: 'timeout',
    });
    expect(result).toEqual({
      user_id: '368',
      page: 1,
      per_page: 50,
      keyword: 'timeout',
    });
  });
});
