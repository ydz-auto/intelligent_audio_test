import { ref, computed, type Ref } from 'vue';
import { reportService } from '../services/reportService';
import type { Task } from '../shared/types';

/**
 * 任务报告编辑组合式函数
 *
 * 职责：
 * - 编辑结论（开始/保存/切换/取消）
 * - 编辑报告（切换/取消）
 * - 报告保存/发布/关闭
 * - 报告相关计算属性（名称、结论、设备、数据）
 */

export function useTaskReport(
  tasks: Ref<Task[]>,
  selectedTasks: Ref<Set<string | number>>
) {
  const isEditingReport = ref(false);
  const isEditingConclusion = ref(false);

  const reportConclusion = computed({
    get: () => {
      const report = reportService.comparisonReport.value;
      return report?.conclusion || '';
    },
    set: (val) => {
      const report = reportService.comparisonReport.value;
      if (report) {
        report.conclusion = val;
      }
    }
  });

  const reportName = computed({
    get: () => {
      const report = reportService.comparisonReport.value;
      return report?.title || report?.name || '';
    },
    set: (val) => {
      const report = reportService.comparisonReport.value;
      if (report) {
        report.title = val;
        report.name = val;
      }
    }
  });

  const reportDevices = computed(() => reportService.devices.value || []);
  const reportServiceData = computed(() => reportService.comparisonReport.value);

  const showComparisonReport = computed(() => reportService.comparisonTasks.value.length > 0);
  const comparisonTasks = computed(() => reportService.comparisonTasks.value);
  const comparisonReport = computed(() => reportService.comparisonReport.value);

  const {
    deviceApiColumns,
    caseExecutionColumns,
    extractDevicesFromTasks,
    updateComparisonData,
    toggleDeviceSelection,
    deviceApiComparisonData,
    caseExecutionData,
    updateComparisonReportConclusion
  } = reportService;

  const closeComparisonReport = () => {
    reportService.comparisonTasks.value = [];
    reportService.comparisonReport.value = {
      id: '',
      name: '任务对比报告',
      type: 'comparison',
      status: 'draft',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      description: '',
      summary: {
        totalCases: 0,
        passedCases: 0,
        failedCases: 0,
        passRate: 0,
        avgScore: 0,
        completedCases: 0,
        allMetrics: [],
        detailedResults: [],
        deviceStats: [],
        apiStats: []
      }
    } as any;
  };

  const saveComparisonReport = async () => {
    try {
      if (reportService.comparisonReport.value) {
        await reportService.saveReport(reportService.comparisonReport.value);
        alert('报告已保存');
      }
    } catch (error) {
      console.error('Failed to save report:', error);
    }
  };

  const publishComparisonReport = async () => {
    try {
      if (reportService.comparisonReport.value?.id) {
        await reportService.publishReport(reportService.comparisonReport.value.id);
        alert('报告已发布');
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
      await reportService.updateComparisonReportConclusion(selectedTasksArray);
      if (reportService.comparisonReport.value) {
        await reportService.saveReport(reportService.comparisonReport.value);
      }
      isEditingConclusion.value = false;
    } catch (error: any) {
      console.error('Failed to save conclusion:', error);
      alert('结论保存失败: ' + (error.message || '未知错误'));
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
