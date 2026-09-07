import { ref, computed, type Ref } from 'vue';
import {
  extractDevicesFromTasks,
  updateComparisonData,
  toggleDeviceSelection,
  updateComparisonReportConclusion,
  saveReport as saveReportApi,
  publishReport as publishReportApi,
  resetReportState,
} from '../report/useReportComparison';
import {
  comparisonReport,
  comparisonTasks,
  comparisonDevices,
  deviceApiColumns,
  caseExecutionColumns,
  deviceApiComparisonData,
  caseExecutionData,
} from '../../store/reportComparisonStore';
import { useNotification } from '../modal/useNotification';
import type { Task } from '../../domain';
/**
 * 任务报告编辑组合式函数
 *
 * 职责：
 * - 编辑结论（开始/保存/切换/取消）
 * - 编辑报告（切换/取消）
 * - 报告保存/发布/关闭
 * - 报告相关计算属性（名称、结论、设备、数据）
 *
 * 对比报告 ReadModel 来自 composables/report/useReportComparison（模块级单例）。
 */

export function useTaskReport(
  tasks: Ref<Task[]>,
  selectedTasks: Ref<Set<string | number>>
) {
  const notification = useNotification();
  const isEditingReport = ref(false);
  const isEditingConclusion = ref(false);

  const reportConclusion = computed({
    get: () => comparisonReport.value?.conclusion || '',
    set: (val) => {
      if (comparisonReport.value) {
        comparisonReport.value.conclusion = val;
      }
    }
  });

  const reportName = computed({
    get: () => comparisonReport.value?.title || comparisonReport.value?.name || '',
    set: (val) => {
      if (comparisonReport.value) {
        comparisonReport.value.title = val;
        comparisonReport.value.name = val;
      }
    }
  });

  const reportDevices = computed(() => comparisonDevices.value || []);
  const reportServiceData = computed(() => comparisonReport.value);

  const showComparisonReport = computed(() => comparisonTasks.value.length > 0);

  const closeComparisonReport = () => {
    resetReportState();
  };

  const saveComparisonReport = async () => {
    try {
      if (comparisonReport.value) {
        await saveReportApi(comparisonReport.value);
        notification.success('报告已保存');
      }
    } catch (error) {
      console.error('Failed to save report:', error);
    }
  };

  const publishComparisonReport = async () => {
    try {
      if (comparisonReport.value?.id) {
        await publishReportApi(comparisonReport.value.id);
        notification.success('报告已发布');
      }
    } catch (error) {
      console.error('Failed to publish report:', error);
    }
  };

  const startEditingConclusion = () => {
    isEditingConclusion.value = true;
  };

  const saveConclusion = async () => {
    try {
      const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
      await updateComparisonReportConclusion(selectedTasksArray);
      if (comparisonReport.value) {
        await saveReportApi(comparisonReport.value);
      }
      isEditingConclusion.value = false;
    } catch (error: any) {
      console.error('Failed to save conclusion:', error);
      notification.error('结论保存失败: ' + (error.message || '未知错误'));
    }
  };

  const toggleEditConclusion = () => {
    isEditingConclusion.value = !isEditingConclusion.value;
  };

  const cancelEditConclusion = () => {
    isEditingConclusion.value = false;
  };

  const toggleEditReport = () => {
    isEditingReport.value = !isEditingReport.value;
  };

  const cancelEditReport = () => {
    isEditingReport.value = false;
  };

  return {
    isEditingReport,
    isEditingConclusion,
    reportConclusion,
    reportName,
    reportDevices,
    reportServiceData,
    showComparisonReport,
    comparisonTasks,
    comparisonReport,
    deviceApiColumns,
    caseExecutionColumns,
    extractDevicesFromTasks,
    updateComparisonData,
    toggleDeviceSelection,
    deviceApiComparisonData,
    caseExecutionData,
    updateComparisonReportConclusion,
    closeComparisonReport,
    saveComparisonReport,
    publishComparisonReport,
    startEditingConclusion,
    saveConclusion,
    toggleEditConclusion,
    cancelEditConclusion,
    toggleEditReport,
    cancelEditReport,
  };
}
