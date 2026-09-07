import { TaskStatus, ExecutionStatus, EvaluationStatus } from '@/domain/enums'

const executionStatusMap: Record<string, string> = {
  [ExecutionStatus.PENDING]: ExecutionStatus.PENDING,
  [ExecutionStatus.QUEUED]: ExecutionStatus.QUEUED,
  [TaskStatus.RUNNING]: ExecutionStatus.IN_PROGRESS,
  [TaskStatus.EVALUATING]: TaskStatus.EVALUATING,
  [ExecutionStatus.COMPLETED]: ExecutionStatus.COMPLETED,
  [ExecutionStatus.STOPPED]: ExecutionStatus.STOPPED,
  [ExecutionStatus.FAILED]: ExecutionStatus.FAILED,
  [TaskStatus.REEVALUATE_QUEUED]: TaskStatus.REEVALUATE_QUEUED,
  [TaskStatus.REEVALUATING]: TaskStatus.REEVALUATING,
}

const evaluationStatusMap: Record<string, string> = {
  [EvaluationStatus.PENDING]: EvaluationStatus.PENDING,
  [EvaluationStatus.QUEUED]: EvaluationStatus.QUEUED,
  [TaskStatus.RUNNING]: EvaluationStatus.CALCULATING,
  [EvaluationStatus.COMPLETED]: EvaluationStatus.COMPLETED,
  [ExecutionStatus.STOPPED]: ExecutionStatus.STOPPED,
  [EvaluationStatus.CALCULATING]: EvaluationStatus.CALCULATING,
  [EvaluationStatus.FAILED]: EvaluationStatus.FAILED,
}

const resultStatusMap: Record<string, string> = {
  [ExecutionStatus.COMPLETED]: ExecutionStatus.COMPLETED,
  'passed': ExecutionStatus.COMPLETED,
  [ExecutionStatus.FAILED]: ExecutionStatus.FAILED,
}

export interface TestCaseProgress {
  executionStatus?: string
  evaluationStatus?: string
  status?: string
  resultStatus?: string
  errorMessage?: string
}

export interface TransformedStatus {
  status: string
  executionStatus: string
  evaluationStatus: string
  resultStatus: string
  errorMessage: string
}

export function transformTestCaseStatus(testCaseProgress: TestCaseProgress): TransformedStatus {
  let executionStatus: string = testCaseProgress.executionStatus || ExecutionStatus.PENDING
  let evaluationStatus: string = testCaseProgress.evaluationStatus || EvaluationStatus.PENDING
  let resultStatus: string = testCaseProgress.status || testCaseProgress.resultStatus || TaskStatus.PENDING
  let finalStatus: string = TaskStatus.PENDING

  if (executionStatusMap[executionStatus]) {
    executionStatus = executionStatusMap[executionStatus]
  }

  if (evaluationStatusMap[evaluationStatus]) {
    evaluationStatus = evaluationStatusMap[evaluationStatus]
  }

  if (resultStatusMap[resultStatus]) {
    resultStatus = resultStatusMap[resultStatus]
  }

  if (executionStatus === ExecutionStatus.FAILED) {
    finalStatus = ExecutionStatus.FAILED
  } else if (executionStatus === ExecutionStatus.IN_PROGRESS) {
    finalStatus = ExecutionStatus.IN_PROGRESS
  } else if (executionStatus === ExecutionStatus.QUEUED) {
    finalStatus = ExecutionStatus.QUEUED
  } else if (executionStatus === ExecutionStatus.COMPLETED) {
    if (evaluationStatus === EvaluationStatus.QUEUED) {
      finalStatus = EvaluationStatus.QUEUED
    } else if (evaluationStatus === EvaluationStatus.CALCULATING || evaluationStatus === EvaluationStatus.RUNNING) {
      finalStatus = EvaluationStatus.CALCULATING
    } else if (evaluationStatus === EvaluationStatus.FAILED) {
      finalStatus = EvaluationStatus.FAILED
    } else if (evaluationStatus === EvaluationStatus.COMPLETED) {
      finalStatus = resultStatus
    } else if (evaluationStatus === EvaluationStatus.PENDING) {
      finalStatus = TaskStatus.EVALUATING
    } else {
      finalStatus = EvaluationStatus.CALCULATING
    }
  }

  return {
    status: finalStatus,
    executionStatus: executionStatus,
    evaluationStatus: evaluationStatus,
    resultStatus: resultStatus,
    errorMessage: testCaseProgress.errorMessage || ''
  }
}

export function transformTaskStatus(status: string): string {
  return executionStatusMap[status] || status
}

export function getStatusText(status: string): string {
  const statusTextMap: Record<string, string> = {
    [ExecutionStatus.PENDING]: '等待中',
    [ExecutionStatus.QUEUED]: '排队中',
    [ExecutionStatus.IN_PROGRESS]: '执行中',
    [ExecutionStatus.COMPLETED]: '已完成',
    [ExecutionStatus.STOPPED]: '已停止',
    [ExecutionStatus.FAILED]: '失败',
    [EvaluationStatus.CALCULATING]: '评估中',
    [TaskStatus.EVALUATING]: '评估中',
    [TaskStatus.REEVALUATE_QUEUED]: '重新评估排队中',
    [TaskStatus.REEVALUATING]: '重新评估中'
  }

  return statusTextMap[status] || status
}

export function getStatusType(status: string): string {
  const statusTypeMap: Record<string, string> = {
    [ExecutionStatus.PENDING]: 'info',
    [ExecutionStatus.QUEUED]: 'warning',
    [ExecutionStatus.IN_PROGRESS]: 'primary',
    [ExecutionStatus.COMPLETED]: 'success',
    [ExecutionStatus.STOPPED]: 'warning',
    [ExecutionStatus.FAILED]: 'danger',
    [EvaluationStatus.CALCULATING]: 'warning',
    [TaskStatus.EVALUATING]: 'warning',
    [TaskStatus.REEVALUATE_QUEUED]: 'warning',
    [TaskStatus.REEVALUATING]: 'primary'
  }

  return statusTypeMap[status] || 'info'
}
