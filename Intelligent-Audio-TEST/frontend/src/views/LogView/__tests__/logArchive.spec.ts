/**
 * INT-548 useLogArchive composable 契约测试
 *
 * 覆盖归档面板核心动作：
 * - 权限门控（log:manage）对触发/删除的约束
 * - loadStatus / triggerArchive（确认后 POST，取消不发请求）
 * - queryArchivedLogs（缺查询条件不发请求；有条件调 GET）
 * - deleteArchive（确认后 DELETE + 刷新状态）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/composables/task/logsPort', () => ({
  logsPort: {
    getArchiveStatus: vi.fn(),
    archive: vi.fn(),
    getArchivedLogs: vi.fn(),
    downloadArchive: vi.fn(),
    deleteArchive: vi.fn(),
  },
}));

const { modalControl } = vi.hoisted(() => ({
  modalControl: {
    open: vi.fn(),
    close: vi.fn(),
    closeAll: vi.fn(),
    getActiveModals: vi.fn(() => []),
    updateModalProps: vi.fn(),
    registerModal: vi.fn(),
  },
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => modalControl,
}));

import { useLogArchive } from '../logArchive';
import { logsPort } from '@/composables/task/logsPort';
import { useAuthStore } from '@/store/authStore';
import { createPinia, setActivePinia } from 'pinia';

const mockedPort = vi.mocked(logsPort);
const mockedOpen = modalControl.open;

const STATUS_DTO = {
  totalLogs: 100,
  hotLogs: 60,
  coldLogs: 40,
  archiveDir: 'oss://archives',
  taskArchives: 3,
  caseArchives: 2,
  otherArchives: 1,
};

beforeEach(() => {
  setActivePinia(createPinia());
  mockedPort.getArchiveStatus.mockReset();
  mockedPort.archive.mockReset();
  mockedPort.getArchivedLogs.mockReset();
  mockedPort.downloadArchive.mockReset();
  mockedPort.deleteArchive.mockReset();
  mockedOpen.mockReset();
  // 默认确认通过
  mockedOpen.mockResolvedValue({ confirmed: true, checkboxValue: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function setPermissions(permissions: string[]) {
  useAuthStore().setAuth('t', {
    id: 1,
    username: 'u',
    roleId: null,
    roleName: '',
    permissions,
  });
}

describe('权限门控', () => {
  it('无 log:manage 时 canManage=false', () => {
    setPermissions(['log:read']);
    expect(useLogArchive().canManage.value).toBe(false);
  });

  it('admin（* 通配）canManage=true', () => {
    setPermissions(['*']);
    expect(useLogArchive().canManage.value).toBe(true);
  });

  it('仅 log:manage 也可操作', () => {
    setPermissions(['log:manage']);
    expect(useLogArchive().canManage.value).toBe(true);
  });
});

describe('归档状态', () => {
  it('loadStatus 拉取并映射状态', async () => {
    setPermissions(['*']);
    mockedPort.getArchiveStatus.mockResolvedValue(STATUS_DTO as any);
    const view = useLogArchive();
    await view.loadStatus();
    expect(mockedPort.getArchiveStatus).toHaveBeenCalledTimes(1);
    expect(view.status.value.totalLogs).toBe(100);
    expect(view.status.value.taskArchives).toBe(3);
  });

  it('loadStatus 失败写入 statusError 且不抛', async () => {
    setPermissions(['*']);
    mockedPort.getArchiveStatus.mockRejectedValue(new Error('网关不可达'));
    const view = useLogArchive();
    await view.loadStatus();
    expect(view.statusError.value).toContain('网关不可达');
  });
});

describe('触发归档（POST /logs/archive）', () => {
  it('确认后调用 archive，dry_run 传递正确', async () => {
    setPermissions(['*']);
    // logsPort.archive 已由 logsApi 映射为 camelCase Domain
    mockedPort.archive.mockResolvedValue({ message: '将归档 42 条日志', coldLogsCount: 42, cutoffDate: '' } as any);
    const view = useLogArchive();
    view.archiveDays.value = 7;
    view.archiveDryRun.value = true;
    await view.triggerArchive();
    expect(mockedOpen).toHaveBeenCalledWith('basicConfirm', expect.objectContaining({ title: '确认归档' }));
    expect(mockedPort.archive).toHaveBeenCalledWith({ days: 7, dryRun: true });
    expect(view.result.value?.coldLogsCount).toBe(42);
    // dry_run 不刷新状态
    expect(mockedPort.getArchiveStatus).not.toHaveBeenCalled();
  });

  it('确认后真实归档会刷新状态与已归档列表', async () => {
    setPermissions(['*']);
    mockedPort.archive.mockResolvedValue({ archivedCount: 30, remainingCount: 999 } as any);
    mockedPort.getArchiveStatus.mockResolvedValue(STATUS_DTO as any);
    mockedPort.getArchivedLogs.mockResolvedValue({ items: [], total: 0, source: 'archive' } as any);
    const view = useLogArchive();
    view.archiveDays.value = 30;
    view.archiveDryRun.value = false;
    view.archivedQuery.value = { taskId: 493, testCaseId: '' };
    await view.triggerArchive();
    expect(mockedPort.archive).toHaveBeenCalledWith({ days: 30, dryRun: false });
    expect(mockedPort.getArchiveStatus).toHaveBeenCalled();
    expect(mockedPort.getArchivedLogs).toHaveBeenCalledWith({ taskId: 493, testCaseId: undefined });
  });

  it('用户取消确认时不发请求', async () => {
    setPermissions(['*']);
    mockedOpen.mockRejectedValue(new Error('cancelled'));
    const view = useLogArchive();
    await view.triggerArchive();
    expect(mockedPort.archive).not.toHaveBeenCalled();
  });

  it('无 log:manage 权限时直接返回不发请求', async () => {
    setPermissions(['log:read']);
    const view = useLogArchive();
    await view.triggerArchive();
    expect(mockedOpen).not.toHaveBeenCalled();
    expect(mockedPort.archive).not.toHaveBeenCalled();
  });
});

describe('已归档日志查询（GET /logs/archive/logs）', () => {
  it('缺少 task_id 与 test_case_id 时不发请求', async () => {
    setPermissions(['*']);
    const view = useLogArchive();
    view.archivedQuery.value = { taskId: undefined, testCaseId: '' };
    await view.queryArchivedLogs();
    expect(mockedPort.getArchivedLogs).not.toHaveBeenCalled();
    expect(view.archivedError.value).toContain('任务ID或用例ID');
  });

  it('按 taskId 查询并填充列表', async () => {
    setPermissions(['*']);
    mockedPort.getArchivedLogs.mockResolvedValue({
      items: [{ id: 1, taskId: 493, level: 'error', content: 'boom' }],
      total: 1,
      source: 'archive',
    } as any);
    const view = useLogArchive();
    view.archivedQuery.value = { taskId: 493, testCaseId: '' };
    await view.queryArchivedLogs();
    expect(mockedPort.getArchivedLogs).toHaveBeenCalledWith({ taskId: 493, testCaseId: undefined });
    expect(view.archivedLogs.value).toHaveLength(1);
    expect(view.archivedTotal.value).toBe(1);
  });
});

describe('归档文件操作', () => {
  it('deleteArchive 确认后 DELETE 并刷新状态', async () => {
    setPermissions(['*']);
    mockedPort.deleteArchive.mockResolvedValue(undefined as any);
    mockedPort.getArchiveStatus.mockResolvedValue(STATUS_DTO as any);
    const view = useLogArchive();
    await view.deleteArchive('task_case/493/case-1/2026-10-15.json');
    expect(mockedOpen).toHaveBeenCalledWith('deleteConfirm', expect.objectContaining({ title: '确认删除归档' }));
    expect(mockedPort.deleteArchive).toHaveBeenCalledWith('task_case/493/case-1/2026-10-15.json');
    expect(mockedPort.getArchiveStatus).toHaveBeenCalled();
  });

  it('downloadArchive 将 blob 落盘（filename 取逻辑 key 最后段）', async () => {
    setPermissions(['*']);
    const blob = new Blob(['{}'], { type: 'application/json' });
    mockedPort.downloadArchive.mockResolvedValue(blob as any);
    const createObjectURL = vi.fn(() => 'blob:fake');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', {
      createObjectURL,
      revokeObjectURL,
    });
    const view = useLogArchive();
    await view.downloadArchive('task_case/493/case-1/2026-10-15.json');
    expect(mockedPort.downloadArchive).toHaveBeenCalledWith('task_case/493/case-1/2026-10-15.json');
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake');
  });
});
