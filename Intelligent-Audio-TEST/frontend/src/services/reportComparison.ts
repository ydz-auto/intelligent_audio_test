import type {
  Report,
  ComparisonDevice,
  DeviceAPIComparisonItem,
  CaseExecutionItem,
  Task,
  Device,
  APIConfig
} from './reportTypes';
import { TaskStatus, ReportStatus } from '../shared/types/enums';
import {
  devices,
  deviceApiComparisonData,
  caseExecutionData,
  comparisonTasks,
  comparisonReport
} from './reportState';

export function extractDevicesFromTasks(tasks: Task[], report?: Report): ComparisonDevice[] {
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

export function updateComparisonData(tasks?: Task[], report?: Report): void {
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
                categories.forEach((c: any) => {
                  const metrics = Array.isArray(c?.metrics) ? c.metrics : [];
                  const wer = metrics.find((m: any) => m && m.metric === 'WER');
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
                categories.forEach((c: any) => {
                  const metrics = Array.isArray(c?.metrics) ? c.metrics : [];
                  const wer = metrics.find((m: any) => m && m.metric === 'WER');
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

      return {id: d.id, name: d.name, type: d.type, version: (d as any).version || '', status: currentReport?.status || ReportStatus.COMPLETED, totalCases, successRate: totalCases ? Math.round((completedCases / totalCases) * 100) : 0, avgResponseTime, stability};
    });

  if (currentReport) {
    const detailedResults = currentReport.detailedResults || [];
    const totalCasesCount = detailedResults.length || 0;
    const completedCasesCount = detailedResults.filter((result: any) =>
      result.status === TaskStatus.COMPLETED ||
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

export function toggleDeviceSelection(deviceId: string | number): void {
  const device = devices.value.find(d => d.id === deviceId);
  if (device) {
    device.selected = !device.selected;
    updateComparisonData();
  }
}

export { comparisonReport, comparisonTasks, devices, deviceApiComparisonData, caseExecutionData };
