/**
 * INT-256：INT-250 修复本体回归锁 —— PublishedTasks 筛选栏 pt- 前缀隔离（结构渲染断言）。
 *
 * 背景：INT-250 将独立页 PublishedTasks.vue 筛选栏五类（filter-section / search-input /
 *   filter-item / custom-range / sort-item）改 pt- 前缀，规避全局注入的三条串扰规则——
 *   test-case-manager.css .filter-section{height:40px}（徽章筛选换行后容器被钳高、第二行
 *   溢出压到卡片）、common.css .search-input{background:transparent!important;padding-left:40px!important}、
 *   comparison-common.css .filter-item{width:100%}。
 * INT-298 随后将该页迁入 Tasks 页「已发布任务」页签（PublishedTaskPanel.vue，视图能力不降级）：
 *   筛选栏由宿主 Tasks.vue 共享筛选栏承载（filter-sort.css 域内类，不在面板范围），
 *   pt- 前缀隔离纪律在面板延续为结构类命名（pt-list / pt-card / pt-detail / pt-pagination / pt-empty）。
 *
 * 锁定口径（本用例，防串扰结构回归）：
 * 1. 面板结构渲染：列表 / 卡片 / 卡片头 / 版本徽章 / 状态徽章 / Benchmark 徽章 / 元信息 /
 *    操作按钮区 / 详情区 / 空态 / 分页——各区块 pt- 类存在且随数据渲染（有回归语义，非空断言）；
 * 2. 隔离不变量：面板整棵 DOM 无任何元素携带三条全局串扰源类（filter-section / search-input /
 *    filter-item）——若后续全局样式调整使面板复用这些裸类名，立即失败并复现 INT-250 同类串扰；
 * 3. 全局串扰源负例锚点：注入三条真实全局规则后，带 pt- 类的元素计算样式不受其影响
 *    （height 不被钳 40px、background 不被透明化、width 不被钳 100%）——证明全局源真实加载、
 *    隔离断言不空转；对照裸类名元素确实被命中。
 * 4. 发布入口：宿主经 ref 调 openPublishModal → 弹窗打开（expose 契约）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { nextTick } from 'vue';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const srcDir = resolve(here, '../../..'); // src/views/Tasks/__tests__ → src

const pushes = vi.hoisted(() => ({ list: [] as any[] }));
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: (loc: any) => pushes.list.push(loc) }),
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
import type { PublishedTaskItem } from '../../../domain/model/publishedTask';

/** 三条全局串扰源规则（与生产 main.css 全局注入的三个文件同源、原样摘录） */
const GLOBAL_COLLIDING_CSS = [
  readFileSync(resolve(srcDir, 'assets/styles/test-case-manager/test-case-manager.css'), 'utf8'),
  readFileSync(resolve(srcDir, 'assets/styles/components/common.css'), 'utf8'),
  readFileSync(resolve(srcDir, 'assets/styles/components/comparison-common.css'), 'utf8'),
].join('\n');

const injectedStyles: HTMLStyleElement[] = [];
function injectCss(css: string) {
  const el = document.createElement('style');
  el.textContent = css;
  document.head.appendChild(el);
  injectedStyles.push(el);
}

beforeEach(() => {
  pushes.list.length = 0;
});

afterEach(() => {
  while (injectedStyles.length) injectedStyles.pop()!.remove();
  document.body.innerHTML = '';
});

/** 列表项（对齐 PublishedTaskItem Domain 形状） */
function ptItem(overrides: Partial<PublishedTaskItem> = {}): PublishedTaskItem {
  return {
    id: 101,
    sourceTaskId: 9,
    name: '回归任务A',
    description: 'INT-250 回归锁定用例',
    status: 'published',
    benchmark: true,
    version: 3,
    isCurrent: true,
    versionCount: 2,
    publishedBy: 'tester',
    publishedAt: '2026-10-13T12:00:00Z',
    ...overrides,
  } as PublishedTaskItem;
}

/** usePublishedTasks 状态替身（PublishedTaskPanel 仅消费该对象，不关心实现） */
function fakePt(overrides: Record<string, any> = {}) {
  return {
    items: [] as PublishedTaskItem[],
    detail: null as any,
    total: 0,
    page: 1,
    perPage: 10,
    pages: 0,
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
    fetchDetail: vi.fn(async () => null),
    publish: vi.fn(),
    execute: vi.fn(),
    createVersion: vi.fn(),
    archive: vi.fn(),
    rename: vi.fn(),
    setPage: vi.fn(),
    toggleSort: vi.fn(),
    ...overrides,
  } as any;
}

/** 全权限（执行/新版本/归档按钮随权限点显隐） */
async function mountPanel(ptState: any = fakePt()) {
  const { createPinia, setActivePinia } = await import('pinia');
  const { useAuthStore } = await import('../../../store/authStore');
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: 1, username: 'u', roleId: null, roleName: '', permissions: ['*'] });

  const wrapper = mount(PublishedTaskPanel, {
    props: { pt: ptState },
    attachTo: document.body,
    global: {
      stubs: {
        // 弹窗（Teleport to body）不在本文件断言范围（另见 publishedTaskModals.overlayVisibility.spec.ts）
        PublishTaskModal: { template: '<div class="publish-task-modal-stub" />', props: ['tasks', 'submitting', 'presetSourceTaskId'] },
        ReportSnapshotModal: { template: '<div class="report-snapshot-modal-stub" />' },
        TaskSnapshotModal: { template: '<div class="task-snapshot-modal-stub" />' },
        PublishedTaskNameModal: { template: '<div class="published-task-name-modal-stub" />' },
      },
    },
  });
  await flushPromises();
  return wrapper;
}

describe('面板结构渲染（pt- 前缀结构类存在且有数据语义）', () => {
  it('列表卡片渲染完整结构：pt-list/pt-card/pt-card-head/pt-card-main/pt-card-actions', async () => {
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));
    expect(w.find('.pt-list').exists()).toBe(true);
    expect(w.findAll('.pt-card')).toHaveLength(1);
    expect(w.find('.pt-card-head').exists()).toBe(true);
    expect(w.find('.pt-card-main').exists()).toBe(true);
    expect(w.find('.pt-card-actions').exists()).toBe(true);
    w.unmount();
  });

  it('卡片标题行徽章随数据渲染：版本 / 状态 / Benchmark / 版本数 / 当前', async () => {
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));
    expect(w.find('.pt-card-title-row').exists()).toBe(true);
    expect(w.find('.pt-version-badge').text()).toBe('v3');
    expect(w.find('.pt-card-status').text()).toBe('已发布');
    expect(w.find('.pt-benchmark-badge').exists()).toBe(true);
    expect(w.find('.pt-card-version-count').text()).toContain('共 2 个版本');
    expect(w.find('.pt-card-current').text()).toBe('当前');
    w.unmount();
  });

  it('说明与元信息渲染：pt-card-desc / pt-card-meta（来源任务、发布时间、发布人）', async () => {
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));
    expect(w.find('.pt-card-desc').text()).toBe('INT-250 回归锁定用例');
    const meta = w.find('.pt-card-meta').text();
    expect(meta).toContain('来源任务 #9');
    expect(meta).toContain('发布人 tester');
    w.unmount();
  });

  it('操作按钮按权限点渲染：执行 / 版本 / 新版本 / 重命名 / 归档', async () => {
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));
    const actions = w.find('.pt-card-actions').text();
    expect(actions).toContain('执行');
    expect(actions).toContain('版本');
    expect(actions).toContain('新版本');
    expect(actions).toContain('重命名');
    expect(actions).toContain('归档');
    w.unmount();
  });

  it('分页渲染：pt-pagination 与页码信息（total>0 时）', async () => {
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));
    expect(w.find('.pt-pagination').exists()).toBe(true);
    expect(w.find('.pt-page-info').text()).toContain('第 1 / 1 页 · 共 1 条');
    w.unmount();
  });

  it('空态渲染：pt-empty 与引导文案（loading=false 且 items 为空）', async () => {
    const w = await mountPanel(fakePt());
    expect(w.find('.pt-empty').exists()).toBe(true);
    expect(w.find('.pt-empty-hint').exists()).toBe(true);
    expect(w.find('.pt-pagination').exists()).toBe(false);
    w.unmount();
  });

  it('加载态渲染：pt-empty 承载加载中文案', async () => {
    const w = await mountPanel(fakePt({ loading: true }));
    expect(w.find('.pt-empty').text()).toBe('加载中...');
    w.unmount();
  });

  it('展开详情渲染：pt-detail 区块与版本历史行（fetchDetail 成功路径）', async () => {
    const detail = {
      id: 101, name: '回归任务A', status: 'published', version: 3, isCurrent: true, benchmark: false,
      snapshotConfig: {}, hasTaskSnapshot: false, hasReportSnapshot: false,
      sourceTaskId: 9, sourceTaskName: '来源任务A', sourceTaskStatus: 'completed',
      sourceTaskTotalCases: 3, sourceTaskCompletedCases: 3,
      versions: [ptItem(), ptItem({ id: 102, version: 2, isCurrent: false })],
      executionHistory: [],
    } as any;
    const ptState = fakePt({
      items: [ptItem()], total: 1, pages: 1,
      fetchDetail: vi.fn(async () => detail),
    });
    const w = await mountPanel(ptState);
    expect(w.find('.pt-detail').exists()).toBe(false);
    await w.findAll('.pt-card-actions button').find((b) => b.text().includes('版本'))!.trigger('click');
    await flushPromises();
    expect(w.find('.pt-detail').exists()).toBe(true);
    expect(ptState.detail).toBe(detail);
    expect(w.find('.pt-detail-source').text()).toContain('来源任务 #9');
    w.unmount();
  });
});

describe('pt- 前缀隔离不变量（INT-250 防串扰结构回归）', () => {
  it('面板整棵 DOM 无元素携带三条全局串扰源类（filter-section/search-input/filter-item）', async () => {
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));
    for (const cls of ['filter-section', 'search-input', 'filter-item']) {
      expect(w.find(`.${cls}`).exists(), `面板不应复用全局串扰类 .${cls}`).toBe(false);
    }
    // 自定义区间/排序（若宿主未来迁入）也必须走 pt- 前缀
    expect(w.find('.custom-range').exists()).toBe(false);
    expect(w.find('.sort-item').exists()).toBe(false);
    w.unmount();
  });

  it('注入三条真实全局串扰源后，pt- 结构元素计算样式不受钳制（对照裸类名元素被命中）', async () => {
    injectCss(GLOBAL_COLLIDING_CSS);
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));

    // 列表容器：全局 .filter-section{height:40px} 不得命中（pt-list 非 flex 钳高布局）
    const list = w.find('.pt-list').element as HTMLElement;
    expect(window.getComputedStyle(list).height).not.toBe('40px');
    // 对照：裸 filter-section 元素确实被全局规则钳到 40px（证明全局源真实加载）
    const bare = document.createElement('section');
    bare.className = 'filter-section';
    document.body.appendChild(bare);
    expect(window.getComputedStyle(bare).height).toBe('40px');

    // 卡片标题行：全局 .filter-item{width:100%} 不得命中
    const titleRow = w.find('.pt-card-title-row').element as HTMLElement;
    expect(window.getComputedStyle(titleRow).width).not.toBe('100%');

    // 输入类：面板无 search-input；全局 common.css .search-input{background:transparent!important}
    // 若回归回退为裸类名，透明背景立即复现（对照锚点）
    const bareSearch = document.createElement('input');
    bareSearch.className = 'search-input';
    document.body.appendChild(bareSearch);
    expect(window.getComputedStyle(bareSearch).backgroundColor).toBe('rgba(0, 0, 0, 0)');
    expect(w.find('input.search-input').exists()).toBe(false);

    w.unmount();
  });
});

describe('发布入口 expose 契约（INT-298：宿主 Tasks.vue 经 ref 触发）', () => {
  it('openPublishModal → 拉取日常任务候选并打开发布弹窗', async () => {
    const { tasksPort } = await import('@/composables/task/tasksPort');
    const w = await mountPanel(fakePt({ items: [ptItem()], total: 1, pages: 1 }));
    expect(w.find('.publish-task-modal-stub').exists()).toBe(false);
    await (w.vm as any).openPublishModal();
    await flushPromises();
    expect(tasksPort.getAll).toHaveBeenCalledWith({ page: 1, perPage: 100 });
    expect(w.find('.publish-task-modal-stub').exists()).toBe(true);
    w.unmount();
  });
});
