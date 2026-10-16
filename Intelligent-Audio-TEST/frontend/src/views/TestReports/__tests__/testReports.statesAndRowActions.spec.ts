/**
 * INT-287：TestReports 占位页补齐回归。
 *
 * 缺陷：/test-reports 页两版（V9.7.10/V9.7.31）同为占位半成品——加载态只有一行
 * 文本、0 条无空态文案、错误仅 console.error 用户无感知、列表项无任何操作入口。
 *
 * 验收（issue 原文）：页面具备空态/错误态/加载态与至少「查看报告」入口。
 * 锁定契约：
 * 1. 加载态：spinner + 文案（非裸文本行）；
 * 2. 错误态：端口 reject → 用户可见错误态 + 重试按钮，重试重新拉取；
 * 3. 空态：0 条 → 空态文案；
 * 4. 行操作：查看报告 → router.push /report/:id；删除 → DELETE_CONFIRM 模态 +
 *    reportsPort.delete + 列表重取；收藏 → favoritesPort.favorite + 星标态翻转；
 * 5. 分页：prev/next/go-to/page-size 均以新参数重取。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
  delete: vi.fn(),
  favorite: vi.fn(),
  unfavorite: vi.fn(),
  listFavoriteIds: vi.fn(),
}));
const modal = vi.hoisted(() => ({ open: vi.fn() }));
const routerPush = vi.hoisted(() => vi.fn());

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}));

vi.mock('@/composables/report/reportsPort', () => ({
  reportsPort: ports,
}));

vi.mock('@/composables/favorite/useFavorites', () => ({
  useFavorites: () => {
    const favoriteIds = { value: new Set<string>(['9']) };
    return {
      favoriteIds,
      favoriteOnly: { value: false },
      isFavorite: (id: string | number) => favoriteIds.value.has(String(id)),
      loadFavorites: vi.fn(() => Promise.resolve()),
      toggleFavorite: async (id: string | number) => {
        if (favoriteIds.value.has(String(id))) {
          await ports.unfavorite(id);
          favoriteIds.value = new Set([...favoriteIds.value].filter(k => k !== String(id)));
        } else {
          await ports.favorite(id);
          favoriteIds.value = new Set(favoriteIds.value).add(String(id));
        }
      },
      restore: vi.fn(),
      purge: vi.fn(),
    };
  },
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({ open: modal.open }),
}));

vi.mock('@/composables/modal/constants', () => ({
  MODAL_TYPES: {
    BASIC_CONFIRM: 'basicConfirm',
    DELETE_CONFIRM: 'deleteConfirm',
  },
}));

import TestReports from '../TestReports.vue';

/** 单页报告列表响应（camelCase Domain，端口层形状） */
const REPORTS_PAGE = {
  items: [
    {
      id: 1,
      name: '任务报告A',
      type: 'task',
      status: 'published',
      createdAt: '2026-10-13T10:00:00Z',
      description: '示例任务报告',
      summary: { totalCases: 10, overallSuccessRate: 90 },
    },
    {
      id: 2,
      name: '对比报告B',
      type: 'comparison',
      status: 'draft',
      createdAt: '2026-10-13T11:00:00Z',
      summary: { taskCount: 2, totalCases: 20 },
    },
  ],
  total: 2,
  page: 1,
  perPage: 10,
  pages: 1,
};
const EMPTY_PAGE = { items: [], total: 0, page: 1, perPage: 10, pages: 0 };

beforeEach(() => {
  vi.clearAllMocks();
  ports.getAll.mockResolvedValue(REPORTS_PAGE);
  ports.listFavoriteIds.mockResolvedValue({ report: ['9'] });
  modal.open.mockResolvedValue(true);
});

async function mountPage() {
  const wrapper = mount(TestReports, {
    global: {
      stubs: { teleport: true },
    },
  });
  await flushPromises();
  return wrapper;
}

describe('三态齐全（INT-287 验收主项）', () => {
  it('加载态：spinner + 加载文案（首屏拉取期间可见）', async () => {
    let resolveGet: (v: any) => void = () => {};
    ports.getAll.mockReturnValue(new Promise(resolve => { resolveGet = resolve; }));

    const wrapper = mount(TestReports, { global: { stubs: { teleport: true } } });
    await wrapper.vm.$nextTick();

    const loading = wrapper.find('.tr-loading-state');
    expect(loading.exists(), '拉取期间应渲染加载态容器').toBe(true);
    expect(loading.find('.tr-loading-spinner').exists()).toBe(true);
    expect(loading.text()).toContain('正在加载报告');

    resolveGet(REPORTS_PAGE);
    await flushPromises();
    expect(wrapper.find('.tr-loading-state').exists()).toBe(false);
  });

  it('错误态：端口 reject → 用户可见错误文案 + 重试按钮，重试重新拉取', async () => {
    ports.getAll.mockRejectedValueOnce(new Error('net down'));

    const wrapper = await mountPage();

    const errorState = wrapper.find('.tr-error-state');
    expect(errorState.exists(), '失败后应渲染错误态容器（不再仅 console.error）').toBe(true);
    expect(errorState.text()).toContain('加载报告失败');

    const retry = errorState.findAll('button').find((b: any) => b.text().includes('重试'));
    expect(retry, '错误态应提供重试入口').toBeTruthy();

    ports.getAll.mockResolvedValue(REPORTS_PAGE);
    await retry!.trigger('click');
    await flushPromises();
    expect(wrapper.find('.tr-error-state').exists()).toBe(false);
    expect(ports.getAll).toHaveBeenCalledTimes(2);
    expect(wrapper.find('.report-card').exists()).toBe(true);
  });

  it('空态：0 条时渲染空态文案（不再是裸「报告数量0」）', async () => {
    ports.getAll.mockResolvedValue(EMPTY_PAGE);

    const wrapper = await mountPage();

    const empty = wrapper.find('.tr-empty-state');
    expect(empty.exists(), '0 条时应渲染空态容器').toBe(true);
    expect(empty.text()).toContain('暂无报告数据');
    expect(wrapper.text()).not.toContain('报告数量');
  });
});

describe('行操作：查看 / 收藏 / 删除（对齐 HistoryReports 口径）', () => {
  it('查看报告：点击跳转 /report/:id（router.push reportView）', async () => {
    const wrapper = await mountPage();

    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('任务报告A'));
    expect(card, '报告卡片应存在').toBeTruthy();
    const viewBtn = card!.findAll('button').find((b: any) => b.text().includes('查看报告'));
    expect(viewBtn, '卡片应提供「查看报告」入口').toBeTruthy();

    await viewBtn!.trigger('click');
    expect(routerPush).toHaveBeenCalledWith({ name: 'reportView', params: { id: 1 } });
  });

  it('收藏：点击星标 → favoritesPort.favorite，星标态翻转为已收藏', async () => {
    const wrapper = await mountPage();

    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('任务报告A'));
    const star = card!.findAll('button').find((b: any) => b.attributes('title') === '收藏');
    expect(star, '卡片应提供收藏按钮（title=收藏）').toBeTruthy();

    await star!.trigger('click');
    await flushPromises();
    expect(ports.favorite).toHaveBeenCalledWith(1);
    expect(star!.attributes('title'), '收藏后 title 应翻转为「取消收藏」').toBe('取消收藏');
  });

  it('删除：DELETE_CONFIRM 模态确认 → reportsPort.delete → 列表重取', async () => {
    const wrapper = await mountPage();

    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('任务报告A'));
    const delBtn = card!.findAll('button').find((b: any) => b.text().includes('删除'));
    expect(delBtn, '卡片应提供删除按钮').toBeTruthy();

    await delBtn!.trigger('click');
    await flushPromises();
    expect(modal.open).toHaveBeenCalledTimes(1);
    expect(modal.open.mock.calls[0][0]).toBe('deleteConfirm');

    // 模拟用户确认
    await (modal.open.mock.calls[0][1] as any).onConfirm();
    await flushPromises();
    expect(ports.delete).toHaveBeenCalledWith(1);
    // 删除成功后列表重取（总调用：mounted 1 次 + 删除后 1 次）
    expect(ports.getAll).toHaveBeenCalledTimes(2);
  });

  it('删除：模态取消（onConfirm 不触发）不调 delete', async () => {
    const wrapper = await mountPage();

    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('任务报告A'));
    const delBtn = card!.findAll('button').find((b: any) => b.text().includes('删除'));
    await delBtn!.trigger('click');
    await flushPromises();

    expect(ports.delete).not.toHaveBeenCalled();
  });
});

describe('分页', () => {
  it('next/prev/go-to-page 以新页码重取', async () => {
    ports.getAll.mockResolvedValue({
      items: REPORTS_PAGE.items,
      total: 35,
      page: 1,
      perPage: 10,
      pages: 4,
    });

    const wrapper = await mountPage();

    const nextBtn = wrapper.findAll('button').find((b: any) => b.text().includes('下一页'));
    expect(nextBtn, '多页数据应渲染分页组件').toBeTruthy();
    await nextBtn!.trigger('click');
    await flushPromises();
    expect(ports.getAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, perPage: 10 }));

    const gotoBtns = wrapper.findAll('button').filter((b: any) => /^\d+$/.test(b.text().trim()));
    const page3 = gotoBtns.find((b: any) => b.text().trim() === '3');
    await page3!.trigger('click');
    await flushPromises();
    expect(ports.getAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3, perPage: 10 }));
  });

  it('page-size 变更：重置第 1 页并按新尺寸重取', async () => {
    ports.getAll.mockResolvedValue({ items: REPORTS_PAGE.items, total: 35, page: 1, perPage: 10, pages: 4 });

    const wrapper = await mountPage();
    const pagination = wrapper.findComponent({ name: 'PaginationComponent' });
    expect(pagination.exists()).toBe(true);

    pagination.vm.$emit('page-size-change', 20);
    await flushPromises();
    expect(ports.getAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, perPage: 20 }));
  });
});

describe('INT-536：私有报告非 owner 隐藏删除入口（canEditResource 门控）', () => {
  /** 设置认证用户并挂载页面（canEditResource 依赖 authStore） */
  async function mountWithAuth(userId: number, permissions: string[] = []) {
    setActivePinia(createPinia());
    useAuthStore().setAuth('t', { id: userId, username: 'tester', roleId: null, roleName: '', permissions });
    const wrapper = mount(TestReports, { global: { stubs: { teleport: true } } });
    await flushPromises();
    return wrapper;
  }

  const PRIVATE_REPORT = {
    id: 5,
    name: '私有报告',
    type: 'task',
    status: 'published',
    visibility: 'private',
    createdByUserId: 999,
    createdAt: '2026-10-13T10:00:00Z',
    summary: { totalCases: 1 },
  };

  it('非 owner 私有报告：不渲染删除按钮', async () => {
    ports.getAll.mockResolvedValue({
      items: [PRIVATE_REPORT],
      total: 1, page: 1, perPage: 10, pages: 1,
    });

    const wrapper = await mountWithAuth(1);
    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('私有报告'));
    const delBtn = card!.findAll('button').find((b: any) => b.text().includes('删除'));
    expect(delBtn, '非 owner 私有报告应隐藏删除入口').toBeUndefined();
  });

  it('owner 私有报告：保留删除按钮', async () => {
    ports.getAll.mockResolvedValue({
      items: [{ ...PRIVATE_REPORT, createdByUserId: 1 }],
      total: 1, page: 1, perPage: 10, pages: 1,
    });

    const wrapper = await mountWithAuth(1);
    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('私有报告'));
    const delBtn = card!.findAll('button').find((b: any) => b.text().includes('删除'));
    expect(delBtn, 'owner 私有报告应保留删除入口').toBeTruthy();
  });

  it('admin 豁免：非 owner 私有报告仍保留删除按钮', async () => {
    ports.getAll.mockResolvedValue({
      items: [PRIVATE_REPORT],
      total: 1, page: 1, perPage: 10, pages: 1,
    });

    const wrapper = await mountWithAuth(1, ['*']);
    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('私有报告'));
    const delBtn = card!.findAll('button').find((b: any) => b.text().includes('删除'));
    expect(delBtn, 'admin 豁免下非 owner 私有报告应保留删除入口').toBeTruthy();
  });

  it('共享报告非 owner：保留删除按钮（回落既有权限点）', async () => {
    ports.getAll.mockResolvedValue({
      items: [{ ...PRIVATE_REPORT, visibility: 'shared' }],
      total: 1, page: 1, perPage: 10, pages: 1,
    });

    const wrapper = await mountWithAuth(1);
    const card = wrapper.findAll('.report-card').find((c: any) => c.text().includes('私有报告'));
    const delBtn = card!.findAll('button').find((b: any) => b.text().includes('删除'));
    expect(delBtn, '共享报告应保留删除入口').toBeTruthy();
  });
});
