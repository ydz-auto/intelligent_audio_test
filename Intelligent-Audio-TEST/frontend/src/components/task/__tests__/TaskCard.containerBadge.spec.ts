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
