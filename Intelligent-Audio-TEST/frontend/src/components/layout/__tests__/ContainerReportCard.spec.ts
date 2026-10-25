// -*- coding: utf-8 -*-
/**
 * ContainerReportCard 报告区回归（INT-1837 · 规范 18 §7「无报告」/ §8.2 / §11 文案）。
 *
 * 锁死：
 * - 无报告：Empty +「该合并任务暂无报告」/「合并任务无执行过程，报告需手动生成」+「生成报告」；
 * - 已有报告：名称 + 状态 + ID +「查看报告」（跳 /report/:id）；
 * - 加载中：骨架（不闪「暂无报告」）；列表失败：Empty +「重试」；
 * - 生成中：不谎报「暂无报告」；
 * - 权限：report:create 无 → 不渲染「生成报告」；report:read 无 → 不渲染「查看报告」。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref } from 'vue';

const mocks = vi.hoisted(() => ({
  hasPermission: vi.fn((_point?: string): boolean => true),
  push: vi.fn(),
  retry: vi.fn(),
  generate: vi.fn(),
  state: {
    report: { value: null as any },
    loading: { value: false },
    error: { value: false },
    generating: { value: false },
  },
}));

vi.mock('../../../composables/task/useContainerReport', () => ({
  useContainerReport: () => ({
    report: mocks.state.report,
    loading: mocks.state.loading,
    error: mocks.state.error,
    generating: mocks.state.generating,
    retry: mocks.retry,
    generate: mocks.generate,
  }),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: mocks.hasPermission }),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push }),
}));

import ContainerReportCard from '../ContainerReportCard.vue';

function mountCard() {
  return mount(ContainerReportCard, { props: { taskId: 580 } });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.hasPermission.mockReturnValue(true);
  mocks.state.report = ref(null);
  mocks.state.loading = ref(false);
  mocks.state.error = ref(false);
  mocks.state.generating = ref(false);
});

describe('无报告（§7）', () => {
  it('Empty 两行文案 +「生成报告」，点击触发生成', async () => {
    const wrapper = mountCard();
    expect(wrapper.text()).toContain('该合并任务暂无报告');
    expect(wrapper.text()).toContain('合并任务无执行过程，报告需手动生成');
    const btn = wrapper.findAll('button').find((b) => b.text() === '生成报告');
    expect(btn).toBeTruthy();
    await btn!.trigger('click');
    expect(mocks.generate).toHaveBeenCalledTimes(1);
  });

  it('无 report:create 权限 → 不渲染「生成报告」，空态照常可见', () => {
    mocks.hasPermission.mockImplementation((p?: string) => p !== 'report:create');
    const wrapper = mountCard();
    expect(wrapper.text()).toContain('该合并任务暂无报告');
    expect(wrapper.findAll('button').some((b) => b.text() === '生成报告')).toBe(false);
  });
});

describe('已有报告', () => {
  it('展示名称 / 状态 / ID，「查看报告」跳报告页', async () => {
    mocks.state.report = ref({ id: 901, name: '合并任务报告', status: 'published' });
    const wrapper = mountCard();
    expect(wrapper.text()).toContain('合并任务报告');
    expect(wrapper.text()).toContain('已发布');
    expect(wrapper.text()).toContain('ID 901');
    const view = wrapper.findAll('button').find((b) => b.text() === '查看报告');
    await view!.trigger('click');
    expect(mocks.push).toHaveBeenCalledWith({ name: 'reportView', params: { id: '901' } });
  });

  it('无 report:read 权限 → 不渲染「查看报告」', () => {
    mocks.hasPermission.mockImplementation((p?: string) => p !== 'report:read');
    mocks.state.report = ref({ id: 901, name: '合并任务报告', status: 'draft' });
    const wrapper = mountCard();
    expect(wrapper.findAll('button').some((b) => b.text() === '查看报告')).toBe(false);
    expect(wrapper.text()).toContain('草稿');
  });
});

describe('加载 / 失败 / 生成中', () => {
  it('加载中渲染骨架，不渲染「暂无报告」', () => {
    mocks.state.loading = ref(true);
    const wrapper = mountCard();
    expect(wrapper.find('[data-testid="container-report-skeleton"]').exists()).toBe(true);
    expect(wrapper.text()).not.toContain('该合并任务暂无报告');
  });

  it('列表失败 → Empty +「重试」（不阻断详情其余区域）', async () => {
    mocks.state.error = ref(true);
    const wrapper = mountCard();
    expect(wrapper.text()).toContain('报告加载失败');
    const retry = wrapper.findAll('button').find((b) => b.text() === '重试');
    await retry!.trigger('click');
    expect(mocks.retry).toHaveBeenCalledTimes(1);
  });

  it('生成中 → 「报告生成中…」，不谎报「暂无报告」', () => {
    mocks.state.generating = ref(true);
    const wrapper = mountCard();
    expect(wrapper.text()).toContain('报告生成中…');
    expect(wrapper.text()).not.toContain('该合并任务暂无报告');
  });
});
