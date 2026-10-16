/**
 * INT-536（D2）：文件夹视图音频编辑/删除入口 canEditResource 门控回归。
 *
 * 契约：私有音频非 owner（含 admin 豁免）隐藏「详情」（编辑）与「删除」入口；
 *      共享音频回落既有权限点保留入口；owner 私有音频保留入口。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';
import FolderNodeComponent from '../FolderNodeComponent.vue';

const FILES = [
  { id: 1, filename: '共享音频.wav', format: 'wav', size: 10, duration: 1, audioType: 'dry', visibility: 'shared', createdByUserId: 999 },
  { id: 2, filename: '他人私有.wav', format: 'wav', size: 10, duration: 1, audioType: 'dry', visibility: 'private', createdByUserId: 999 },
  { id: 3, filename: '我的私有.wav', format: 'wav', size: 10, duration: 1, audioType: 'dry', visibility: 'private', createdByUserId: 1 },
];

function mountFolder(userId: number, permissions: string[] = []) {
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: userId, username: 'tester', roleId: null, roleName: '', permissions });
  return mount(FolderNodeComponent, {
    props: {
      folder: { path: '/', name: 'root', files: FILES, folders: [], count: 3 },
      enableSelection: false,
      isSelectedFn: () => false,
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('INT-536 D2：文件夹视图编辑/删除入口门控', () => {
  it('非 owner 私有音频：隐藏「详情」与「删除」按钮', () => {
    const wrapper = mountFolder(1);
    const item = wrapper.findAll('.file-item').find((i: any) => i.text().includes('他人私有'));
    expect(item, '他人私有音频文件项应渲染').toBeTruthy();
    expect(item!.text()).not.toContain('详情');
    expect(item!.text()).not.toContain('删除');
  });

  it('owner 私有音频：保留「详情」与「删除」按钮', () => {
    const wrapper = mountFolder(1);
    const item = wrapper.findAll('.file-item').find((i: any) => i.text().includes('我的私有'));
    expect(item!.text()).toContain('详情');
    expect(item!.text()).toContain('删除');
  });

  it('共享音频：保留「详情」与「删除」按钮', () => {
    const wrapper = mountFolder(1);
    const item = wrapper.findAll('.file-item').find((i: any) => i.text().includes('共享音频'));
    expect(item!.text()).toContain('详情');
    expect(item!.text()).toContain('删除');
  });

  it('admin 豁免：非 owner 私有音频仍保留「详情」与「删除」按钮', () => {
    const wrapper = mountFolder(1, ['*']);
    const item = wrapper.findAll('.file-item').find((i: any) => i.text().includes('他人私有'));
    expect(item!.text()).toContain('详情');
    expect(item!.text()).toContain('删除');
  });
});
