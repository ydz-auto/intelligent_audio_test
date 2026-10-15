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
