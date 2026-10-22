/**
 * INT-1332：音频删除超时/加载态回归。
 *
 * 契约：
 * - 删除确认后请求期间进入加载态（deletingIds / batchDeleting），完成后清除；
 * - 同一行/批量删除进行中忽略重复点击，不重复发请求；
 * - 请求超过 DELETE_REQUEST_TIMEOUT_MS 未响应 → 刷新列表核对 + 超时弹窗
 *   （confirmText=重试）；点重试以 skipConfirm 直接重发，不再二次确认。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ref } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/store/authStore';
import { DELETE_REQUEST_TIMEOUT_MS } from '../useAudioBatchOps';

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

const ownerAudio = { id: 3, name: '我的私有', visibility: 'private', createdByUserId: 1 };

function deferred() {
  let resolve!: (v: any) => void;
  let reject!: (e?: any) => void;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
  modalManager.open.mockResolvedValue(true);
  authAs(1);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('INT-1332 单删加载态与并发防护', () => {
  it('删除请求期间进入加载态，成功后清除并刷新', async () => {
    const audioList = ref([ownerAudio] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);
    const d = deferred();
    audiosPort.delete.mockReturnValue(d.promise);

    const p = ops.deleteAudio(3);
    await Promise.resolve();
    // 确认弹窗已返回 true，请求进行中 → 行内加载态
    expect(ops.deletingIds.value).toContain(3);

    d.resolve({ success: true, code: 0, message: '音频文件已删除', data: null });
    await p;

    expect(ops.deletingIds.value).not.toContain(3);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(audiosPort.delete).toHaveBeenCalledTimes(1);
    expect(audiosPort.delete.mock.calls[0][1]).toMatchObject({ unwrapResponse: false });
    expect(audiosPort.delete.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
    expect(modalManager.open).toHaveBeenLastCalledWith('basicConfirm', expect.objectContaining({ title: '删除成功' }));
  });

  it('同一行删除进行中：重复点击忽略，不重复发请求', async () => {
    const audioList = ref([ownerAudio] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);
    const d = deferred();
    audiosPort.delete.mockReturnValue(d.promise);

    const p1 = ops.deleteAudio(3);
    await Promise.resolve();
    const p2 = ops.deleteAudio(3); // 第二次点击，应被并发防护拦截
    await Promise.resolve();

    expect(audiosPort.delete).toHaveBeenCalledTimes(1);

    d.resolve({ success: true, code: 0, message: '音频文件已删除', data: null });
    await Promise.all([p1, p2]);
    expect(audiosPort.delete).toHaveBeenCalledTimes(1);
    expect(ops.deletingIds.value).not.toContain(3);
  });
});

describe('INT-1332 删除超时与重试', () => {
  it('单删超时：刷新核对 + 超时弹窗（重试按钮），点重试不再二次确认直接重发', async () => {
    vi.useFakeTimers();
    const audioList = ref([ownerAudio] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);
    // 首次挂起（触发超时），重试立即成功
    audiosPort.delete
      .mockReturnValueOnce(new Promise(() => {}))
      .mockReturnValueOnce(Promise.resolve({ success: true, code: 0, message: '音频文件已删除', data: null }));

    const p = ops.deleteAudio(3);
    await vi.advanceTimersByTimeAsync(DELETE_REQUEST_TIMEOUT_MS + 1);
    await p;

    // 超时刷新核对（1 次）+ 重试成功后再次刷新（1 次）
    expect(onRefresh).toHaveBeenCalledTimes(2);
    // 超时弹窗：标题 删除超时 + 重试按钮
    expect(modalManager.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({ title: '删除超时', confirmText: '重试' }));
    // 点重试 → 直接重发（共 2 次），不再二次弹确认
    expect(audiosPort.delete).toHaveBeenCalledTimes(2);
    const confirmCalls = modalManager.open.mock.calls.filter(
      (c: any[]) => c[0] === 'basicConfirm' && c[1]?.title === '删除音频'
    );
    expect(confirmCalls).toHaveLength(1);
    // 重试成功后弹出成功提示
    expect(modalManager.open).toHaveBeenLastCalledWith('basicConfirm', expect.objectContaining({ title: '删除成功' }));
    expect(ops.deletingIds.value).not.toContain(3);
  });

  it('单删失败（业务错误）：保留错误提示，不自动重试', async () => {
    const audioList = ref([ownerAudio] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);
    audiosPort.delete.mockRejectedValue(new Error('该音频文件已被测试用例使用，禁止删除'));

    await ops.deleteAudio(3);

    expect(modalManager.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({ title: '删除失败', confirmText: '确定' }));
    expect(audiosPort.delete).toHaveBeenCalledTimes(1);
    expect(ops.deletingIds.value).not.toContain(3);
  });

  it('后端 DEADLINE_EXCEEDED 透传视为超时：提示重试', async () => {
    vi.useFakeTimers();
    const audioList = ref([ownerAudio] as any);
    const ops = useAudioBatchOps(audioList, ref([]) as any, onRefresh);
    const deadlineErr: any = new Error('删除音频失败: <_InactiveRpcError ... StatusCode.DEADLINE_EXCEEDED ...>');
    audiosPort.delete
      .mockRejectedValueOnce(deadlineErr)
      .mockResolvedValueOnce({ success: true, code: 0, message: '音频文件已删除', data: null });

    const p = ops.deleteAudio(3);
    await vi.advanceTimersByTimeAsync(0);
    await p;

    expect(modalManager.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({ title: '删除超时', confirmText: '重试' }));
    expect(audiosPort.delete).toHaveBeenCalledTimes(2);
  });
});

describe('INT-1332 批量删除加载态与超时', () => {
  it('批量删除进行中进入加载态，成功后清空选择并刷新', async () => {
    const selected = ref([1, 2]);
    const ops = useAudioBatchOps(ref([]) as any, selected as any, onRefresh);
    const d = deferred();
    audiosPort.batchAction.mockReturnValue(d.promise);

    const p = ops.batchDelete();
    await Promise.resolve();
    expect(ops.batchDeleting.value).toBe(true);

    d.resolve({ success: true, code: 0, message: '成功删除 2 个音频', data: null });
    await p;

    expect(ops.batchDeleting.value).toBe(false);
    expect(selected.value).toEqual([]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(audiosPort.batchAction).toHaveBeenCalledWith('delete', [1, 2], {}, expect.objectContaining({ unwrapResponse: false }));
  });

  it('批量删除进行中：重复点击忽略', async () => {
    const selected = ref([1, 2]);
    const ops = useAudioBatchOps(ref([]) as any, selected as any, onRefresh);
    const d = deferred();
    audiosPort.batchAction.mockReturnValue(d.promise);

    const p1 = ops.batchDelete();
    await Promise.resolve();
    const p2 = ops.batchDelete(); // 进行中重复点击
    await Promise.resolve();

    expect(audiosPort.batchAction).toHaveBeenCalledTimes(1);

    d.resolve({ success: true, code: 0, message: '成功删除 2 个音频', data: null });
    await Promise.all([p1, p2]);
    expect(audiosPort.batchAction).toHaveBeenCalledTimes(1);
  });

  it('批量删除超时：刷新核对 + 可重试提示', async () => {
    vi.useFakeTimers();
    const selected = ref([1, 2]);
    const ops = useAudioBatchOps(ref([]) as any, selected as any, onRefresh);
    // 首次挂起（触发超时），重试立即成功
    audiosPort.batchAction
      .mockReturnValueOnce(new Promise(() => {}))
      .mockReturnValueOnce(Promise.resolve({ success: true, code: 0, message: '成功删除 2 个音频', data: null }));

    const p = ops.batchDelete();
    await vi.advanceTimersByTimeAsync(DELETE_REQUEST_TIMEOUT_MS + 1);
    await p;

    // 超时刷新核对（1 次）+ 重试成功后再次刷新（1 次）
    expect(onRefresh).toHaveBeenCalledTimes(2);
    expect(modalManager.open).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({ title: '批量删除超时', confirmText: '重试' }));
    expect(audiosPort.batchAction).toHaveBeenCalledTimes(2);
    expect(ops.batchDeleting.value).toBe(false);
    expect(selected.value).toEqual([]);
  });
});
