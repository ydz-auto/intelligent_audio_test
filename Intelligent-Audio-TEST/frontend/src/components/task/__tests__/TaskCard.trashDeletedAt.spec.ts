/**
 * INT-239 回归锁定：任务回收站卡删除时间必须经卡片内 formatDate 输出
 * `YYYY-MM-DD HH:mm:ss`，不得直显后端 isoformat() 原文（含 T 与微秒），
 * 与报告（HistoryReports.vue）/用例（TestCaseCard.vue）三视图口径一致；
 * NULL / 空（AUTH_MODE=off 或历史数据）→「—」。
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import TaskCard from '../TaskCard.vue';

vi.mock('../TaskCard', () => ({
  useTaskCard: () => ({
    isEditingName: false,
    editedName: '',
    startEditName: vi.fn(),
    saveEditName: vi.fn(),
    cancelEditName: vi.fn(),
    handleBlur: vi.fn(),
    handleKeydown: vi.fn(),
    toggleSelection: vi.fn(),
    handleAction: vi.fn(),
    getDeviceTypesText: vi.fn(() => 'API'),
    getDeviceTypeClass: vi.fn(() => ''),
    getAlgorithmTypeText: vi.fn(() => ''),
    getStatusText: vi.fn(() => '已完成'),
    // INT-301：双状态徽章 helper（mock 最小实现：透传状态值）
    getExecutionBadgeStatus: vi.fn((task: any) => task?.executionStatus || task?.status || 'pending'),
    getExecutionBadgeIcon: vi.fn(() => 'fa-check-circle'),
    getEvaluationStatusText: vi.fn((s: string) => s),
    getEvaluationBadgeIcon: vi.fn(() => 'fa-check-circle'),
    getStepStatusText: vi.fn(() => ''),
    calculateCompletionRate: vi.fn(() => 0),
  }),
}));

const mountTask = (task: Record<string, unknown>) =>
  mount(TaskCard, {
    props: { task, isSelected: false, showCheckbox: true, showConfig: false, actions: [] },
  });

describe('TaskCard 回收站删除时间展示（INT-239）', () => {
  it('deletedAt 为后端 isoformat 原文时经 formatDate 输出 YYYY-MM-DD HH:mm:ss（checkbox 布局）', () => {
    const wrapper = mountTask({
      id: 1,
      name: '已删任务',
      status: 'completed',
      deleted: true,
      deletedAt: '2026-10-12T19:29:00.123456',
      caseCount: 3,
      deviceCount: 2,
    });
    const text = wrapper.text();
    expect(text).toContain('删除时间2026-10-12 19:29:00');
    expect(text).not.toContain('2026-10-12T19:29:00');
  });

  it('deletedAt 为后端 isoformat 原文时经 formatDate 输出 YYYY-MM-DD HH:mm:ss（无 checkbox 布局）', () => {
    const wrapper = mount(TaskCard, {
      props: { task: { id: 1, name: '已删任务', status: 'completed', deleted: true, deletedAt: '2026-10-12T19:29:00.123456' }, isSelected: false, showCheckbox: false, showConfig: false, actions: [] },
    });
    const text = wrapper.text();
    expect(text).toContain('删除时间2026-10-12 19:29:00');
    expect(text).not.toContain('2026-10-12T19:29:00');
  });

  it('deletedAt 缺省（AUTH_MODE=off / 历史数据）显示「—」', () => {
    const wrapper = mountTask({
      id: 2,
      name: '已删任务',
      status: 'completed',
      deleted: true,
      deletedAt: undefined,
    });
    expect(wrapper.text()).toContain('删除时间—');
  });

  it('非回收站条目不渲染删除时间 meta', () => {
    const wrapper = mountTask({
      id: 3,
      name: '正常任务',
      status: 'completed',
      deleted: false,
      createdAt: '2026-10-12 19:29:00',
    });
    expect(wrapper.text()).not.toContain('删除时间');
  });
});
