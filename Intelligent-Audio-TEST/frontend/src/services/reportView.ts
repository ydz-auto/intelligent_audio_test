import { reportsApi } from '../utils/api';
import socketService from '../utils/socket';
import { MODAL_TYPES } from '../composables/modal/useModal';
import type { Report, Task } from './reportTypes';
import {
  comparisonReport,
  comparisonTasks,
  modalManager
} from './reportState';
import { extractDevicesFromTasks, updateComparisonData } from './reportComparison';
import { extractCasesFromReport } from './reportCases';

export async function viewTaskReport(task: Task): Promise<Report> {
  try {
    console.log('Viewing task report for task:', task);

    if (!task || !task.id) {
      throw new Error('任务ID无效');
    }

    const taskName = task.name || (task as { title?: string }).title || '未命名任务';
    let result = await reportsApi.generateTaskReport(task.id, `${taskName} - 测试报告`);
    console.log('generateTaskReport result:', result);

    if (result.status === 'generating') {
      socketService.connect();

      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          socketService.off('report_generated', handleReportGenerated);
          reject(new Error('报告生成超时'));
        }, 120000);

        const handleReportGenerated = async (data: any) => {
          console.log('[reportService] Received report_generated event:', data);
          if (data.taskId === task.id) {
            clearTimeout(timeout);
            socketService.off('report_generated', handleReportGenerated);

            if (!data.success) {
              reject(new Error(data.error || '报告生成失败'));
              return;
            }

            try {
              let report = await reportsApi.getOne(data.reportId);
              console.log('Got report from API:', report);

              if (!report) {
                throw new Error('无法获取报告详情');
              }

              const cases = extractCasesFromReport(report);
              const summary = report.summary || {};

              comparisonReport.value = {...comparisonReport.value,
                id: report.id,
                name: report.name || report.title,
                description: report.description || '',
                conclusion: (report.analysis || report.conclusion) || '',
                status: report.status,
                algorithm_type: report.algorithm_type || task.algorithm_type,
                created_at: report.created_at,
                updated_at: report.updated_at,
                summary: {
                  ...summary, all_metrics: summary.all_metrics || [], detailed_results: report.detailed_results || [], device_stats: summary.device_stats || [], api_stats: summary.api_stats || []
                },
                cases: cases,
                detailed_results: report.detailed_results || [],
                all_metrics: summary.all_metrics || []
              } as any;

              comparisonTasks.value = [task];
              extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);
              updateComparisonData();

              resolve(comparisonReport.value);
            } catch (err: any) {
              reject(err);
            }
          }
        };

        socketService.on('report_generated', handleReportGenerated);
      });
    }

    if (!result || !result.id) {
      throw new Error('生成报告失败，结果无效');
    }

    let report = await reportsApi.getOne(result.id);
    console.log('Got report from API:', report);

    if (!report) {
      throw new Error('无法获取报告详情');
    }

    const cases = extractCasesFromReport(report);

    const summary = report.summary || {};
    comparisonReport.value = {...comparisonReport.value,
      id: report.id,
      name: report.name || report.title,
      description: report.description || '',
      conclusion: (report.analysis || report.conclusion) || '',
      status: report.status,
      algorithm_type: report.algorithm_type || task.algorithm_type,
      created_at: report.created_at,
      updated_at: report.updated_at,
      summary: {
        ...summary, all_metrics: summary.all_metrics || [], detailed_results: report.detailed_results || [], device_stats: summary.device_stats || [], api_stats: summary.api_stats || []
      },
      cases: cases,
      detailed_results: report.detailed_results || [],
      all_metrics: summary.all_metrics || []
    } as any;

    comparisonTasks.value = [task];

    extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);

    updateComparisonData();

    return comparisonReport.value;
  } catch (error: any) {
    console.error('查看任务报告失败:', error);
    const errorMessage = error instanceof Error ? error.message : '生成报告失败，请检查任务状态';
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '报告生成失败',
      content: errorMessage,
      confirmText: '确定',
      cancelText: '关闭',
      danger: true
    });
    throw new Error(`API调用失败: ${error.message}`);
  }
}

export async function regenerateTaskReport(reportId: string | number, task: Task): Promise<Report> {
  try {
    if (!reportId) {
      throw new Error('报告ID无效');
    }

    const result = await reportsApi.regenerateReport(reportId);

    if (result.status === 'generating') {
      socketService.connect();

      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          socketService.off('report_generated', handleReportGenerated);
          reject(new Error('报告重新生成超时'));
        }, 120000);

        const handleReportGenerated = async (data: any) => {
          if (data.taskId === task.id) {
            clearTimeout(timeout);
            socketService.off('report_generated', handleReportGenerated);

            if (!data.success) {
              reject(new Error(data.error || '报告重新生成失败'));
              return;
            }

            try {
              let report = await reportsApi.getOne(data.reportId);
              if (!report) throw new Error('无法获取报告详情');

              const cases = extractCasesFromReport(report);
              const summary = report.summary || {};
              comparisonReport.value = {
                ...comparisonReport.value,
                id: report.id,
                name: report.name || report.title,
                description: report.description || '',
                conclusion: (report.analysis || report.conclusion) || '',
                status: report.status,
                algorithm_type: report.algorithm_type || task.algorithm_type,
                created_at: report.created_at,
                updated_at: report.updated_at,
                summary: {
                  ...summary,
                  all_metrics: summary.all_metrics || [],
                  detailed_results: report.detailed_results || [],
                  device_stats: summary.device_stats || [],
                  api_stats: summary.api_stats || []
                },
                cases: cases,
                detailed_results: report.detailed_results || [],
                all_metrics: summary.all_metrics || []
              } as any;

              comparisonTasks.value = [task];
              extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);
              updateComparisonData();

              resolve(comparisonReport.value);
            } catch (err: any) {
              reject(err);
            }
          }
        };

        socketService.on('report_generated', handleReportGenerated);
      });
    }

    if (!result || !result.id) {
      throw new Error('重新生成报告失败，结果无效');
    }

    let report = await reportsApi.getOne(result.id);
    if (!report) throw new Error('无法获取报告详情');

    const cases = extractCasesFromReport(report);
    const summary = report.summary || {};
    comparisonReport.value = {
      ...comparisonReport.value,
      id: report.id,
      name: report.name || report.title,
      description: report.description || '',
      conclusion: (report.analysis || report.conclusion) || '',
      status: report.status,
      algorithm_type: report.algorithm_type || task.algorithm_type,
      created_at: report.created_at,
      updated_at: report.updated_at,
      summary: {
        ...summary,
        all_metrics: summary.all_metrics || [],
        detailed_results: report.detailed_results || [],
        device_stats: summary.device_stats || [],
        api_stats: summary.api_stats || []
      },
      cases: cases,
      detailed_results: report.detailed_results || [],
      all_metrics: summary.all_metrics || []
    } as any;

    comparisonTasks.value = [task];
    extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);
    updateComparisonData();

    return comparisonReport.value;
  } catch (error: any) {
    console.error('Failed to regenerate task report:', error);
    throw new Error(`重新生成报告失败: ${error.message}`);
  }
}

export async function batchCompare(taskIds: (string | number)[], tasks: Task[]): Promise<Report> {
  try {
    const taskNames = tasks.map(task => task.name || (task as { title?: string }).title || '未命名任务').join('_');
    const result = await reportsApi.compare(taskIds, `任务对比报告_${taskNames}_${new Date().getTime()}`);

    const reportId = (result as any)?.id ?? (result as any)?.reportId;
    if (!reportId) {
      throw new Error('对比报告生成失败');
    }

    let report = await reportsApi.getOne(reportId);
    if (!report) {
      throw new Error('获取对比报告详情失败');
    }

    const cases = extractCasesFromReport(report);

    const summary = report.summary || {};

    if (summary.overall_success_rate !== undefined && summary.pass_rate === undefined) {
      summary.pass_rate = summary.overall_success_rate;
    }

    const dimension_values = summary.dimension_values;
    if (dimension_values) {
      const findValue = (names: string[]) => {
        for (const name of names) {
          if (dimension_values[name] !== undefined) return dimension_values[name];
        }
        return undefined;
      };

      if (summary.stability === undefined) {
        summary.stability = findValue(['稳定性', 'Stability', 'stability']) || 0;
      }

      if (summary.avg_response_time === undefined) {
        summary.avg_response_time = findValue(['平均响应时间', 'Avg Response Time', 'avg_response_time', 'Response Time']) || 0;
      }
    }

    comparisonReport.value = {...comparisonReport.value,
      id: report.id,
      name: report.name || report.title,
      description: report.description || '',
      conclusion: (report.analysis || report.conclusion) || '',
      status: report.status,
      algorithm_type: report.algorithm_type,
      updated_at: report.updated_at,
      summary: summary,
      cases: cases,
      detailed_results: report.detailed_results || [],
      all_metrics: summary.all_metrics || []
    } as any;

    comparisonTasks.value = [...tasks];

    extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);

    return comparisonReport.value;
  } catch (error) {
    console.error('批量对比任务失败:', error);
    throw error;
  }
}
