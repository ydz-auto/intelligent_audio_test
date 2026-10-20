/**
 * INT-283：PublishedTasks 执行记录/来源任务行恢复「详情/报告」跳转入口（对齐基线 V9.7.10）。
 *
 * 锁定口径（本用例，防回归）：
 * 1. 执行记录行尾渲染 详情+报告 按钮；点击 emit task-action（view-details → 宿主
 *    handleTaskAction 打开任务详情模态；view-report → /report/:id），载荷携带
 *    exec.taskId / exec.taskName；
 * 2. 存量版本（hasTaskSnapshot=false）来源任务行尾渲染 详情+报告 按钮，载荷携带
 *    sourceTaskId / sourceTaskName；
 * 3. 冻结版本（hasTaskSnapshot=true）不渲染存量行内活跳按钮——详情入口由「查看冻结任务
 *    详情」承载，报告入口由「冻结报告」区块承载（INT-303 冻结语义，防止双入口歧义）。
 */
import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import type { PublishedTaskItem } from '../../../domain/model/publishedTask';

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: { getAll: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 100, pages: 0 })) },
}));

vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({ show: vi.fn(), error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() }),
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: vi.fn(), close: vi.fn(), closeAll: vi.fn(), getActiveModals: () => [], updateModalProps: vi.fn(), registerModal: vi.fn() }),
  getModalManager: () => ({ open: vi.fn(), close: vi.fn(), closeAll: vi.fn(), getActiveModals: () => [], updateModalProps: vi.fn(), registerModal: vi.fn() }),
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm', DELETE_CONFIRM: 'deleteConfirm' },
}));

import PublishedTaskPanel from '../PublishedTaskPanel.vue';

function ptItem(overrides: Partial<PublishedTaskItem> = {}): PublishedTaskItem {
  return {
    id: 101,
    sourceTaskId: 9,
    name: '回归任务A',
    description: '',
    status: 'published',
    benchmark: false,
    version: 3,
    isCurrent: true,
    versionCount: 1,
    publishedBy: 'tester',
    publishedAt: '2026-10-13T12:00:00Z',
    ...overrides,
  } as PublishedTaskItem;
}

function fakePt(detail: any) {
  return {
    items: [ptItem()],
    detail: null as any,
    total: 1,
    page: 1,
    perPage: 10,
    pages: 1,
    loading: false,
    actionLoading: false,
    filters: {
      status: 'all', keyword: '', type: 'all', algorithmType: 'all',
      timeRange: 'all', customRange: { start: '', end: '' },
      sort: { field: 'publishedAt', order: 'desc' as const },
    },
    statusOptions: [],
    typeOptions: [],
    fetchList: vi.fn(async () => {}),
    fetchDetail: vi.fn(async () => detail),
    publish: vi.fn(),
    execute: vi.fn(),
    createVersion: vi.fn(),
    archive: vi.fn(),
    rename: vi.fn(),
    setPage: vi.fn(),
    toggleSort: vi.fn(),
  } as any;
}

/** 存量版本详情（hasTaskSnapshot=false：来源任务 + 执行记录均走行内按钮） */
const legacyDetail = {
  id: 101, name: '回归任务A', status: 'published', version: 3, isCurrent: true, benchmark: false,
  snapshotConfig: {}, hasTaskSnapshot: false, hasReportSnapshot: false,
  sourceTaskId: 9, sourceTaskName: '来源任务A', sourceTaskStatus: 'completed',
  sourceTaskTotalCases: 3, sourceTaskCompletedCases: 3,
  versions: [],
  executionHistory: [
    { taskId: 201, taskName: '执行任务A', version: 3, status: 'completed', totalCases: 5, completedCases: 5, createdAt: '2026-10-14T10:00:00Z' },
  ],
};

/** 冻结版本详情（hasTaskSnapshot=true：来源任务按冻结数据渲染） */
const frozenDetail = {
  ...legacyDetail,
  hasTaskSnapshot: true,
  snapshotConfig: {
    sourceTaskId: 9,
    taskSnapshot: {
      task: { id: 9, name: '冻结任务A', algorithmType: 'APITest', tags: ['回归'] },
      cases: [{ id: 1 }],
    },
  },
};

async function mountPanel(detail: any) {
  const { createPinia, setActivePinia } = await import('pinia');
  const { useAuthStore } = await import('../../../store/authStore');
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: 1, username: 'u', roleId: null, roleName: '', permissions: ['*'] });

  const wrapper = mount(PublishedTaskPanel, {
    props: { pt: fakePt(detail) },
    attachTo: document.body,
    global: {
      stubs: {
        PublishTaskModal: { template: '<div class="publish-task-modal-stub" />', props: ['tasks', 'submitting', 'presetSourceTaskId'] },
        ReportSnapshotModal: { template: '<div class="report-snapshot-modal-stub" />' },
        TaskSnapshotModal: { template: '<div class="task-snapshot-modal-stub" />' },
        PublishedTaskNameModal: { template: '<div class="published-task-name-modal-stub" />' },
      },
    },
  });
  await flushPromises();
  // 展开版本详情
  const versionBtn = wrapper.findAll('.pt-card-actions button').find((b: any) => b.text().includes('版本'))!;
  await versionBtn.trigger('click');
  await flushPromises();
  return wrapper;
}

function sectionByTitle(w: any, keyword: string) {
  return w.findAll('.pt-detail-section').find((s: any) => s.find('.pt-detail-title').text().includes(keyword))!;
}

describe('INT-283 执行记录/来源任务行内详情/报告跳转入口', () => {
  it('执行记录行尾渲染详情/报告按钮，点击 emit task-action（载荷带 exec.taskId/taskName）', async () => {
    const w = await mountPanel(legacyDetail);
    const execSection = sectionByTitle(w, '执行记录');
    const execRow = execSection.find('.pt-detail-row');
    const detailBtn = execRow.findAll('button').find((b: any) => b.text().includes('详情'))!;
    const reportBtn = execRow.findAll('button').find((b: any) => b.text().includes('报告'))!;
    expect(detailBtn.exists()).toBe(true);
    expect(reportBtn.exists()).toBe(true);

    await detailBtn.trigger('click');
    expect(w.emitted('task-action')!.at(-1)).toEqual([{ action: { id: 'view-details' }, task: { id: 201 } }]);

    await reportBtn.trigger('click');
    expect(w.emitted('task-action')!.at(-1)).toEqual([{ action: { id: 'view-report' }, task: { id: 201, name: '执行任务A' } }]);
    w.unmount();
  });

  it('存量版本来源任务行尾渲染详情/报告按钮，点击 emit task-action（载荷带 sourceTaskId/sourceTaskName）', async () => {
    const w = await mountPanel(legacyDetail);
    const srcSection = sectionByTitle(w, '来源任务');
    const srcRow = srcSection.find('.pt-detail-row');
    const detailBtn = srcRow.findAll('button').find((b: any) => b.text().includes('详情'))!;
    const reportBtn = srcRow.findAll('button').find((b: any) => b.text().includes('报告'))!;
    expect(detailBtn.exists()).toBe(true);
    expect(reportBtn.exists()).toBe(true);

    await detailBtn.trigger('click');
    expect(w.emitted('task-action')!.at(-1)).toEqual([{ action: { id: 'view-details' }, task: { id: 9 } }]);

    await reportBtn.trigger('click');
    expect(w.emitted('task-action')!.at(-1)).toEqual([{ action: { id: 'view-report' }, task: { id: 9, name: '来源任务A' } }]);
    w.unmount();
  });

  it('冻结版本（hasTaskSnapshot=true）不渲染存量行内活跳按钮，仍保留「查看冻结任务详情」', async () => {
    const w = await mountPanel(frozenDetail);
    // 冻结语义：区块标题为「任务详情（发布时冻结 · 不可变）」
    const srcSection = sectionByTitle(w, '任务详情');
    // 详情入口由冻结详情按钮承载，不出现存量行内 详情/报告 活跳
    expect(srcSection.text()).not.toContain('报告');
    expect(srcSection.findAll('button').some((b: any) => b.text().includes('查看冻结任务详情'))).toBe(true);
    w.unmount();
  });
});
