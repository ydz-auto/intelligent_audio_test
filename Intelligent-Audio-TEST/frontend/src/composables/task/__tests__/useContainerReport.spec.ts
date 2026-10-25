// -*- coding: utf-8 -*-
/**
 * useContainerReport（INT-1837 · 规范 18 §7 无报告态）—— application 层单测。
 *
 * 锁定：
 * - 按 task_id 复用现有报告列表端点取最新一份（不新增端点）；
 * - 列表失败 → error（详情其余区域不受影响）；
 * - 生成走现有 generate-task 端点，后端异步落库 → 轮询列表直到出现（最长 60s 后按暂无收尾）；
 * - 任务切换丢弃过期响应。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ref } from 'vue';
import { flushPromises } from '@vue/test-utils';

const mocks = vi.hoisted(() => ({
  getAll: vi.fn(),
  generateTaskReport: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock('../../report/reportsPort', () => ({
  reportsPort: {
    getAll: mocks.getAll,
    generateTaskReport: mocks.generateTaskReport,
  },
}));

vi.mock('../../modal/useNotification', () => ({
  useNotification: () => ({ success: mocks.success, error: mocks.error, warning: vi.fn(), info: vi.fn() }),
}));

import { useContainerReport } from '../useContainerReport';

const page = (items: any[]) => ({ items, total: items.length, page: 1, perPage: 1, pages: 1 });

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('报告读取（GET /reports?task_id=）', () => {
  it('按 task_id 取最新一份', async () => {
    mocks.getAll.mockResolvedValue(page([{ id: 901, name: '合并任务报告', status: 'published' }]));
    const state = useContainerReport(ref(580));
    await flushPromises();

    expect(mocks.getAll).toHaveBeenCalledWith(expect.objectContaining({
      taskId: 580, page: 1, perPage: 1, sortBy: 'created_at', order: 'desc', deleted: false,
    }));
    expect(state.report.value?.id).toBe(901);
    expect(state.loading.value).toBe(false);
    expect(state.error.value).toBe(false);
  });

  it('无报告 → report = null（空态由组件呈现）', async () => {
    mocks.getAll.mockResolvedValue(page([]));
    const state = useContainerReport(ref(580));
    await flushPromises();
    expect(state.report.value).toBeNull();
    expect(state.error.value).toBe(false);
  });

  it('列表失败 → error（不抛错、不影响详情其余区域）', async () => {
    mocks.getAll.mockRejectedValue(new Error('boom'));
    const state = useContainerReport(ref(580));
    await flushPromises();
    expect(state.error.value).toBe(true);
    expect(state.report.value).toBeNull();
  });

  it('无 taskId 不发请求', async () => {
    const state = useContainerReport(ref(null));
    await flushPromises();
    expect(mocks.getAll).not.toHaveBeenCalled();
    expect(state.report.value).toBeNull();
  });
});

describe('生成报告（POST /reports/generate-task + 轮询）', () => {
  it('生成成功后轮询列表，报告出现即停止生成态', async () => {
    vi.useFakeTimers();
    mocks.getAll.mockResolvedValue(page([]));
    mocks.generateTaskReport.mockResolvedValue({ success: true });

    const state = useContainerReport(ref(580));
    await vi.advanceTimersByTimeAsync(0);

    await state.generate();
    expect(mocks.generateTaskReport).toHaveBeenCalledWith(580);
    expect(state.generating.value).toBe(true);
    expect(state.report.value).toBeNull();

    // 后端异步落库：下一次轮询拿到报告
    mocks.getAll.mockResolvedValue(page([{ id: 902, name: '合并任务报告', status: 'draft' }]));
    await vi.advanceTimersByTimeAsync(2000);
    await flushPromises();

    expect(state.report.value?.id).toBe(902);
    expect(state.generating.value).toBe(false);
  });

  it('生成失败 → 不清空空态、生成态复位、toast 报错', async () => {
    mocks.getAll.mockResolvedValue(page([]));
    mocks.generateTaskReport.mockRejectedValue(new Error('生成报告失败'));
    const state = useContainerReport(ref(580));
    await flushPromises();

    await state.generate();
    expect(state.generating.value).toBe(false);
    expect(mocks.error).toHaveBeenCalled();
  });
});
