import { ref } from 'vue';
import { reportsApi } from '../utils/api';
import { useModalControl, MODAL_TYPES } from '../composables/modal/useModal';
import { sanitizeConclusion } from '../utils/sanitize';
import { normalizeReport } from '../utils/fieldNaming';
import socketService from '../utils/socket';
import { 
  TASK_STATUS_MAP, 
  REPORT_TYPE_MAP, 
  getTaskStatusLabel, 
  getReportTypeLabel 
} from '../shared/constants/reportConstants';
import type { 
    Report, 
    ComparisonDevice, 
    DeviceAPIComparisonItem, 
    CaseExecutionItem,
    Task,
    Device,
    APIConfig
} from '../shared/types';

interface AggregatedMetrics {
  [key: string]: any;
}

interface RoundDetail {
  round: number;
  input?: any;
  output?: any;
  interruption?: any;
  latency?: any;
  wait_time?: any;
  evaluation?: any;
}

interface MultiRoundResult {
  isMultiRound: boolean;
  rounds: RoundDetail[];
  aggregated: AggregatedMetrics | null;
  totalRounds: number;
}

const now = new Date().toISOString();
const modalManager = useModalControl();

const createDefaultReport = (): Report => ({
  id: '',
  name: '任务对比报告',
  type: 'comparison',
  status: 'draft',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  description: '',
  summary: {totalCases: 0, passedCases: 0, failedCases: 0, passRate: 0, avgScore: 0, allMetrics: [], detailedResults: [], deviceStats: [], apiStats: []}
});

const comparisonReport = ref<Report>(createDefaultReport());

const comparisonTasks = ref<Task[]>([]);

const deviceApiComparisonData = ref<DeviceAPIComparisonItem[]>([]);
const caseExecutionData = ref<CaseExecutionItem[]>([]);
const devices = ref<ComparisonDevice[]>([]);

const deviceApiColumns = [
  { key: 'name', label: '名称', type: 'text', sortable: true },
  { key: 'type', label: '类型', type: 'text', sortable: true },
  { key: 'version', label: '版本', type: 'text', sortable: true },
  { key: 'status', label: '状态', type: 'status', sortable: true },
  { key: 'totalCases', label: '总用例数', type: 'number', sortable: true },
  { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
  { key: 'avgResponseTime', label: '平均响应时间 (ms)', type: 'number', sortable: true },
  { key: 'stability', label: '稳定性', type: 'percentage', sortable: true }
];

const caseExecutionColumns = [
  { key: 'name', label: '名称', type: 'text', sortable: true },
  { key: 'total', label: '总用例数', type: 'number', sortable: true },
  { key: 'executed', label: '已执行', type: 'number', sortable: true },
  { key: 'completed', label: '已完成', type: 'number', sortable: true },
  { key: 'failed', label: '失败', type: 'number', sortable: true },
  { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
  { key: 'failedRate', label: '失败率', type: 'percentage', sortable: true }
];

function extractDevicesFromTasks(tasks: Task[], report?: Report): ComparisonDevice[] {
  const extractedDevices: ComparisonDevice[] = [];
  
  tasks.forEach(task => {
    const taskDevices = [
      ...((task as any).devices || []),
      ...(task.config?.devices || [])
    ] as Device[];
    
    const taskApis = [
      ...((task as any).apis || []),
      ...(task.config?.apis || [])
    ] as APIConfig[];
    
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
          id: typeof device === 'string' ? `device-${deviceName.toLowerCase().replace(/\s+/g, '-')}` : (device.id || `device-${Math.random().toString(36).slice(2, 11)}`),
          name: deviceName,
          type: typeof device === 'string' ? '设备' : (((device as Device).type || '设备') as '设备' | 'API'),
          selected: true
        });
      }
    });
    
    const reportAPIs = report.summary?.apis || [];
    
    reportAPIs.forEach(api => {
      const apiName = typeof api === 'string' ? api : api.name;
      
      if (apiName && !extractedDevices.find(d => d.name === apiName)) {
        extractedDevices.push({
          id: typeof api === 'string' ? `api-${apiName.toLowerCase().replace(/\s+/g, '-')}` : (api.id || `api-${Math.random().toString(36).slice(2, 11)}`),
          name: apiName,
          type: 'API' as '设备' | 'API',
          selected: true
        });
      }
    });
  }
  
  if (extractedDevices.length === 0) {
    console.warn('No devices or APIs found in tasks or report');
  }
  
  devices.value = extractedDevices;
  updateComparisonData(tasks, report);
  
  return extractedDevices;
}

function updateComparisonData(tasks?: Task[], report?: Report): void {
  const currentTasks = tasks || comparisonTasks.value || [];
  const currentReport = report || comparisonReport.value;
  
  const selectedDeviceIds = new Set(devices.value.filter(d => d.selected).map(d => d.id));
  
  deviceApiComparisonData.value = devices.value
    .filter(d => selectedDeviceIds.has(d.id))
    .map(d => {
      let totalCases = 0;
      let completedCases = 0;
      let avgResponseTime = 0;
      let stability = 0;
      
      if (currentReport && currentReport.summary) {
        if (d.type === '设备') {
          const deviceStats = currentReport.summary.deviceStats || [];
          const deviceStat = deviceStats.find((stat: Record<string, any>) => 
            stat.id === d.id || stat.name === d.name
          );
          
          if (deviceStat) {
            totalCases = deviceStat.totalCases || 0;
            completedCases = deviceStat.completedCases || 0;
            
            const getMetric = (names: string[]) => {
              for (const name of names) {
                if (deviceStat[name] !== undefined) return deviceStat[name];
              }
              if (deviceStat.metrics) {
                for (const name of names) {
                  if (deviceStat.metrics[name] !== undefined) return deviceStat.metrics[name];
                }
              }
              return 0;
            };
            
            avgResponseTime = getMetric(['avgResponseTime', 'averageResponseTime', '平均响应时间']);
            stability = getMetric(['stability', '稳定性', 'Stability']);
          } else {
            totalCases = currentReport.summary.totalCases || 0;
            completedCases = currentReport.summary.completedCases || 0;
            
            let metricCount = 0;
            let werSum = 0;
            
            const metricGroups = (currentReport.summary.metricData || []) as any[];
            const deviceName = String(d.name || '').toLowerCase();
            const deviceId = String(d.id || '').toLowerCase();
            metricGroups.forEach((group) => {
              if (!group) return;
              const resource = String(group.resource || '').toLowerCase();
              const matched =
                (deviceId && resource.includes(`${deviceId}-`)) ||
                (deviceName && resource.includes(deviceName));
              if (matched) {
                const categories = Array.isArray(group.categories) ? group.categories : [];
                categories.forEach((c) => {
                  const metrics = Array.isArray(c?.metrics) ? c.metrics : [];
                  const wer = metrics.find(m => m && m.metric === 'WER');
                  if (wer) {
                    werSum += Number(wer.value || 0);
                    metricCount++;
                  }
                })
              }
            });
            
            if (metricCount > 0) {
              const avgWer = werSum / metricCount;
              stability = Math.max(0, 100 - avgWer);
            }
          }
        }
        else if (d.type === 'API') {
          const apiStats = currentReport.summary.apiStats || [];
          const apiStat = apiStats.find((stat: Record<string, any>) => 
            stat.id === d.id || stat.name === d.name
          );
          
          if (apiStat) {
            totalCases = apiStat.totalCases || 0;
            completedCases = apiStat.completedCases || 0;
            avgResponseTime = apiStat.avgResponseTime || 0;
            stability = apiStat.stability || 0;
          } else {
            totalCases = currentReport.summary.totalCases || 0;
            completedCases = currentReport.summary.completedCases || 0;
            
            let metricCount = 0;
            let werSum = 0;
            
            const metricGroups = (currentReport.summary.metricData || []) as any[];
            const apiName = String(d.name || '').toLowerCase();
            const apiId = String(d.id || '').toLowerCase();
            metricGroups.forEach((group) => {
              if (!group) return;
              const resource = String(group.resource || '').toLowerCase();
              const matched =
                (apiId && resource.includes(`${apiId}-`)) ||
                (apiName && resource.includes(apiName));
              if (matched) {
                const categories = Array.isArray(group.categories) ? group.categories : [];
                categories.forEach((c) => {
                  const metrics = Array.isArray(c?.metrics) ? c.metrics : [];
                  const wer = metrics.find(m => m && m.metric === 'WER');
                  if (wer) {
                    werSum += Number(wer.value || 0);
                    metricCount++;
                  }
                })
              }
            });
            
            if (metricCount > 0) {
              const avgWer = werSum / metricCount;
              stability = Math.max(0, 100 - avgWer);
            }
          }
        }
      }
      
      if (totalCases === 0) {
        currentTasks.forEach(task => {
          const taskResource = (task as any).devices?.find((device: Device) => device.id === d.id) || 
                             (task as any).apis?.find((api: APIConfig) => api.id === d.id) ||
                             (task as any).devices?.find((device: Device) => device.name === d.name) ||
                             (task as any).apis?.find((api: APIConfig) => api.name === d.name);
          if (taskResource) {
            totalCases += task.totalCases || 0;
            completedCases += (task.completedCases || 0) - (task.failedCases || 0);
          }
        });
      }
      
      if (totalCases === 0 && currentReport?.summary) {
        totalCases = currentReport.summary.totalCases || 0;
        completedCases = currentReport.summary.completedCases || 0;
      }
      
      if (totalCases === 0) {
        totalCases = 0;
        completedCases = 0;
      }
      
      return {id: d.id, name: d.name, type: d.type, version: (d as any).version || '', status: currentReport?.status || 'completed', totalCases, successRate: totalCases ? Math.round((completedCases / totalCases) * 100) : 0, avgResponseTime, stability};
    });

  if (currentReport) {
    const detailedResults = currentReport.detailedResults || [];
    const totalCasesCount = detailedResults.length || 0;
    const completedCasesCount = detailedResults.filter((result: any) => 
      result.status === 'completed' ||
      result.status === 'passed'
    ).length || 0;
    
    caseExecutionData.value = [
      {
        id: 'total',
        name: '全部用例',
        total: totalCasesCount,
        executed: totalCasesCount,
        completed: completedCasesCount,
        failed: totalCasesCount - completedCasesCount,
        successRate: totalCasesCount ? Math.round((completedCasesCount / totalCasesCount) * 100) : 0,
        failedRate: totalCasesCount ? Math.round(((totalCasesCount - completedCasesCount) / totalCasesCount) * 100) : 0
      }
    ];
    
    const deviceStats = currentReport.summary?.deviceStats || [];
    deviceStats.forEach((stat: Record<string, any>) => {
      const deviceTotalCases = stat.totalCases || 0;
      const deviceCompletedCases = stat.completedCases || 0;
      const deviceFailedCases = deviceTotalCases - deviceCompletedCases;
      
      caseExecutionData.value.push({
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
  } else {
    let totalCasesCount = 0;
    let completedCasesCount = 0;
    let failedCasesCount = 0;
    
    currentTasks.forEach(task => {
      totalCasesCount += task.totalCases || 0;
      const taskFailed = task.failedCases || 0;
      const taskCompleted = (task.completedCases || 0) - taskFailed;
      completedCasesCount += taskCompleted;
      failedCasesCount += taskFailed;
    });
    
    caseExecutionData.value = [
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
}

function formatStatsForCharts(stats: any) {
  if (!stats) return null;
  
  const total = stats.total ?? 0;
  const completed = stats.completed ?? 0;
  const failed = stats.failed ?? 0;
  return { total, completed, failed, successRate: total ? Math.round((completed / total) * 100) : 0 };
}

function getDefaultStats(): CaseExecutionItem[] {
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

function toggleDeviceSelection(deviceId: string | number): void {
  const device = devices.value.find(d => d.id === deviceId);
  if (device) {
    device.selected = !device.selected;
    updateComparisonData();
  }
}

function getStatusText(status: string): string {
  return getTaskStatusLabel(status);
}

function updateComparisonReportConclusion(tasks: any[]): void {
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
  const statusText = Array.from(taskStatuses).map(status => getStatusText(status)).join('、');
  
  comparisonReport.value.conclusion = `根据对比分析，共选择了 ${taskCount} 个测试任务进行对比。这些任务涵盖了 ${typeText} 测试类型，状态包括 ${statusText}。从设备数量（共 ${totalDevices} 台）和用例数量（共 ${totalCases} 个）来看，各任务之间存在明显差异，建议进一步分析任务执行效率和质量。通过对比不同任务的执行结果，可以识别出系统性能瓶颈和质量问题，为后续优化提供依据。`;
}

function getReportTypeLabelFromService(type: string): string {
  return getReportTypeLabel(type);
}

async function saveReport(reportData: Partial<Report>): Promise<Report> {
  try {
    if (reportData.id) {
      const result = await reportsApi.update(reportData.id, reportData);
      return result;
    } else {
      const result = await reportsApi.create(reportData);
      return result;
    }
  } catch (error) {
    console.error('保存报告失败:', error);
    throw error;
  }
}

async function createComparisonReport(tasks: Task[]) {
  try {
    const reportData = {name: `任务对比报告_${new Date().toLocaleString()}`,
      type: 'comparison',
      taskIds: tasks.map(t => t.id),
      config: {devices: devices.value.filter(d => d.selected).map(d => ({ id: d.id, name: d.name, type: d.type}))}
    };
    
    const response = await reportsApi.create(reportData);
    return response;
  } catch (err: any) {
    console.error('Failed to create comparison report:', err);
    throw err;
  }
}

async function exportReport(reportId: string | number, format = 'excel'): Promise<Blob> {
  try {
    const blob = await reportsApi.export([reportId], format);
    return blob;
  } catch (error) {
    console.error('导出报告失败:', error);
    throw error;
  }
}

async function publishReport(reportId: string | number): Promise<any> {
  try {
    const result = await reportsApi.publish(reportId);
    return result;
  } catch (error) {
    console.error('发布报告失败:', error);
    throw error;
  }
}

function convertDetailedResultsToCases(report: any): any[] {
  const detailedResults = report.detailedResults || [];
  if (detailedResults.length === 0) return [];

  const casesMap = new Map();
  
  detailedResults.forEach((result: any) => {
    const testCaseId = result.testCaseId;
    if (!testCaseId) return;

    if (!casesMap.has(testCaseId)) {
      const caseObj: any = {id: testCaseId, name: result.testCaseName || '未命名用例', description: '', category: '', tags: [], metrics: {},
        results: {},
        audio: {id: result.audioId || '', name: result.audioName || '', filePath: result.audioFilePath || '', duration: result.audioDuration || 0},
        asr: {referenceText: result.asr?.referenceText || '', results: {}},
        translation: {referenceText: result.translation?.referenceText || '', results: {}},
        logs: result.errorMessage || ''
      };
      casesMap.set(testCaseId, caseObj);
    }
    
    const caseObj = casesMap.get(testCaseId);
    
    let resourceName = '';
    const device = result.device;
    const api = result.api;

    if (device) {
      resourceName = device.name;
    } else if (api) {
      resourceName = api.name;
    } else {
      resourceName = '默认资源';
    }
    
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
    caseObj.results[resourceKey] = {status: status === 'completed' || status === 'passed' ? '成功' : '失败', startTime: result.createdAt, endTime: result.createdAt};
    
    caseObj.asr.results[resourceKey] = {text: result.asr?.resultText || ''};
    
    caseObj.translation.results[resourceKey] = {text: result.translation?.resultText || ''};
  });
  
  return Array.from(casesMap.values());
}

function extractCasesFromReport(report: any): any[] {
  if (report.cases && report.cases.length > 0) {
    return report.cases;
  } else if (report.summary?.cases && report.summary.cases.length > 0) {
    return report.summary.cases;
  } else {
    return convertDetailedResultsToCases(report);
  }
}

async function viewTaskReport(task: Task): Promise<Report> {
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

              report = normalizeReport(report);
              const cases = extractCasesFromReport(report);
              const summary = report.summary || {};
              
              comparisonReport.value = {...comparisonReport.value, 
                id: report.id, 
                name: report.name || report.title, 
                description: report.description || '', 
                conclusion: (report.analysis || report.conclusion) || '',
                status: report.status, 
                algorithmType: report.algorithmType || task.algorithmType,
                createdAt: report.createdAt, 
                updatedAt: report.updatedAt, 
                summary: {
                  ...summary, allMetrics: summary.allMetrics || [], detailedResults: report.detailedResults || [], deviceStats: summary.deviceStats || [], apiStats: summary.apiStats || []
                },
                cases: cases,
                detailedResults: report.detailedResults || [],
                allMetrics: summary.allMetrics || []
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

    report = normalizeReport(report);

    const cases = extractCasesFromReport(report);

    const summary = report.summary || {};
    comparisonReport.value = {...comparisonReport.value, 
      id: report.id, 
      name: report.name || report.title, 
      description: report.description || '', 
      conclusion: (report.analysis || report.conclusion) || '',
      status: report.status, 
      algorithmType: report.algorithmType || task.algorithmType,
      createdAt: report.createdAt, 
      updatedAt: report.updatedAt, 
      summary: {
        ...summary, allMetrics: summary.allMetrics || [], detailedResults: report.detailedResults || [], deviceStats: summary.deviceStats || [], apiStats: summary.apiStats || []
      },
      cases: cases,
      detailedResults: report.detailedResults || [],
      allMetrics: summary.allMetrics || []
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

async function batchCompare(taskIds: (string | number)[], tasks: Task[]): Promise<Report> {
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

    report = normalizeReport(report);

    const cases = extractCasesFromReport(report);

    const summary = report.summary || {};
    
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
        summary.avgResponseTime = findValue(['平均响应时间', 'Avg Response Time', 'avgResponseTime', 'Response Time']) || 0;
      }
    }

    comparisonReport.value = {...comparisonReport.value, 
      id: report.id, 
      name: report.name || report.title, 
      description: report.description || '', 
      conclusion: (report.analysis || report.conclusion) || '',
      status: report.status, 
      algorithmType: report.algorithmType,
      updatedAt: report.updatedAt, 
      summary: summary, 
      cases: cases, 
      detailedResults: report.detailedResults || [], 
      allMetrics: summary.allMetrics || []
    } as any;

    comparisonTasks.value = [...tasks];
    
    extractDevicesFromTasks(comparisonTasks.value, comparisonReport.value);

    return comparisonReport.value;
  } catch (error) {
    console.error('批量对比任务失败:', error);
    throw error;
  }
}

function resetReportState(): void {
  comparisonTasks.value = [];
  deviceApiComparisonData.value = [];
  caseExecutionData.value = [];
  devices.value = [];
  comparisonReport.value = createDefaultReport();
  console.log('[ReportService] 报告状态已重置');
}

function parseMultiRoundResult(algorithmResult: any): MultiRoundResult {
  const isMultiRound = algorithmResult && typeof algorithmResult === 'object' && 'rounds' in algorithmResult && Array.isArray(algorithmResult.rounds);

  if (!isMultiRound) {
    return { isMultiRound: false, rounds: [], aggregated: null, totalRounds: 0 };
  }

  const rounds: RoundDetail[] = algorithmResult.rounds.map((item: any): RoundDetail => {
    if ('round' in item) {
      return {
        round: item.round,
        input: item.input,
        output: item.output,
        interruption: item.interruption,
        latency: item.latency,
        wait_time: item.wait_time,
        evaluation: item.evaluation
      };
    }
    if ('roundNumber' in item) {
      return {
        round: item.roundNumber - 1,
        input: item.input,
        output: item.output,
        interruption: item.interruption,
        latency: item.latency,
        wait_time: item.wait_time,
        evaluation: item.evaluation
      };
    }
    return { round: 0 };
  });

  return {
    isMultiRound: true,
    rounds,
    aggregated: algorithmResult.aggregated || null,
    totalRounds: algorithmResult.total_rounds || algorithmResult.rounds.length
  };
}

function getMetricValue(algorithmResult: any, metricName: string, dimensions?: any[]): number | null {
  const parsed = parseMultiRoundResult(algorithmResult);

  if (parsed.isMultiRound && parsed.aggregated) {
    if (parsed.aggregated[metricName] !== undefined) {
      return parsed.aggregated[metricName];
    }
    const avgKey = `avg_${metricName}`;
    if (parsed.aggregated[avgKey] !== undefined) {
      return parsed.aggregated[avgKey];
    }
    return null;
  }

  if (dimensions && Array.isArray(dimensions)) {
    const dim = dimensions.find((d: any) => d.dimension_name === metricName);
    if (dim && dim.value !== undefined) {
      return dim.value;
    }
  }

  return null;
}

export const reportService = {
  comparisonReport,
  comparisonTasks,
  deviceApiComparisonData,
  caseExecutionData,
  devices,
  deviceApiColumns,
  caseExecutionColumns,
  extractDevicesFromTasks,
  updateComparisonData,
  toggleDeviceSelection,
  updateComparisonReportConclusion,
  getStatusText,
  getReportTypeLabel: getReportTypeLabelFromService,
  saveReport,
  exportReport,
  publishReport,
  createComparisonReport,
  viewTaskReport,
  batchCompare,
  formatStatsForCharts,
  getDefaultStats,
  resetReportState,
  sanitizeConclusion,
  parseMultiRoundResult,
  getMetricValue,
  TASK_STATUS_MAP,
  REPORT_TYPE_MAP
};

export default reportService;
