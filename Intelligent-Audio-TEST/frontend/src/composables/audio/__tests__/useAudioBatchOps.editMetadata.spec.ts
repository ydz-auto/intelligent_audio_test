/**
 * INT-1330（P1）：音频详情「编辑元数据」改「文件名」不生效回归。
 *
 * 契约：PUT /audios/{id}/metadata 的「文件名」上行 key 必须用后端
 *       UpdateMetadataRequest / handle_update_metadata 只读的 `name`；
 *       发 `fileName` 后端不读，GET 后 name 仍为原值。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';

const audiosPort = vi.hoisted(() => ({ delete: vi.fn(), batchAction: vi.fn(), updateMetadata: vi.fn(), download: vi.fn() }));
const modalManager = vi.hoisted(() => ({ open: vi.fn(), closeAll: vi.fn() }));
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

describe('INT-1330：编辑元数据「文件名」上行 name', () => {
  it('打开元数据模态窗：data 与 fields 用 name（非 fileName）', () => {
    authAs(1);
    const audioList = ref([{ id: 7, name: '原名.wav', audioType: 'dry', asrText: 'x', tags: [], filepath: '/a/b' }] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);

    ops.editMetadata(7);

    expect(modalManager.open).toHaveBeenCalledTimes(1);
    const config = modalManager.open.mock.calls[0][1];
    expect(config.data.name).toBe('原名.wav');
    expect(config.data.fileName).toBeUndefined();
    expect(config.fields).toContainEqual({ key: 'name', label: '文件名' });
  });

  it('保存时 updateMetadata 收到含 name 的 editedData，无 fileName', async () => {
    authAs(1);
    const audioList = ref([{ id: 7, name: '原名.wav', audioType: 'dry', asrText: 'x', tags: [], filepath: '/a/b' }] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);
    audiosPort.updateMetadata.mockResolvedValue({ success: true, message: '元数据更新成功' });
    modalManager.open.mockResolvedValue({
      action: 'save',
      data: {
        id: 7,
        name: '接线测试_改名.wav',
        audioType: 'dry',
        asrText: 'x',
        tags: '',
        format: '',
        duration: 0,
        size: 0,
        sourceLanguage: '',
        translations: [],
        annotations: [],
      },
    });

    await ops.editMetadata(7);

    expect(audiosPort.updateMetadata).toHaveBeenCalledTimes(1);
    const [id, payload] = audiosPort.updateMetadata.mock.calls[0];
    expect(id).toBe(7);
    expect(payload.name).toBe('接线测试_改名.wav');
    expect(payload.fileName).toBeUndefined();
  });
});
