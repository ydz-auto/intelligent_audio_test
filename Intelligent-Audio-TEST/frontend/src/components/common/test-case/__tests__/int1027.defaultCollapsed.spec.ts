/**
 * INT-1027 回归：分组/标签卡默认收起（对照 React INT-1027 实施对齐）。
 *
 * React 基准 d6bb04be6（grouped-case-list.test.tsx / tag-case-list.test.tsx）：
 * - 分组/标签异步到达后默认收起——组头可见、组内用例卡不可见；
 * - 点组头展开后组内用例可见，其他组保持收起；再点可收起。
 *
 * Vue 侧共用组件 TestCaseListContainer（/testcases 与 /start-test 共用）：
 * 展开状态由 useTestCaseGroupExpand 的 expandedCategories / expandedTagCategories
 * 驱动模板 `.category-content :class="{ expanded: expandedCategories[group] }"`
 * （TestCaseListContainer.css:542-550 `.category-content{display:none}` ↔
 *  `.category-content.expanded{display:block}` 门控）。
 *
 * 本 spec 分两层锁定：
 * 1) 容器编排层状态契约——初始空集（默认收起）、toggleCategory / toggleTagCategory
 *    展开/收起生效、展开触发组内懒加载；
 * 2) 组件 DOM 门控——默认无 .expanded 类，点组头后挂 .expanded（display:none→block，
 *    组内内容随展开可见），其他组保持收起，再点可收起。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { reactive } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { mount } from '@vue/test-utils';

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
}));

vi.mock('@/composables/testCase/testcasesPort', () => ({ testcasesPort: ports }));
// 生命周期 onMounted 会拉算法/维度/播放设备选项，挂载时静默为假端口返回空
vi.mock('@/composables/device/playbackPort', () => ({ playbackPort: { getAll: vi.fn().mockResolvedValue([]) } }));
vi.mock('@/composables/algorithm/algorithmPort', () => ({ algorithmPort: { getOptions: vi.fn().mockResolvedValue({ algorithms: [] }) } }));
vi.mock('@/composables/evaluation/evaluationPort', () => ({ evaluationPort: { getOptions: vi.fn().mockResolvedValue({ dimensions: [] }) } }));
vi.mock('@/composables/shared/tagsPort', () => ({ tagsPort: { getTags: vi.fn().mockResolvedValue({ items: [] }) } }));

import { createContainerState } from '../testCaseListContainer.state';
import { createGroupExpandModule } from '../testCaseListContainer.groupExpand';
import { useTestCaseStore } from '@/store/testCaseStore';
import TestCaseListContainer from '../TestCaseListContainer.vue';

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  ports.getAll.mockResolvedValue({ items: [], total: 0, page: 1, perPage: 20, pages: 1 });
});

// ===== 容器编排层：状态契约 =====

const setupModule = (viewMode: 'group' | 'tag' = 'group') => {
  const props = reactive({ viewMode, trashMode: false });
  const state = createContainerState(props);
  const emit = vi.fn();
  const mod = createGroupExpandModule(props, emit, state);
  return { props, state, mod };
};

const seedGroup = (name = '分组A', id = 'g1', testCaseCount = 3) => {
  const store = useTestCaseStore();
  store.groupsList = [{ id, name, testCaseCount }];
  store.fullGroupsMap = { [id]: { id, name } } as any;
  return store;
};

describe('INT-1027｜状态契约：默认收起 + 组头可展开（对照 React grouped-case-list.test.tsx）', () => {
  it('初始 expandedCategories / expandedTagCategories 均为空集 → 分组/标签卡默认收起', () => {
    const { mod } = setupModule('group');
    expect(mod.expandedCategories.value).toEqual({});
    expect(mod.expandedTagCategories.value).toEqual({});
  });

  it('toggleCategory 展开分组：展开态生效且触发组内懒加载（组内内容随展开可加载）', async () => {
    const { mod } = setupModule('group');
    seedGroup();

    await mod.toggleCategory('分组A');

    expect(mod.expandedCategories.value['分组A']).toBe(true);
    expect(ports.getAll).toHaveBeenCalledWith(expect.objectContaining({ groupId: 'g1' }));
  });

  it('toggleCategory 再点收起（组头可展开/可折叠，会话内状态保持）', async () => {
    const { mod } = setupModule('group');
    seedGroup();

    await mod.toggleCategory('分组A');
    await mod.toggleCategory('分组A');

    expect(mod.expandedCategories.value['分组A']).toBe(false);
  });

  it('toggleTagCategory 展开/收起标签卡（标签视图同样默认收起）', () => {
    const { mod } = setupModule('tag');

    expect(mod.expandedTagCategories.value).toEqual({});

    mod.toggleTagCategory('音箱');
    expect(mod.expandedTagCategories.value['音箱']).toBe(true);

    mod.toggleTagCategory('音箱');
    expect(mod.expandedTagCategories.value['音箱']).toBe(false);
  });
});

// ===== 组件 DOM 门控 =====

/** 用桩替换重型子组件：用例列表桩渲染组内用例名（证明内容区在展开后可见） */
const caseListStub = {
  name: 'TestCaseListWithPagination',
  props: ['testCases'],
  template: '<div class="case-list-stub"><div v-for="tc in testCases" :key="tc.id" class="stub-case-name">{{ tc.name }}</div></div>',
};

const mountContainer = (testCaseGroups: Record<string, any[]>) => {
  const pinia = createPinia();
  setActivePinia(pinia);
  return mount(TestCaseListContainer, {
    props: {
      viewMode: 'group',
      testCaseGroups,
    },
    global: {
      plugins: [pinia],
      stubs: {
        TestCaseListWithPagination: caseListStub,
        TestCaseGroupActions: { template: '<div class="group-actions-stub" />' },
        BadgeFilter: { template: '<div class="badge-filter-stub" />' },
        AlgorithmFilter: { template: '<div class="algorithm-filter-stub" />' },
        AudioPlayerModal: { template: '<div class="audio-player-stub" />' },
        AudioPreviewModal: { template: '<div class="audio-preview-stub" />' },
      },
    },
  });
};

const CASES = {
  '分组A': [
    { id: 'c1', name: '智能音箱-播放音乐', type: 'api' },
    { id: 'c2', name: '智能音箱-闹钟设置', type: 'e2e' },
  ],
  '分组B': [
    { id: 'c3', name: '车载-导航指令', type: 'api' },
  ],
};

describe('INT-1027｜DOM 门控：默认收起、点组头展开可见（对照 React tag-case-list.test.tsx）', () => {
  // jsdom 不应用外部样式表（vitest css:false），display:none 无法经 getComputedStyle 计算；
  // 故 DOM 层以 .expanded 类门控为可见性契约（TestCaseListContainer.css:542-550
  //  `.category-content{display:none}` ↔ `.category-content.expanded{display:block}`）。
  it('分组异步到达后默认收起：组头可见、.category-content 均不带 expanded（内容区 display:none 门控）', () => {
    const wrapper = mountContainer(CASES);

    expect(wrapper.find('.category-header').exists()).toBe(true);
    expect(wrapper.text()).toContain('分组A');
    const contents = wrapper.findAll('.category-content');
    expect(contents.length).toBe(2);
    for (const content of contents) {
      expect(content.classes()).not.toContain('expanded');
    }
    expect(wrapper.findAll('.category-content.expanded').length).toBe(0);
  });

  it('点组头展开：该组 .category-content 挂 expanded（display:none→block）、组内内容区渲染用例；其他组保持收起', async () => {
    const wrapper = mountContainer(CASES);

    await wrapper.findAll('.category-header')[0].trigger('click');

    expect(wrapper.findAll('.category-content.expanded').length).toBe(1);
    // 展开组内容区渲染组内用例名（.expanded → CSS display:block，组内内容随展开可见）
    const expandedContent = wrapper.find('.category-content.expanded');
    expect(expandedContent.text()).toContain('智能音箱-播放音乐');
    expect(expandedContent.text()).toContain('智能音箱-闹钟设置');
    // 另一组保持收起：.category-content 仍不带 expanded（CSS display:none 门控，组内用例不可见）
    const otherContent = wrapper.findAll('.category-content').find((c: any) => !c.classes().includes('expanded'));
    expect(otherContent).toBeTruthy();
    expect(otherContent!.classes()).not.toContain('expanded');
  });

  it('再点组头可收起（可折叠）', async () => {
    const wrapper = mountContainer(CASES);

    await wrapper.findAll('.category-header')[0].trigger('click');
    expect(wrapper.findAll('.category-content.expanded').length).toBe(1);

    await wrapper.findAll('.category-header')[0].trigger('click');
    expect(wrapper.findAll('.category-content.expanded').length).toBe(0);
  });
});
