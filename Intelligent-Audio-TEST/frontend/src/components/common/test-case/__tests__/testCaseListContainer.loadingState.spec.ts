/**
 * INT-1296：用例管理列表首屏加载指示（不渲染误导性空态）。
 *
 * 锁定行为（选择器随 INT-1314 骨架屏方案合并后更新，行为不变）：
 * - 分组视图首屏加载中（isLoading=true 且尚无分组）→ 渲染骨架屏，不渲染空态；
 * - 分组视图加载完成且确实无分组 → 空态照常渲染（回归）；
 * - 分组视图已有数据时再次刷新（isLoading=true 但已有分组）→ 保持显示分组，不闪加载态；
 * - 标签视图首屏加载中（isLoading=true 且尚无标签）→ 渲染骨架屏，不渲染空态；
 * - 标签视图加载完成且确实无标签 → 空态照常渲染（回归）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';

vi.mock('@/composables/testCase/testcasesPort', () => ({
  testcasesPort: {
    getGroups: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 1000, pages: 1 })),
    getAll: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 50, pages: 1 })),
    getTagView: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 50, pages: 1 })),
  },
}));
vi.mock('@/composables/shared/tagsPort', () => ({
  tagsPort: { getTagNames: vi.fn(async () => ({ items: [] })) },
}));
vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getOptions: vi.fn(async () => ({ algorithms: [] })) },
}));
vi.mock('@/composables/evaluation/evaluationPort', () => ({
  evaluationPort: { getOptions: vi.fn(async () => ({ dimensions: [] })) },
}));
vi.mock('@/composables/device/playbackPort', () => ({
  playbackPort: { getAll: vi.fn(async () => []) },
}));
vi.mock('@/composables/audio/audiosPort', () => ({
  audiosPort: {
    getAll: vi.fn(async () => ({ items: [] })),
    getByIds: vi.fn(async () => []),
  },
}));
vi.mock('@/composables/algorithm/useAlgorithmConfig', () => ({
  useAlgorithmConfig: () => ({
    getAlgorithmOptions: vi.fn(async () => []),
    getCaseAlgorithmParams: vi.fn(async () => []),
  }),
}));
vi.mock('@/composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({
    algorithmOptions: { value: [] },
    loadAlgorithms: vi.fn(async () => {}),
  }),
}));
vi.mock('@/composables/modal/useModal', async () => {
  const actual = await vi.importActual<any>('@/composables/modal/useModal');
  return {
    ...actual,
    useModalControl: () => ({
      open: vi.fn(async () => ({})),
      close: vi.fn(),
      closeAll: vi.fn(),
      getActiveModals: vi.fn(() => []),
      updateModalProps: vi.fn(),
      registerModal: vi.fn(),
    }),
  };
});

import TestCaseListContainer from '../TestCaseListContainer.vue';

const stubs = {
  TestCaseListWithPagination: true,
  TestCaseGroupActions: true,
  BadgeFilter: true,
  AlgorithmFilter: true,
  AudioPlayerModal: true,
  AudioPreviewModal: true,
};

beforeEach(() => {
  setActivePinia(createPinia());
});

const mountContainer = (props: Record<string, unknown> = {}) =>
  mount(TestCaseListContainer, {
    props: {
      testCaseGroups: {},
      tagViewData: {},
      tags: [],
      paginationInfo: { page: 1, pages: 1, perPage: 50, total: 0 },
      tagViewPagination: { page: 1, pages: 1, perPage: 50, total: 0 },
      isLoading: false,
      tagViewLoading: false,
      ...props,
    },
    global: { stubs },
  });

const fakeCase = {
  id: 'case-1',
  name: '接线测试_加载态用例',
  type: 'api',
  deleted: false,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  config: {},
  tags: [],
  algorithmType: 'asr',
  groupId: 'group-1',
  groupName: '分组A',
};

describe('INT-1296：首屏加载指示（分组视图）', () => {
  it('isLoading=true 且无分组 → 渲染骨架屏，不渲染空态', async () => {
    const wrapper = mountContainer({ viewMode: 'group', isLoading: true });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(true);
    expect(wrapper.find('.empty-state').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('没有找到测试用例分组');
    expect(wrapper.text()).not.toContain('请尝试添加新的测试用例或创建分组');
  });

  it('isLoading=false 且确实无分组 → 空态照常渲染（回归）', async () => {
    const wrapper = mountContainer({ viewMode: 'group', isLoading: false });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(false);
    expect(wrapper.find('.empty-state').exists()).toBe(true);
    expect(wrapper.text()).toContain('没有找到测试用例分组');
  });

  it('已有分组时再次刷新（isLoading=true）→ 保持显示分组，不闪加载态', async () => {
    const wrapper = mountContainer({
      viewMode: 'group',
      isLoading: true,
      testCaseGroups: { 分组A: [fakeCase] },
    });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(false);
    expect(wrapper.find('.empty-state').exists()).toBe(false);
    expect(wrapper.text()).toContain('分组A');
  });

  it('挂载后 isLoading 由 false→true（首屏加载中的响应式流）→ 骨架屏出现、空态被抑制', async () => {
    const wrapper = mountContainer({ viewMode: 'group', isLoading: false });
    await flushPromises();
    // 初始：无数据、未加载 → 空态（旧基线）；随后父级进入加载中
    expect(wrapper.find('.empty-state').exists()).toBe(true);

    await wrapper.setProps({ isLoading: true });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(true);
    expect(wrapper.find('.empty-state').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('没有找到测试用例分组');
  });

  it('挂载后 isLoading 由 true→false 且确实无分组 → 骨架屏消失、空态回归', async () => {
    const wrapper = mountContainer({ viewMode: 'group', isLoading: true });
    await flushPromises();
    expect(wrapper.find('.case-list-skeleton').exists()).toBe(true);

    await wrapper.setProps({ isLoading: false });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(false);
    expect(wrapper.find('.empty-state').exists()).toBe(true);
    expect(wrapper.text()).toContain('没有找到测试用例分组');
  });

  it('加载失败（error 非空）→ 错误横幅优先，不渲染骨架屏', async () => {
    const wrapper = mountContainer({
      viewMode: 'group',
      isLoading: true,
      error: '用例服务暂不可用，请稍后重试',
    });
    await flushPromises();

    expect(wrapper.find('.test-case-error-banner').exists()).toBe(true);
    expect(wrapper.find('.case-list-skeleton').exists()).toBe(false);
  });
});

describe('INT-1296：首屏加载指示（标签视图）', () => {
  it('isLoading=true 且无标签 → 渲染骨架屏，不渲染空态', async () => {
    const wrapper = mountContainer({ viewMode: 'tag', isLoading: true });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(true);
    expect(wrapper.find('.empty-state').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('没有找到标签分组的测试用例');
    // 首屏加载中不得误显示「加载更多标签」
    expect(wrapper.text()).not.toContain('加载更多标签');
  });

  it('isLoading=false 且确实无标签 → 空态照常渲染（回归）', async () => {
    const wrapper = mountContainer({ viewMode: 'tag', isLoading: false });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(false);
    expect(wrapper.find('.empty-state').exists()).toBe(true);
    expect(wrapper.text()).toContain('没有找到标签分组的测试用例');
  });
});
