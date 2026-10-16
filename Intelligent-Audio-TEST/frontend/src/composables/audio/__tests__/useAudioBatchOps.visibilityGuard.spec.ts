/**
 * INT-536（D2）：useAudioBatchOps.deleteAudio owner 守卫回归。
 *
 * 契约：私有音频非 owner（admin 豁免见 canEditResource）前端兜底拦截删除——
 *      列表入口已按 canEditResource 隐藏，此处拦截绕过 UI 直达的删除调用；
 *      owner / admin / 共享音频放行后端删除。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';

const audiosPort = vi.hoisted(() => ({ delete: vi.fn(), batchAction: vi.fn(), updateMetadata: vi.fn(), download: vi.fn() }));
const modalManager = vi.hoisted(() => ({ open: vi.fn() }));
const onRefresh = vi.hoisted(() => vi.fn());

vi.mock('@/composables/audio/audiosPort', () => ({ audiosPort }));
vi.mock('@/utils/modalManager', () => ({ getModalManager: () => modalManager }));
vi.mock('@/composables/modal/constants', () => ({
  MODAL_TYPES: {
    BASIC_CONFIRM: 'basicConfirm',
    DELETE_CONFIRM: 'deleteConfirm',
    DETAIL_VIEW: 'detailView',
  },
}));
vi.mock('@/utils/utils', () => ({ downloadBlob: vi.fn() }));

import { useAudioBatchOps } from '../useAudioBatchOps';

function authAs(userId: number, permissions: string[] = []) {
  setActivePinia(createPinia());
  useAuthStore().setAuth('t', { id: userId, username: 'tester', roleId: null, roleName: '', permissions });
}

beforeEach(() => {
  vi.clearAllMocks();
  modalManager.open.mockResolvedValue(true);
});

describe('INT-536 D2：deleteAudio owner 守卫', () => {
  it('私有音频非 owner：拦截删除（无权限提示），不调 audiosPort.delete', async () => {
    authAs(1);
    const audioList = ref([{ id: 2, name: '他人私有', visibility: 'private', createdByUserId: 999 }] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);

    await ops.deleteAudio(2);

    expect(audiosPort.delete).not.toHaveBeenCalled();
    expect(modalManager.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({ title: '无权限' }));
  });

  it('owner 私有音频：放行后端删除', async () => {
    authAs(1);
    const audioList = ref([{ id: 3, name: '我的私有', visibility: 'private', createdByUserId: 1 }] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);

    await ops.deleteAudio(3);

    expect(audiosPort.delete).toHaveBeenCalledTimes(1);
    expect(audiosPort.delete.mock.calls[0][0]).toBe(3);
  });

  it('admin 豁免：非 owner 私有音频放行后端删除', async () => {
    authAs(1, ['*']);
    const audioList = ref([{ id: 2, name: '他人私有', visibility: 'private', createdByUserId: 999 }] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);

    await ops.deleteAudio(2);

    expect(audiosPort.delete).toHaveBeenCalledTimes(1);
    expect(audiosPort.delete.mock.calls[0][0]).toBe(2);
  });
});
