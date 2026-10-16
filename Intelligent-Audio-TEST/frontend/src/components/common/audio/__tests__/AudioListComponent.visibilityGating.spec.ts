/**
 * INT-536（D2）：音频列表编辑/删除入口 canEditResource 门控回归。
 *
 * 契约：私有音频非 owner（含 admin 豁免）隐藏「详情」（编辑）与「删除」入口；
 *      共享音频回落既有权限点保留入口；owner 私有音频保留入口。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';
import AudioListComponent from '../AudioListComponent.vue';

vi.mock('../misc/FolderNodeComponent.vue', () => ({ default: { template: '<div class="folder-node-stub" />' } }));
vi.mock('../data/PaginationComponent.vue', () => ({ default: { template: '<div class="pagination-stub" />' } }));
vi.mock('../BadgeFilter.vue', () => ({ default: { template: '<div class="badge-filter-stub" />' } }));

const baseProps = {
  audios: [] as any[],
  enableSelection: true,
  showStatus: true,
  audioType: 'all',
  selectedAudios: [] as (string | number)[],
  totalAudios: 0,
  currentPage: 1,
  pageSize: 20,
  allTags: [] as string[],
  selectedTags: [] as string[],
  tagModes: {},
};

function mountComponent(overrides: Record<string, unknown> = {}) {
  return mount(AudioListComponent, {
    props: { ...baseProps, ...overrides },
  });
}

const AUDIOS = [
  { id: 1, name: '共享音频', format: 'wav', size: 10, duration: 1, type: 'dry', status: 'active', visibility: 'shared', createdByUserId: 999 },
  { id: 2, name: '他人私有', format: 'wav', size: 10, duration: 1, type: 'dry', status: 'active', visibility: 'private', createdByUserId: 999 },
  { id: 3, name: '我的私有', format: 'wav', size: 10, duration: 1, type: 'dry', status: 'active', visibility: 'private', createdByUserId: 1 },
];

function authAs(userId: number, permissions: string[] = []) {
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: userId, username: 'tester', roleId: null, roleName: '', permissions });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('INT-536 D2：音频列表编辑/删除入口门控', () => {
  it('非 owner 私有音频：隐藏「详情」与「删除」按钮', () => {
    authAs(1);
    const wrapper = mountComponent({ viewMode: 'list', audios: AUDIOS, totalAudios: 3, loading: false });

    const row = wrapper.findAll('tbody tr').find((r: any) => r.text().includes('他人私有'));
    expect(row, '他人私有音频行应渲染').toBeTruthy();
    expect(row!.text()).not.toContain('详情');
    expect(row!.text()).not.toContain('删除');
  });

  it('owner 私有音频：保留「详情」与「删除」按钮', () => {
    authAs(1);
    const wrapper = mountComponent({ viewMode: 'list', audios: AUDIOS, totalAudios: 3, loading: false });

    const row = wrapper.findAll('tbody tr').find((r: any) => r.text().includes('我的私有'));
    expect(row!.text()).toContain('详情');
    expect(row!.text()).toContain('删除');
  });

  it('共享音频：保留「详情」与「删除」按钮（回落既有权限点）', () => {
    authAs(1);
    const wrapper = mountComponent({ viewMode: 'list', audios: AUDIOS, totalAudios: 3, loading: false });

    const row = wrapper.findAll('tbody tr').find((r: any) => r.text().includes('共享音频'));
    expect(row!.text()).toContain('详情');
    expect(row!.text()).toContain('删除');
  });

  it('admin 豁免：非 owner 私有音频仍保留「详情」与「删除」按钮', () => {
    authAs(1, ['*']);
    const wrapper = mountComponent({ viewMode: 'list', audios: AUDIOS, totalAudios: 3, loading: false });

    const row = wrapper.findAll('tbody tr').find((r: any) => r.text().includes('他人私有'));
    expect(row!.text()).toContain('详情');
    expect(row!.text()).toContain('删除');
  });
});
