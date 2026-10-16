import { ref, computed } from 'vue';
import { logsPort } from '../../composables/task/logsPort';
import { useModalControl } from '../../composables/modal/useModal';
import { MODAL_TYPES } from '../../composables/modal/constants';
import { useAuthStore } from '../../store/authStore';
import { PermissionPoint } from '@/domain/enums';
import { downloadBlob } from '../../utils/utils';
import type {
  LogArchiveStatus,
  LogArchiveResult,
  LogArchiveQuery,
  Log,
} from '@/domain/model/log';

/**
 * 日志归档管理面（INT-548）
 *
 * 对接后端 5 个归档端点（api_gateway/routes/log_bp.py:52-82）：
 *   GET    /logs/archive/status      归档状态（log:read）
 *   POST   /logs/archive             触发归档（log:manage）
 *   GET    /logs/archive/logs        已归档日志列表（log:read）
 *   GET    /logs/archive/{filename}  下载归档文件（log:read）
 *   DELETE /logs/archive/{filename}  删除归档文件（log:manage）
 *
 * 状态全部收敛在本 composable；LogArchivePanel.vue 为纯展示组件。
 * 操作类按钮按 log:manage 权限门控（与既有 C2 口径一致，admin 可全操作）。
 */
const EMPTY_STATUS: LogArchiveStatus = {
  totalLogs: 0,
  hotLogs: 0,
  coldLogs: 0,
  archiveDir: '',
  taskArchives: 0,
  caseArchives: 0,
  otherArchives: 0,
};

export function useLogArchive() {
  const modalManager = useModalControl();
  const authStore = useAuthStore();

  // —— 归档状态（GET /logs/archive/status） ——
  const status = ref<LogArchiveStatus>({ ...EMPTY_STATUS });
  const statusLoading = ref(false);
  const statusError = ref('');

  // —— 触发归档（POST /logs/archive） ——
  /** 保留最近 N 天热数据（后端 LogArchiveRequest 默认 7） */
  const archiveDays = ref(7);
  /** dry_run 仅预览不执行 */
  const archiveDryRun = ref(false);
  const result = ref<LogArchiveResult | null>(null);
  const resultLoading = ref(false);

  // —— 已归档日志列表（GET /logs/archive/logs） ——
  const archivedQuery = ref<LogArchiveQuery>({ taskId: undefined, testCaseId: '' });
  const archivedLogs = ref<Log[]>([]);
  const archivedTotal = ref(0);
  const archivedLoading = ref(false);
  const archivedError = ref('');

  // —— 归档文件下载/删除（{filename} 端点） ——
  /** 归档文件逻辑 key（如 task_case/493/case-1/2026-10-15.json） */
  const archiveFilename = ref('');
  const fileBusy = ref(false);

  /** 归档操作类按钮权限门控（log:manage） */
  const canManage = computed(() => authStore.hasPermission(PermissionPoint.LOG_MANAGE));

  async function loadStatus() {
    statusLoading.value = true;
    statusError.value = '';
    try {
      status.value = await logsPort.getArchiveStatus();
    } catch (error) {
      statusError.value = error instanceof Error ? error.message : String(error);
    } finally {
      statusLoading.value = false;
    }
  }

  /**
   * 触发归档：先弹确认（BASIC_CONFIRM promise 模式，onConfirm 由 resolve 驱动，
   * 规避 INT-274 onConfirm 未被容器消费的空操作缺陷），确认后调 POST。
   */
  async function triggerArchive() {
    if (!canManage.value) return;
    const days = Number(archiveDays.value) || 7;
    const dryRun = archiveDryRun.value;
    try {
      await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '确认归档',
        content: dryRun
          ? `将预览归档 ${days} 天前的冷日志（仅统计，不执行归档）。`
          : `确定要归档 ${days} 天前的冷日志吗？归档后原日志将从当前库移除。`,
        confirmText: dryRun ? '开始预览' : '确认归档',
        cancelText: '取消',
      });
    } catch {
      return; // 用户取消
    }

    resultLoading.value = true;
    try {
      const res = await logsPort.archive({ days, dryRun });
      result.value = res;
      if (!dryRun) {
        await loadStatus();
        // 归档后刷新已归档列表（保留当前查询条件）
        const rawTaskId = archivedQuery.value.taskId as number | '' | null | undefined;
        const hasTask = rawTaskId !== '' && rawTaskId !== null && rawTaskId !== undefined;
        if (hasTask || archivedQuery.value.testCaseId) {
          await queryArchivedLogs();
        }
      }
    } catch (error) {
      result.value = {
        message: error instanceof Error ? error.message : String(error),
      };
    } finally {
      resultLoading.value = false;
    }
  }

  /** 查询已归档日志：task_id / test_case_id 至少提供一个（后端 400 兜底） */
  async function queryArchivedLogs() {
    const raw = archivedQuery.value;
    // v-model.number 空输入为 ''（与 number 类型不符），此处运行时收敛为空 → 不发该条件
    const rawTaskId = raw.taskId as number | '' | null | undefined;
    const taskId = rawTaskId !== '' && rawTaskId !== null && rawTaskId !== undefined
      ? Number(rawTaskId)
      : undefined;
    const testCaseId = raw.testCaseId ? String(raw.testCaseId) : undefined;
    if (taskId === undefined && !testCaseId) {
      archivedError.value = '请先填写任务ID或用例ID';
      archivedLogs.value = [];
      archivedTotal.value = 0;
      return;
    }
    archivedLoading.value = true;
    archivedError.value = '';
    try {
      const list = await logsPort.getArchivedLogs({ taskId, testCaseId });
      archivedLogs.value = list.items;
      archivedTotal.value = list.total;
    } catch (error) {
      archivedError.value = error instanceof Error ? error.message : String(error);
      archivedLogs.value = [];
      archivedTotal.value = 0;
    } finally {
      archivedLoading.value = false;
    }
  }

  function clearArchivedQuery() {
    archivedQuery.value = { taskId: undefined, testCaseId: '' };
    archivedLogs.value = [];
    archivedTotal.value = 0;
    archivedError.value = '';
  }

  /** 下载归档文件：blob 落盘（文件名取逻辑 key 最后一段） */
  async function downloadArchive(filename: string) {
    if (!filename) return;
    fileBusy.value = true;
    try {
      const blob = await logsPort.downloadArchive(filename);
      const localName = filename.split('/').pop() || `archive-${Date.now()}.json`;
      downloadBlob(blob, localName);
    } catch (error) {
      result.value = {
        message: `下载失败: ${error instanceof Error ? error.message : String(error)}`,
      };
    } finally {
      fileBusy.value = false;
    }
  }

  /** 删除归档文件：确认后 DELETE，成功后刷新状态 */
  async function deleteArchive(filename: string) {
    if (!canManage.value || !filename) return;
    try {
      await modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
        title: '确认删除归档',
        content: `确定要删除归档文件「${filename}」吗？此操作不可撤销。`,
        confirmText: '确定删除',
        cancelText: '取消',
      });
    } catch {
      return; // 用户取消
    }

    fileBusy.value = true;
    try {
      await logsPort.deleteArchive(filename);
      archiveFilename.value = '';
      result.value = { message: `已删除归档文件: ${filename}` };
      await loadStatus();
    } catch (error) {
      result.value = {
        message: `删除失败: ${error instanceof Error ? error.message : String(error)}`,
      };
    } finally {
      fileBusy.value = false;
    }
  }

  return {
    status,
    statusLoading,
    statusError,
    archiveDays,
    archiveDryRun,
    result,
    resultLoading,
    archivedQuery,
    archivedLogs,
    archivedTotal,
    archivedLoading,
    archivedError,
    archiveFilename,
    fileBusy,
    canManage,
    loadStatus,
    triggerArchive,
    queryArchivedLogs,
    clearArchivedQuery,
    downloadArchive,
    deleteArchive,
  };
}
