/**
 * Review Adapter —— DTO(snake_case) → Domain(camelCase) 转换单测。
 * INT-797：报告侧人工审核/AI 复核 基础设施转换口径。
 */
import { describe, it, expect } from 'vitest';
import { toReviewHistoryDomain, toAiReviewRecord } from '../reviewAdapter';

describe('toReviewHistoryDomain', () => {
  it('snake_case 复核留痕行 → camelCase 领域对象', () => {
    const raw = {
      id: 12,
      result_id: 340,
      task_id: 407,
      test_case_id: 'tc-1',
      field_name: 'evaluation_status',
      old_value: 'failed',
      new_value: 'completed',
      comment: '接线测试：复核通过',
      created_by_user_id: 42,
      created_at: '2026-10-18T09:00:00',
    };
    const d = toReviewHistoryDomain(raw);
    expect(d.id).toBe(12);
    expect(d.resultId).toBe(340);
    expect(d.taskId).toBe(407);
    expect(d.testCaseId).toBe('tc-1');
    expect(d.fieldName).toBe('evaluation_status');
    expect(d.oldValue).toBe('failed');
    expect(d.newValue).toBe('completed');
    expect(d.comment).toBe('接线测试：复核通过');
    expect(d.createdByUserId).toBe(42);
    expect(d.createdAt).toBe('2026-10-18T09:00:00');
  });

  it('缺省/空值容忍（old_value/created_at 缺省为 null，id 缺省为 undefined）', () => {
    const d = toReviewHistoryDomain({ result_id: 7, new_value: 'skipped' });
    expect(d.oldValue).toBeNull();
    expect(d.newValue).toBe('skipped');
    expect(d.id).toBeUndefined();
    expect(d.createdAt).toBeNull();
  });
});

describe('toAiReviewRecord', () => {
  it('verdict/confidence/status → 领域对象（高置信度映射「高」，后端 adopted/rejected 0/1 → boolean）', () => {
    const r = toAiReviewRecord({
      id: 1,
      result_id: 9,
      task_id: 407,
      test_case_id: 'tc-9',
      dimension_id: 12,
      status: 'completed',
      verdict: 'passed',
      confidence: 0.9,
      reasoning: '大模型复核通过',
      adopted: 1,
      rejected: 0,
      created_at: '2026-10-18T10:00:00',
    });
    expect(r.verdict).toBe('passed');
    expect(r.status).toBe('completed');
    expect(r.confidence?.value).toBe(0.9);
    expect(r.confidence?.label).toBe('高');
    expect(r.reasoning).toBe('大模型复核通过');
    expect(r.testCaseId).toBe('tc-9');
    expect(r.dimensionId).toBe(12);
    expect(r.adopted).toBe(true);
    expect(r.rejected).toBe(false);
  });

  it('运行中记录：verdict/confidence 未回写 → null；status 原样保留', () => {
    const r = toAiReviewRecord({ id: 2, result_id: 9, task_id: 407, status: 'running' });
    expect(r.status).toBe('running');
    expect(r.verdict).toBeNull();
    expect(r.confidence).toBeNull();
    expect(r.adopted).toBe(false);
  });

  it('verdict 仅 passed/failed/uncertain 原样保留，其余为 null；置信度中档映射「中」', () => {
    expect(toAiReviewRecord({ verdict: 'failed', confidence: 0.4, status: 'completed' }).verdict).toBe('failed');
    expect(toAiReviewRecord({ verdict: 'uncertain', confidence: 0.5, status: 'completed' }).verdict).toBe('uncertain');
    expect(toAiReviewRecord({ verdict: 'weird', confidence: 0.6, status: 'completed' }).verdict).toBeNull();
    expect(toAiReviewRecord({ verdict: 'passed', confidence: 0.6, status: 'completed' }).confidence?.label).toBe('中');
  });

  it('status 未知值兜底 pending', () => {
    expect(toAiReviewRecord({ status: 'whatever' }).status).toBe('pending');
  });
});
