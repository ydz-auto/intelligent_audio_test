const executionStatusMap: Record<string, string> = {'pending': 'pending', 'queued': 'queued', 'running': 'in_progress', 'evaluating': 'evaluating', 'completed': 'completed', 'stopped': 'stopped', 'failed': 'failed', 'reevaluate_queued': 'reevaluate_queued', 'reevaluating': 'reevaluating'};

const evaluationStatusMap: Record<string, string> = {'pending': 'pending', 'queued': 'queued', 'running': 'calculating', 'completed': 'completed', 'stopped': 'stopped', 'calculating': 'calculating', 'failed': 'failed'};

const resultStatusMap: Record<string, string> = {'completed': 'completed', 'passed': 'completed', 'failed': 'failed'};

export interface TestCaseProgress {
  executionStatus?: string;
  evaluationStatus?: string;
  status?: string;
  resultStatus?: string;
  errorMessage?: string;
  [key: string]: any;
}

export interface TransformedStatus {
  status: string;
  executionStatus: string;
  evaluationStatus: string;
  resultStatus: string;
  errorMessage: string;
}

export function transformTestCaseStatus(testCaseProgress: TestCaseProgress): TransformedStatus {
  let executionStatus = testCaseProgress.executionStatus || 'pending';
  let evaluationStatus = testCaseProgress.evaluationStatus || 'pending';
  let resultStatus = testCaseProgress.status || testCaseProgress.resultStatus || 'pending';
  let finalStatus = 'pending';
  
  if (executionStatusMap[executionStatus]) {
    executionStatus = executionStatusMap[executionStatus];
  }
  
  if (evaluationStatusMap[evaluationStatus]) {
    evaluationStatus = evaluationStatusMap[evaluationStatus];
  }
  
  if (resultStatusMap[resultStatus]) {
    resultStatus = resultStatusMap[resultStatus];
  }
  
  if (executionStatus === 'failed') {
    finalStatus = 'failed';
  } else if (executionStatus === 'in_progress') {
    finalStatus = 'in_progress';
  } else if (executionStatus === 'queued') {
    finalStatus = 'queued';
  } else if (executionStatus === 'completed') {
    if (evaluationStatus === 'queued') {
      finalStatus = 'queued';
    } else if (evaluationStatus === 'calculating' || evaluationStatus === 'running') {
      finalStatus = 'calculating';
    } else if (evaluationStatus === 'failed') {
      finalStatus = 'failed';
    } else if (evaluationStatus === 'completed') {
      finalStatus = resultStatus;
    } else if (evaluationStatus === 'pending') {
      finalStatus = 'evaluating';
    } else {
      finalStatus = 'calculating';
    }
  }
  
  return {
    status: finalStatus, 
    executionStatus: executionStatus, 
    evaluationStatus: evaluationStatus, 
    resultStatus: resultStatus, 
    errorMessage: testCaseProgress.errorMessage || ''
  };
}

export function transformTaskStatus(status: string): string {
  return executionStatusMap[status] || status;
}

export function getStatusText(status: string): string {
  const statusTextMap: Record<string, string> = {
    'pending': '等待中',
    'queued': '排队中',
    'in_progress': '执行中',
    'completed': '已完成',
    'stopped': '已停止',
    'failed': '失败',
    'calculating': '评估中',
    'evaluating': '评估中',
    'reevaluate_queued': '重新评估排队中',
    'reevaluating': '重新评估中'
  };

  return statusTextMap[status] || status;
}

export function getStatusType(status: string): string {
  const statusTypeMap: Record<string, string> = {
    'pending': 'info',
    'queued': 'warning',
    'in_progress': 'primary',
    'completed': 'success',
    'stopped': 'warning',
    'failed': 'danger',
    'calculating': 'warning',
    'evaluating': 'warning',
    'reevaluate_queued': 'warning',
    'reevaluating': 'primary'
  };

  return statusTypeMap[status] || 'info';
}
