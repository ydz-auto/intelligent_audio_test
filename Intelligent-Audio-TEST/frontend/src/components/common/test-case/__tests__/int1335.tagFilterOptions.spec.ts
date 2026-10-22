/**
 * INT-1335：用例管理「标签」筛选下拉选项数与 /tags/names 不符（已加载用例 7 vs 接口 69）。
 *
 * 修复口径：
 * - 标签筛选下拉选项改用 tagsPort.getTagNames() 全量标签（GET /tags/names），
 *   不再受当前已加载用例的标签子集限制；
 * - 全量标签加载完成前回退到 props.tags（已加载用例的标签），保证筛选立即可用；
 * - 加载失败保持回退，不阻塞筛选。
 *
 * 锁定行为（挂载真实 BadgeFilter 断言其 options）：
 * - 挂载时发起 getTagNames 请求；
 * - getTagNames 返回全量标签 → 标签 BadgeFilter options 与接口返回逐一对照；
 * - getTagNames 未完成/失败 → options 回退 props.tags。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import BadgeFilter from '../../BadgeFilter.vue';
import TestCaseListContainer from '../TestCaseListContainer.vue';

vi.mock('@/composables/testCase/testcasesPort', () => ({
  testcasesPort: {
    getGroups: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 1000, pages: 1 })),
    getAll: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 50, pages: 1 })),
    getTagView: vi.fn(async () => ({ items: [], total: 0, page: 1, perPage: 50, pages: 1 })),
  },
}));
const tagsPort = vi.hoisted(() => ({ getTags: vi.fn(), getTagNames: vi.fn() }));
vi.mock('@/composables/shared/tagsPort', () => ({ tagsPort }));
vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getOptions: vi.fn(async () => ({ algorithms: [] })) },
}));
vi.mock('@/composables/evaluation/evaluationPort', () => ({
  evaluationPort: { getAll: vi.fn(async () => ({ items: [] })), getCategories: vi.fn(async () => ({ items: [] })) },
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

const stubs = {
  TestCaseListWithPagination: true,
  TestCaseGroupActions: true,
  AlgorithmFilter: true,
  AudioPlayerModal: true,
  AudioPreviewModal: true,
};

/** 69 个真实库标签名（INT-1260 走查 GET /api/v1/tags/names?per_page=500 → total=69） */
const FULL_TAG_NAMES = Array.from({ length: 69 }, (_, i) => `标签${i + 1}`);

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

/** 取「标签」标题的 BadgeFilter 组件及其 options prop */
const findTagBadgeFilter = (wrapper: ReturnType<typeof mountContainer>) => {
  const all = wrapper.findAllComponents(BadgeFilter);
  const tagFilter = all.find((b) => b.props('title') === '标签');
  expect(tagFilter).toBeTruthy();
  return tagFilter!;
};

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  tagsPort.getTags.mockResolvedValue({ items: [] });
  tagsPort.getTagNames.mockResolvedValue({ items: FULL_TAG_NAMES, total: FULL_TAG_NAMES.length });
});

describe('INT-1335｜标签筛选下拉选项与 /tags/names 全量对照', () => {
  it('挂载即发起 getTagNames，选项数与接口 total 逐一对照（69）', async () => {
    const wrapper = mountContainer();
    await flushPromises();

    expect(tagsPort.getTagNames).toHaveBeenCalled();
    const options = findTagBadgeFilter(wrapper).props('options') as { value: string; label: string }[];
    expect(options).toHaveLength(FULL_TAG_NAMES.length);
    expect(options.map((o) => o.value)).toEqual(FULL_TAG_NAMES);
    expect(options.map((o) => o.label)).toEqual(FULL_TAG_NAMES);
  });

  it('接口分页（单页不足 total）时按 total 拉全，选项数与 total 一致', async () => {
    const page1 = Array.from({ length: 500 }, (_, i) => `标签${i + 1}`);
    const page2 = Array.from({ length: 100 }, (_, i) => `标签500${i + 1}`);
    tagsPort.getTagNames
      .mockResolvedValueOnce({ items: page1, total: 600 })
      .mockResolvedValueOnce({ items: page2, total: 600 });

    const wrapper = mountContainer();
    await flushPromises();

    expect(tagsPort.getTagNames).toHaveBeenCalledTimes(2);
    expect(tagsPort.getTagNames).toHaveBeenNthCalledWith(1, { page: 1, perPage: 500 });
    expect(tagsPort.getTagNames).toHaveBeenNthCalledWith(2, { page: 2, perPage: 500 });
    const options = findTagBadgeFilter(wrapper).props('options') as { value: string }[];
    expect(options).toHaveLength(600);
  });

  it('getTagNames 尚未完成（挂载即读）→ 回退 props.tags 子集', () => {
    tagsPort.getTagNames.mockReturnValue(new Promise(() => {})); // 永不 resolve
    const wrapper = mountContainer({ tags: ['环境理解', '拒识'] });

    const options = findTagBadgeFilter(wrapper).props('options') as { value: string }[];
    expect(options.map((o) => o.value)).toEqual(['环境理解', '拒识']);
  });

  it('getTagNames 失败 → 回退 props.tags，筛选仍可用', async () => {
    tagsPort.getTagNames.mockRejectedValue(new Error('net down'));
    const wrapper = mountContainer({ tags: ['环境理解'] });
    await flushPromises();

    const options = findTagBadgeFilter(wrapper).props('options') as { value: string }[];
    expect(options.map((o) => o.value)).toEqual(['环境理解']);
  });

  it('getTagNames 返回空列表（后端无标签）→ 选项为空而非残留 props.tags', async () => {
    tagsPort.getTagNames.mockResolvedValue({ items: [], total: 0 });
    const wrapper = mountContainer({ tags: ['环境理解'] });
    await flushPromises();

    const options = findTagBadgeFilter(wrapper).props('options') as { value: string }[];
    expect(options).toHaveLength(0);
  });
});
