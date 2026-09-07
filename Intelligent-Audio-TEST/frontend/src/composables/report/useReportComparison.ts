import { reportsPort } from './reportsPort';
import socketService from '../../utils/socket';
import { MODAL_TYPES, useModalControl } from '../modal/useModal';
import type { Report, Task, ComparisonDevice, DeviceAPIComparisonItem, CaseExecutionItem } from '../../domain/model';
import { TaskStatus, ReportStatus } from '../../domain/enums';
import {
  getTaskStatusLabel,
  getReportTypeLabel,
} from '../../domain/constants/reportLabels';
import {
  comparisonReport,
  comparisonTasks,
  comparisonDevices,
  deviceApiComparisonData,
  caseExecutionData,
  createDefaultReport,
} from '../../store/reportComparisonStore';

/**
 * 报告对比用例编排（Application 层）
 *
 * 职责：
 * - 生成/重新生成/批量对比任务报告（含 socket 异步等待）
 * - 从任务与报告中提取资源并构建对比 ReadModel
 * - 报告保存/导出/发布
 * - 对比结论生成与状态重置
 *
 * 状态承载于 store/reportComparisonStore.ts（模块级单例）。
 */

// ===== 常量（消除魔法数字/魔法字符串） =====
/** 报告异步生成超时时间（ms） */
const REPORT_GENERATE_TIMEOUT_MS = 120_000;
/** socket 报告生成完成事件名 */
const REPORT_GENERATED_EVENT = 'report_generated';

/** 后端 resultStatus 协议值「评估通过」（原始协议值，domain 枚举未收录；adapter 出口 executionStatus 已归一化，此处仅兜底旧数据来源） */
const RESULT_STATUS_PASSED = 'passed';

/** 模块级弹窗管理单例（报告失败提示用） */
const modalManager = useModalControl();

// ===== 内部工具：报告详情 → 对比 ReadModel =====

/**
 * 将后端报告详情合并进对比报告 ReadModel
 * 统一 viewTaskReport/regenerateTaskReport/batchCompare 三处重复的填充逻辑
 */
function buildComparisonReport(report: Report, task?: Task): Report {
  // summary 为后端聚合结构的宽松读取（动态指标名不做 camelCase 转换）
  const summary = (report.summary || {}) as Record<string, any>;
  return {
    ...comparisonReport.value,
    id: report.id,
    name: report.name || report.title,
    description: report.description || '',
    conclusion: report.conclusion || '',
    status: report.status,
    algorithmType: report.algorithmType || task?.algorithmType,
    createdAt: report.createdAt,
    updatedAt: report.updatedAt,
    summary: {
      ...summary,
      allMetrics: summary.allMetrics || [],
      detailedResults: report.detailedResults || [],
      deviceStats: summary.deviceStats || [],
      apiStats: summary.apiStats || []
    },
    cases: extractCasesFromReport(report),
    detailedResults: report.detailedResults || [],
    allMetrics: summary.allMetrics || []
  } as Report;
}

/**
 * 等待 socket「报告生成完成」事件，返回 reportId
 * 超时或失败抛错（文案由调用方区分生成/重新生成场景）
 */
function waitForReportGenerated(
  taskId: string | number,
  timeoutMessage: string,
  failureFallbackMessage: string
): Promise<string | number> {
  return new Promise((resolve, reject) => {
    socketService.connect();

    const timeout = setTimeout(() => {
      socketService.off(REPORT_GENERATED_EVENT, handleReportGenerated);
      reject(new Error(timeoutMessage));
    }, REPORT_GENERATE_TIMEOUT_MS);

    const handleReportGenerated = (data: any) => {
      if (data.taskId === taskId) {
        clearTimeout(timeout);
        socketService.off(REPORT_GENERATED_EVENT, handleReportGenerated);

        if (!data.success) {
          reject(new Error(data.error || failureFallbackMessage));
          return;
        }
        resolve(data.reportId);
      }
    };

    socketService.on(REPORT_GENERATED_EVENT, handleReportGenerated);
  });
}

/** 生成接口返回 generating 时等待完成并取详情，否则直接取详情 */
async function resolveGeneratedReport(
  result: { status?: string; id?: string | number },
  taskId: string | number,
  messages: { timeout: string; failure: string; invalid: string }
): Promise<Report> {
  let reportId: string | number | undefined;
  if (result.status === ReportStatus.GENERATING) {
    reportId = await waitForReportGenerated(taskId, messages.timeout, messages.failure);
  } else {
    if (!result?.id) {
      throw new Error(messages.invalid);
    }
    reportId = result.id;
  }

  const report = await reportsPort.getOne(reportId);
  if (!report) {
    throw new Error('无法获取报告详情');
  }
  return report;
}

// ===== 内部工具：报告 → 用例列表（原 services/reportCases） =====

/** 将 detailedResults 按用例聚合为展示用例列表 */
function convertDetailedResultsToCases(report: any): any[] {
  const detailedResults = report.detailedResults || [];
  if (detailedResults.length === 0) return [];

  const casesMap = new Map();

  detailedResults.forEach((result: any) => {
    const testCaseId = result.testCaseId;
    if (!testCaseId) return;

    if (!casesMap.has(testCaseId)) {
      const caseObj: any = {
        id: testCaseId,
        name: result.testCaseName || '未命名用例',
        description: '',
        category: '',
        tags: [],
        metrics: {},
        results: {},
        audio: {
          id: result.audioId || '',
          name: result.audioName || '',
          filePath: result.audioFilePath || '',
          duration: result.audioDuration || 0
        },
        asr: { referenceText: result.asr?.referenceText || '', results: {} },
        translation: { referenceText: result.translation?.referenceText || '', results: {} },
        logs: result.errorMessage || ''
      };
      casesMap.set(testCaseId, caseObj);
    }

    const caseObj = casesMap.get(testCaseId);

    // 资源键 = 资源ID_资源名（设备或 API）
    const device = result.device;
    const api = result.api;
    const resourceName = device ? device.name : (api ? api.name : '默认资源');
    const resourceId = device?.id || api?.id || 'default';
    const resourceKey = `${resourceId}_${resourceName}`;

    caseObj.metrics[resourceKey] = {};
    const dimensionScores = result.dimensionScores || [];
    dimensionScores.forEach((dim: any) => {
      const dimName = dim.dimensionName;
      if (dimName) {
        caseObj.metrics[resourceKey][dimName] = dim.score;
      }
    });

    const status = result.executionStatus || result.status;
    caseObj.results[resourceKey] = {
      status: status === TaskStatus.COMPLETED || status === RESULT_STATUS_PASSED ? '成功' : '失败',
      startTime: result.createdAt,
      endTime: result.createdAt
    };

    caseObj.asr.results[resourceKey] = { text: result.asr?.resultText || '' };
    caseObj.translation.results[resourceKey] = { text: result.translation?.resultText || '' };
  });

  return Array.from(casesMap.values());
}

/** 提取报告用例：优先 report.cases，其次 summary.cases，最后从 detailedResults 聚合 */
function extractCasesFromReport(report: any): any[] {
  if (report.cases && report.cases.length > 0) {
    return report.cases;
  } else if (report.summary?.cases && report.summary.cases.length > 0) {
    return report.summary.cases;
  } else {
    return convertDetailedResultsToCases(report);
  }
}

// ===== 用例：报告生成 =====

/** 查看任务报告：触发生成（必要时等待 socket），并写入对比 ReadModel */
export async function viewTaskReport(task: Task): Promise<Report> {
  if (!task || !task.id) {
    throw new Error('任务ID无效');
  }

  try {
    const taskName = task.name || (task as { title?: string }).title || '未命名任务';
    const result = await reportsPort.generateTaskReport(task.id, `${taskName} - 测试报告`);

    const report = await resolveGeneratedReport(result, task.id, {
      timeout: '报告生成超时',
      failure: '报告生成失败',
      invalid: '生成报告失败，结果无效'
    });

    comparisonReport.value = buildComparisonReport(report, task);
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

/** 重新生成任务报告并写入对比 ReadModel */
export async function regenerateTaskReport(reportId: string | number, task: Task): Promise<Report> {
  if (!reportId) {
    throw new Error('报告ID无效');
  }

  const result = await reportsPort.regenerateReport(reportId);
  const report = await resolveGeneratedReport(result, task.id, {
    timeout: '报告重新生成超时',
    failure: '报告重新生成失败',
    invalid: '重新生成报告失败，结果无效'
  });

  comparisonReport.value = buildComparisonReport(report, task);
  comparisonTasks.value = [task];
  extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);
  updateComparisonData();

  return comparisonReport.value;
}

/** 批量对比多个任务：生成对比报告并写入 ReadModel */
export async function batchCompare(taskIds: (string | number)[], tasks: Task[]): Promise<Report> {
  try {
    const taskNames = tasks
      .map(task => task.name || (task as { title?: string }).title || '未命名任务')
      .join('_');
    const result = await reportsPort.compare(taskIds, `任务对比报告_${taskNames}_${new Date().getTime()}`);

    const reportId = (result as any)?.id ?? (result as any)?.reportId;
    if (!reportId) {
      throw new Error('对比报告生成失败');
    }

    const report = await reportsPort.getOne(reportId);
    if (!report) {
      throw new Error('获取对比报告详情失败');
    }

    // 兼容旧字段：overallSuccessRate → passRate（dimensionValues 内指标名为后端原始 key，不做转换）
    const summary = (report.summary || {}) as Record<string, any>;
    if (summary.overallSuccessRate !== undefined && summary.passRate === undefined) {
      summary.passRate = summary.overallSuccessRate;
    }

    const dimensionValues = summary.dimensionValues;
    if (dimensionValues) {
      const findValue = (names: string[]) => {
        for (const name of names) {
          if (dimensionValues[name] !== undefined) return dimensionValues[name];
        }
        return undefined;
      };

      if (summary.stability === undefined) {
        summary.stability = findValue(['稳定性', 'Stability', 'stability']) || 0;
      }

      if (summary.avgResponseTime === undefined) {
        summary.avgResponseTime = findValue(['平均响应时间', 'Avg Response Time', 'avg_response_time', 'Response Time']) || 0;
      }
    }

    comparisonReport.value = buildComparisonReport(report);
    comparisonTasks.value = [...tasks];
    extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);

    return comparisonReport.value;
  } catch (error) {
    console.error('批量对比任务失败:', error);
    throw error;
  }
}

// ===== 用例：报告持久化 =====

/** 保存对比报告（仅允许更新已存在的报告） */
export async function saveReport(reportData: Partial<Report>): Promise<Report> {
  if (reportData.id) {
    return await reportsPort.update(reportData.id, reportData);
  }
  throw new Error('报告不存在，无法保存。请先通过任务报告或批量对比生成报告。');
}

/** 导出报告为指定格式（默认 excel） */
export async function exportReport(reportId: string | number, format = 'excel'): Promise<Blob> {
  return await reportsPort.export([reportId], format);
}

/** 发布报告 */
export async function publishReport(reportId: string | number): Promise<any> {
  return await reportsPort.publish(reportId);
}

// ===== 编排：资源提取与对比数据构建（原 services/reportComparison） =====

/**
 * 从任务与报告中提取设备/API 资源列表，写入 comparisonDevices
 * 数据优先级：任务关联资源 > 报告 deviceStats/apiStats > 报告 summary.devices/apis
 */
export function extractDevicesFromTasks(tasks: Task[], report?: Report): ComparisonDevice[] {
  const extractedDevices: ComparisonDevice[] = [];

  tasks.forEach(task => {
    const taskDevices = [
      ...((task as any).devices || []),
      ...(task.config?.devices || [])
    ];

    const taskApis = [
      ...((task as any).apis || []),
      ...(task.config?.apis || [])
    ];

    taskDevices.forEach(res => {
      if (res && !extractedDevices.find(d => d.id === res.id)) {
        extractedDevices.push({
          id: res.id,
          name: res.name || 'Unknown Device',
          type: '设备',
          selected: true
        });
      }
    });

    taskApis.forEach(res => {
      if (res && !extractedDevices.find(d => d.id === res.id)) {
        extractedDevices.push({
          id: res.id,
          name: res.name || 'Unknown API',
          type: 'API',
          selected: true
        });
      }
    });
  });

  if (report) {
    const deviceStats = report.summary?.deviceStats || [];
    deviceStats.forEach((stat: Record<string, any>) => {
      if (!extractedDevices.find(d => d.id === stat.id || d.name === stat.name)) {
        extractedDevices.push({
          id: stat.id || `device-${Math.random().toString(36).slice(2, 11)}`,
          name: stat.name,
          type: '设备',
          selected: true
        });
      }
    });

    const apiStats = report.summary?.apiStats || [];
    apiStats.forEach((stat: Record<string, any>) => {
      if (!extractedDevices.find(d => d.id === stat.id || d.name === stat.name)) {
        extractedDevices.push({
          id: stat.id || `api-${Math.random().toString(36).slice(2, 11)}`,
          name: stat.name,
          type: 'API',
          selected: true
        });
      }
    });

    const reportDevices = report.summary?.devices || [];
    reportDevices.forEach(device => {
      const deviceName = typeof device === 'string' ? device : device.name;

      if (deviceName && !extractedDevices.find(d => d.name === deviceName)) {
        extractedDevices.push({
          id: typeof device === 'string'
            ? `device-${deviceName.toLowerCase().replace(/\s+/g, '-')}`
            : (device.id || `device-${Math.random().toString(36).slice(2, 11)}`),
          name: deviceName,
          type: '设备',
          selected: true
        });
      }
    });

    const reportAPIs = report.summary?.apis || [];
    reportAPIs.forEach(api => {
      const apiName = typeof api === 'string' ? api : api.name;

      if (apiName && !extractedDevices.find(d => d.name === apiName)) {
        extractedDevices.push({
          id: typeof api === 'string'
            ? `api-${apiName.toLowerCase().replace(/\s+/g, '-')}`
            : (api.id || `api-${Math.random().toString(36).slice(2, 11)}`),
          name: apiName,
          type: 'API',
          selected: true
        });
      }
    });
  }

  if (extractedDevices.length === 0) {
    console.warn('No devices or APIs found in tasks or report');
  }

  comparisonDevices.value = extractedDevices;
  updateComparisonData(tasks, report);

  return extractedDevices;
}

/**
 * 从 summary.metricData 按资源名/ID 匹配 WER 指标，计算稳定性
 * （WER 均值 → 稳定性 = 100 - WER；无数据返回 0）
 */
function computeStabilityFromMetricData(
  report: Report,
  resource: { id: string | number; name: string }
): { stability: number; matched: boolean } {
  let metricCount = 0;
  let werSum = 0;

  const metricGroups = (report.summary?.metricData || []) as any[];
  const resourceName = String(resource.name || '').toLowerCase();
  const resourceId = String(resource.id || '').toLowerCase();

  metricGroups.forEach((group) => {
    if (!group) return;
    const groupResource = String(group.resource || '').toLowerCase();
    const matched =
      (resourceId && groupResource.includes(`${resourceId}-`)) ||
      (resourceName && groupResource.includes(resourceName));
    if (!matched) return;

    const categories = Array.isArray(group.categories) ? group.categories : [];
    categories.forEach((c: any) => {
      const metrics = Array.isArray(c?.metrics) ? c.metrics : [];
      const wer = metrics.find((m: any) => m && m.metric === 'WER');
      if (wer) {
        werSum += Number(wer.value || 0);
        metricCount++;
      }
    });
  });

  if (metricCount === 0) return { stability: 0, matched: false };
  return { stability: Math.max(0, 100 - werSum / metricCount), matched: true };
}

/** 统计任务侧（任务无统计字段时的兜底）：累加任务总用例数 */
function accumulateTaskCases(tasks: Task[], target: { id: string | number; name: string }): { totalCases: number; completedCases: number } {
  let totalCases = 0;
  let completedCases = 0;
  tasks.forEach(task => {
    const matched =
      (task as any).devices?.find((device: any) => device.id === target.id || device.name === target.name) ||
      (task as any).apis?.find((api: any) => api.id === target.id || api.name === target.name);
    if (matched) {
      totalCases += task.totalCases || 0;
      completedCases += (task.completedCases || 0) - (task.failedCases || 0);
    }
  });
  return { totalCases, completedCases };
}

/** 构建单个资源的指标对比行 */
function buildDeviceApiItem(
  device: ComparisonDevice,
  report: Report | undefined,
  tasks: Task[]
): DeviceAPIComparisonItem {
  let totalCases = 0;
  let completedCases = 0;
  let avgResponseTime = 0;
  let stability = 0;

  if (report?.summary) {
    const isDevice = device.type === '设备';
    // 设备走 deviceStats，API 走 apiStats
    const stats = isDevice ? report.summary.deviceStats || [] : report.summary.apiStats || [];
    const stat: Record<string, any> | undefined = stats.find(
      (s: Record<string, any>) => s.id === device.id || s.name === device.name
    );

    if (stat) {
      totalCases = stat.totalCases || 0;
      completedCases = stat.completedCases || 0;

      if (isDevice) {
        // 设备统计：动态指标名走宽松索引读取（后端原始 key）
        const statAny = stat as unknown as Record<string, unknown>;
        const metrics = (stat.metrics ?? {}) as Record<string, unknown>;
        const getMetric = (names: string[]) => {
          for (const name of names) {
            if (statAny[name] !== undefined) return statAny[name];
          }
          for (const name of names) {
            if (metrics[name] !== undefined) return metrics[name];
          }
          return 0;
        };
        avgResponseTime = Number(getMetric(['avgResponseTime', 'averageResponseTime', '平均响应时间'])) || 0;
        stability = Number(getMetric(['stability', '稳定性', 'Stability'])) || 0;
      } else {
        avgResponseTime = stat.avgResponseTime || 0;
        stability = stat.stability || 0;
      }
    } else {
      // 无资源级统计：回退报告汇总 + metricData WER 推算
      totalCases = report.summary.totalCases || 0;
      completedCases = report.summary.completedCases || 0;
      const werResult = computeStabilityFromMetricData(report, { id: device.id, name: device.name });
      if (werResult.matched) {
        stability = werResult.stability;
      }
    }
  }

  // 报告无数据时回退任务统计
  if (totalCases === 0) {
    const taskCases = accumulateTaskCases(tasks, { id: device.id, name: device.name });
    totalCases = taskCases.totalCases;
    completedCases = taskCases.completedCases;
  }

  if (totalCases === 0 && report?.summary) {
    totalCases = report.summary.totalCases || 0;
    completedCases = report.summary.completedCases || 0;
  }

  return {
    id: device.id,
    name: device.name,
    type: device.type,
    version: (device as any).version || '',
    status: report?.status || TaskStatus.COMPLETED,
    totalCases,
    successRate: totalCases ? Math.round((completedCases / totalCases) * 100) : 0,
    avgResponseTime,
    stability
  };
}

/** 构建用例执行统计行（报告维度或任务维度） */
function buildCaseExecutionRows(report: Report | undefined, tasks: Task[]): CaseExecutionItem[] {
  if (report) {
    const rows: CaseExecutionItem[] = [];
    const detailedResults = report.detailedResults || [];
    const totalCasesCount = detailedResults.length;
    const completedCasesCount = detailedResults.filter((result: any) =>
      result.status === TaskStatus.COMPLETED || result.status === RESULT_STATUS_PASSED
    ).length;

    rows.push({
      id: 'total',
      name: '全部用例',
      total: totalCasesCount,
      executed: totalCasesCount,
      completed: completedCasesCount,
      failed: totalCasesCount - completedCasesCount,
      successRate: totalCasesCount ? Math.round((completedCasesCount / totalCasesCount) * 100) : 0,
      failedRate: totalCasesCount ? Math.round(((totalCasesCount - completedCasesCount) / totalCasesCount) * 100) : 0
    });

    const deviceStats = report.summary?.deviceStats || [];
    deviceStats.forEach((stat: Record<string, any>) => {
      const deviceTotalCases = stat.totalCases || 0;
      const deviceCompletedCases = stat.completedCases || 0;
      const deviceFailedCases = deviceTotalCases - deviceCompletedCases;

      rows.push({
        id: stat.id || stat.name,
        name: stat.name,
        total: deviceTotalCases,
        executed: deviceTotalCases,
        completed: deviceCompletedCases,
        failed: deviceFailedCases,
        successRate: deviceTotalCases ? Math.round((deviceCompletedCases / deviceTotalCases) * 100) : 0,
        failedRate: deviceTotalCases ? Math.round((deviceFailedCases / deviceTotalCases) * 100) : 0
      });
    });

    return rows;
  }

  // 无报告：按任务汇总
  let totalCasesCount = 0;
  let completedCasesCount = 0;
  let failedCasesCount = 0;

  tasks.forEach(task => {
    totalCasesCount += task.totalCases || 0;
    const taskFailed = task.failedCases || 0;
    completedCasesCount += (task.completedCases || 0) - taskFailed;
    failedCasesCount += taskFailed;
  });

  return [
    {
      id: 'total',
      name: '任务汇总',
      total: totalCasesCount,
      executed: totalCasesCount,
      completed: completedCasesCount,
      failed: failedCasesCount,
      successRate: totalCasesCount ? Math.round((completedCasesCount / totalCasesCount) * 100) : 0,
      failedRate: totalCasesCount ? Math.round((failedCasesCount / totalCasesCount) * 100) : 0
    }
  ];
}

/** 刷新对比数据：按选中资源重算指标行与用例执行统计 */
export function updateComparisonData(tasks?: Task[], report?: Report): void {
  const currentTasks = tasks || comparisonTasks.value || [];
  const currentReport = report || comparisonReport.value;

  const selectedDeviceIds = new Set(comparisonDevices.value.filter(d => d.selected).map(d => d.id));

  deviceApiComparisonData.value = comparisonDevices.value
    .filter(d => selectedDeviceIds.has(d.id))
    .map(d => buildDeviceApiItem(d, currentReport, currentTasks));

  caseExecutionData.value = buildCaseExecutionRows(currentReport, currentTasks);
}

/** 切换资源选中态并刷新对比数据 */
export function toggleDeviceSelection(deviceId: string | number): void {
  const device = comparisonDevices.value.find(d => d.id === deviceId);
  if (device) {
    device.selected = !device.selected;
    updateComparisonData();
  }
}

// ===== 编排：结论与状态（原 services/reportStats） =====

/** 图表用统计格式化 */
export function formatStatsForCharts(stats: any) {
  if (!stats) return null;

  const total = stats.total ?? 0;
  const completed = stats.completed ?? 0;
  const failed = stats.failed ?? 0;
  return { total, completed, failed, successRate: total ? Math.round((completed / total) * 100) : 0 };
}

/** 默认统计（空态占位） */
export function getDefaultStats(): CaseExecutionItem[] {
  return [
    {
      id: 'total',
      name: '全部用例',
      total: 100,
      executed: 100,
      completed: 85,
      failed: 15,
      successRate: 85,
      failedRate: 15
    },
    {
      id: 'device1',
      name: '默认设备',
      total: 100,
      executed: 100,
      completed: 100,
      failed: 0,
      successRate: 100,
      failedRate: 0
    }
  ];
}

/** 任务状态文案（转发 reportConstants，供旧调用方过渡） */
export const getStatusText = getTaskStatusLabel;

/** 报告类型文案 */
export const getReportTypeLabelFromService = getReportTypeLabel;

/** 根据所选任务生成对比结论并写入报告 */
export function updateComparisonReportConclusion(tasks: any[]): void {
  const taskCount = tasks.length;
  if (taskCount === 0) {
    comparisonReport.value.conclusion = '根据对比分析，共选择了 0 个测试任务进行对比。这些任务涵盖了 API 测试和端到端测试类型，状态包括进行中、已完成和失败。从设备数量和用例数量来看，各任务之间存在明显差异，建议进一步分析任务执行效率和质量。通过对比不同任务的执行结果，可以识别出系统性能瓶颈和质量问题，为后续优化提供依据。';
    return;
  }

  const taskTypes = new Set<string>();
  const taskStatuses = new Set<string>();
  let totalDevices = 0;
  let totalCases = 0;

  tasks.forEach(task => {
    if (task) {
      taskTypes.add(task.type);
      taskStatuses.add(task.status);
      totalDevices += task.deviceCount || 0;
      totalCases += task.caseCount || 0;
    }
  });

  const typeText = Array.from(taskTypes).join('、');
  const statusText = Array.from(taskStatuses).map(status => getTaskStatusLabel(status)).join('、');

  comparisonReport.value.conclusion = `根据对比分析，共选择了 ${taskCount} 个测试任务进行对比。这些任务涵盖了 ${typeText} 测试类型，状态包括 ${statusText}。从设备数量（共 ${totalDevices} 台）和用例数量（共 ${totalCases} 个）来看，各任务之间存在明显差异，建议进一步分析任务执行效率和质量。通过对比不同任务的执行结果，可以识别出系统性能瓶颈和质量问题，为后续优化提供依据。`;
}

/** 重置对比 ReadModel 至初始态 */
export function resetReportState(): void {
  comparisonTasks.value = [];
  deviceApiComparisonData.value = [];
  caseExecutionData.value = [];
  comparisonDevices.value = [];
  comparisonReport.value = createDefaultReport();
}
