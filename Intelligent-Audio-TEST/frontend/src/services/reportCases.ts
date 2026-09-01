import { TaskStatus } from '../shared/types/enums';

export function convertDetailedResultsToCases(report: any): any[] {
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
    caseObj.results[resourceKey] = {status: status === TaskStatus.COMPLETED || status === 'passed' ? '成功' : '失败', startTime: result.createdAt, endTime: result.createdAt};

    caseObj.asr.results[resourceKey] = {text: result.asr?.resultText || ''};

    caseObj.translation.results[resourceKey] = {text: result.translation?.resultText || ''};
  });

  return Array.from(casesMap.values());
}

export function extractCasesFromReport(report: any): any[] {
  if (report.cases && report.cases.length > 0) {
    return report.cases;
  } else if (report.summary?.cases && report.summary.cases.length > 0) {
    return report.summary.cases;
  } else {
    return convertDetailedResultsToCases(report);
  }
}
