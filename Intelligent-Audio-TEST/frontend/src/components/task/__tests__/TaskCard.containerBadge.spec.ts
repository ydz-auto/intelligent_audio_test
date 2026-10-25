/**
 * INT-1832 · 规范 18 §2.1：挑选合并容器行标识 —— TaskCard 单测。
 *
 * 锁定口径：
 * - picked → 名称右侧「结果挑选」徽章（--secondary 系 outline，类 task-merge-type--picked）
 * - whole  → 「整任务合并」（历史形态）
 * - 次行「来源 {n} 个任务 · 结果 {m} 条」（Task.sourceTaskCount / sourceResultCount）
 * - 非容器行（无 mergeType / 无来源计数）零变化：不渲染任何新增元素
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';

import TaskCard from '../TaskCard.vue';

vi.mock('../../../composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({ loadAlgorithms: vi.fn(), getAlgorithmLabel: (v: string) => v }),
}));

const mountTask = (task: Record<string, unknown>) =>
  mount(TaskCard, {
    props: { task, isSelected: false, showCheckbox: false, showConfig: false, actions: [] },
  });

describe('TaskCard 容器行标识（INT-1832）', () => {
  it('picked 容器行：名称右侧「结果挑选」徽章 + 次行来源/结果计数', () => {
    const wrapper = mountTask({
      id: 580,
      name: '小艺拒识挑选合并_2026/10/24',
      status: 'failed',
      executionStatus: 'failed',
      caseCount: 5,
      deviceCount: 1,
      mergeType: 'picked',
      sourceTaskCount: 2,
      sourceResultCount: 5,
    });

    const badge = wrapper.find('.task-merge-type');
    expect(badge.exists()).toBe(true);
    expect(badge.text()).toBe('结果挑选');
    expect(badge.classes()).toContain('task-merge-type--picked');

    const counts = wrapper.find('.task-source-count');
    expect(counts.exists()).toBe(true);
    expect(counts.text()).toContain('来源 2 个任务 · 结果 5 条');
  });

  it('whole 容器行：显示「整任务合并」', () => {
    const wrapper = mountTask({
      id: 501, name: '整任务合并示例', status: 'completed',
      mergeType: 'whole', sourceTaskCount: 3, sourceResultCount: 12, caseCount: 12,
    });

    const badge = wrapper.find('.task-merge-type');
    expect(badge.text()).toBe('整任务合并');
    expect(badge.classes()).toContain('task-merge-type--whole');
    expect(wrapper.find('.task-source-count').text()).toContain('来源 3 个任务 · 结果 12 条');
  });

  it('非容器行：无合并方式徽章、无来源计数（普通任务卡零变化）', () => {
    const wrapper = mountTask({
      id: 42, name: '普通任务', status: 'completed', caseCount: 5, deviceCount: 1,
    });

    expect(wrapper.find('.task-merge-type').exists()).toBe(false);
    expect(wrapper.find('.task-source-count').exists()).toBe(false);
  });
});

/**
 * INT-1836 · 规范 18 §2.1/§5：容器行混态执行徽章（纯前端展示映射）。
 * 0 < failedCases < caseCount → 「部分失败」（warning + 小圆点）；= caseCount → 「已失败」；
 * 非容器行 / 计数缺失 → 沿用原映射零变化。后端字符串仍是 failed。
 */
describe('TaskCard 容器行部分失败徽章（INT-1836）', () => {
  const badgeOf = (wrapper: ReturnType<typeof mountTask>) => wrapper.find('.exec-status-badge');

  it('容器混态 3/5 → 「部分失败」+ warning 类 + 无图标（小圆点由 CSS 伪元素）', () => {
    const wrapper = mountTask({
      id: 657, name: '接线测试_INT1716_AUDIT_A', status: 'failed', executionStatus: 'failed',
      caseCount: 5, failedCases: 3, mergeType: 'picked', sourceTaskCount: 3, sourceResultCount: 4,
    });
    const badge = badgeOf(wrapper);
    expect(badge.text()).toBe('部分失败');
    expect(badge.classes()).toContain('exec-status-badge--partial');
    expect(badge.find('.task-indicator').exists()).toBe(false);
  });

  it('容器全失败 failedCases === caseCount → 「已失败」（沿用现映射配色）', () => {
    const wrapper = mountTask({
      id: 503, name: '单来源容器', status: 'failed', executionStatus: 'failed',
      caseCount: 1, failedCases: 1, mergeType: 'picked', sourceTaskCount: 1, sourceResultCount: 1,
    });
    const badge = badgeOf(wrapper);
    expect(badge.text()).toBe('已失败');
    expect(badge.classes()).not.toContain('exec-status-badge--partial');
  });

  it('containerMixState 边界：failedCases = 0 → 沿用原映射', () => {
    const wrapper = mountTask({
      id: 658, name: '全成功容器', status: 'completed', executionStatus: 'completed',
      caseCount: 4, failedCases: 0, mergeType: 'picked', sourceTaskCount: 1, sourceResultCount: 4,
    });
    expect(badgeOf(wrapper).text()).toBe('已完成');
    expect(badgeOf(wrapper).classes()).not.toContain('exec-status-badge--partial');
  });

  it('非容器行：部分失败计数同样不改变原徽章（普通任务零变化）', () => {
    const wrapper = mountTask({
      id: 42, name: '普通任务', status: 'failed', executionStatus: 'failed',
      caseCount: 5, failedCases: 3,
    });
    expect(badgeOf(wrapper).text()).toBe('失败');
    expect(badgeOf(wrapper).classes()).not.toContain('exec-status-badge--partial');
  });
});
