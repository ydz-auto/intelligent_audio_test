/**
 * INT-973：任务列表加载/错误/空态渲染条件锁定。
 *
 * 回归口径：
 * - 空态仅在「非加载、非错误」时渲染（首次进入不闪「没有找到任务」）；
 * - 加载中渲染 loading-state（不渲染空态）；
 * - 错误态由父级错误条承载，此处空态抑制（不落空态误导）。
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import TaskListWithPagination from '../TaskListWithPagination.vue';

// 仅锁定三态渲染条件：TaskCard 渲染细节不在本卡范围，stub 避免深模块图
vi.mock('../TaskCard.vue', () => ({
  default: { template: '<div class="mock-task-card" />' },
}));

const mountList = (props: Record<string, unknown> = {}) =>
  mount(TaskListWithPagination, {
    props: {
      tasks: [],
      showCheckbox: true,
      showConfig: false,
      actions: [],
      totalItems: 0,
      totalPages: 1,
      currentPage: 1,
      pageSize: 10,
      ...props,
    },
  });

describe('TaskListWithPagination 三态渲染（INT-973）', () => {
  it('无数据且非加载/非错误：渲染空态「没有找到任务」', () => {
    const wrapper = mountList();
    expect(wrapper.find('.empty-state').exists()).toBe(true);
    expect(wrapper.text()).toContain('没有找到任务');
    expect(wrapper.find('.loading-state').exists()).toBe(false);
  });

  it('无数据 + isLoading：渲染加载态、抑制空态（修复加载闪空态）', () => {
    const wrapper = mountList({ isLoading: true });
    expect(wrapper.find('.loading-state').exists()).toBe(true);
    expect(wrapper.text()).toContain('加载中...');
    expect(wrapper.find('.empty-state').exists()).toBe(false);
  });

  it('无数据 + hasError：抑制空态（错误由父级错误条承载，不落「没有找到任务」误导）', () => {
    const wrapper = mountList({ hasError: true });
    expect(wrapper.find('.empty-state').exists()).toBe(false);
  });

  it('有数据 + isLoading：渲染任务卡片、不渲染空态/加载态竞争', () => {
    const wrapper = mountList({
      tasks: [{ id: 1, name: 't1', status: 'completed', tags: [] }],
      totalItems: 1,
      isLoading: true,
    });
    expect(wrapper.find('.mock-task-card').exists()).toBe(true);
    expect(wrapper.find('.empty-state').exists()).toBe(false);
    expect(wrapper.find('.loading-state').exists()).toBe(true);
  });
});
