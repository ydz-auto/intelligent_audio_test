/**
 * INT-972：用例列表容器加载失败错误横幅。
 *
 * 锁定行为（错误态降级，对齐 INT-899/900）：
 * - props.error 非空 → 渲染「用例服务暂不可用，请稍后重试」错误横幅（role=alert），
 *   且不再渲染「没有找到测试用例分组/标签」空态（不以空态误导用户以为库里无数据）；
 * - props.error 为空且无数据 → 空态照常渲染（回归）。
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
      ...props,
    },
    global: { stubs },
  });

describe('INT-972：加载失败错误横幅（分组视图）', () => {
  it('error 非空 → 渲染友好错误横幅，不渲染「没有找到分组」空态', async () => {
    const wrapper = mountContainer({ error: '用例服务暂不可用，请稍后重试' });
    await flushPromises();

    const banner = wrapper.find('.test-case-error-banner');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain('用例服务暂不可用，请稍后重试');
    expect(banner.attributes('role')).toBe('alert');
    expect(wrapper.text()).not.toContain('没有找到测试用例分组');
    expect(wrapper.text()).not.toContain('请尝试添加新的测试用例或创建分组');
  });

  it('error 为空且无数据 → 空态照常渲染（回归）', async () => {
    const wrapper = mountContainer({ viewMode: 'group' });
    await flushPromises();

    expect(wrapper.find('.test-case-error-banner').exists()).toBe(false);
    expect(wrapper.text()).toContain('没有找到测试用例分组');
  });
});

describe('INT-972：加载失败错误横幅（标签视图）', () => {
  it('error 非空 → 错误横幅替代「没有找到标签」空态', async () => {
    const wrapper = mountContainer({ viewMode: 'tag', error: '用例服务暂不可用，请稍后重试' });
    await flushPromises();

    expect(wrapper.find('.test-case-error-banner').exists()).toBe(true);
    expect(wrapper.text()).not.toContain('没有找到标签分组的测试用例');
  });

  it('error 为空且无标签 → 标签空态照常渲染（回归）', async () => {
    const wrapper = mountContainer({ viewMode: 'tag' });
    await flushPromises();

    expect(wrapper.find('.test-case-error-banner').exists()).toBe(false);
    expect(wrapper.text()).toContain('没有找到标签分组的测试用例');
  });
});

describe('INT-1314：标签视图失败自动降级到分组视图', () => {
  it('tagViewError 在标签视图变为非空 → 自动切到分组视图 + 页内降级提示', async () => {
    const wrapper = mountContainer({ viewMode: 'tag' });
    await flushPromises();

    await wrapper.setProps({ tagViewError: '标签视图加载失败，请稍后重试' });
    await flushPromises();

    // 自动降级：视图切换按钮「分组视图」激活，并上抛 update:viewMode=group
    const activeViewBtn = wrapper.find('.view-switcher .btn-toggle.active');
    expect(activeViewBtn.exists()).toBe(true);
    expect(activeViewBtn.text()).toContain('分组视图');
    expect(wrapper.emitted('update:viewMode')?.flat()).toContain('group');
    // 页内降级提示可见，且不残留标签错误横幅
    expect(wrapper.find('.test-case-fallback-notice').exists()).toBe(true);
    expect(wrapper.find('.test-case-error-banner').exists()).toBe(false);
  });

  it('tagViewError 非空但当前已在分组视图 → 不降级不提示', async () => {
    const wrapper = mountContainer({ viewMode: 'group', tagViewError: '标签视图加载失败，请稍后重试' });
    await flushPromises();

    const activeViewBtn = wrapper.find('.view-switcher .btn-toggle.active');
    expect(activeViewBtn.exists()).toBe(true);
    expect(activeViewBtn.text()).toContain('分组视图');
    expect(wrapper.find('.test-case-fallback-notice').exists()).toBe(false);
  });
});

describe('INT-1314：首屏加载骨架屏', () => {
  it('分组视图加载中且无数据 → 渲染骨架屏而非空态', async () => {
    const wrapper = mountContainer({ viewMode: 'group', isLoading: true });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(true);
    expect(wrapper.text()).not.toContain('没有找到测试用例分组');
  });

  it('加载完成且无数据 → 空态照常渲染（回归）', async () => {
    const wrapper = mountContainer({ viewMode: 'group', isLoading: false });
    await flushPromises();

    expect(wrapper.find('.case-list-skeleton').exists()).toBe(false);
    expect(wrapper.text()).toContain('没有找到测试用例分组');
  });
});
