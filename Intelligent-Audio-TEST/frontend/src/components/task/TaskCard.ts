import { ref, onMounted } from 'vue'
import { useAlgorithmLabels } from '../../composables/algorithm/useAlgorithmLabels'
import { TaskStatus, TaskEvaluationStatus, ExecutionStatus } from '@/domain/enums'
import { getStatusText } from '../../utils/statusUtils'
import { getTaskEvaluationStatusLabel } from '../../domain/constants/reportLabels'

/** 通用事件参数（DOM 事件） */
type DomEvent = Event & { stopPropagation: () => void }

export function useTaskCard(props: any, emit: (event: string, ...args: any[]) => void) {
  const { loadAlgorithms, getAlgorithmLabel } = useAlgorithmLabels()

  onMounted(() => {
    loadAlgorithms()
  })

  const isEditingName = ref(false)
  const editedName = ref('')
  // 待执行的失焦保存定时器句柄
  let pendingBlurTask: ReturnType<typeof setTimeout> | null = null

  const startEditName = (e: DomEvent) => {
    e.stopPropagation()
    editedName.value = props.task.name || props.task.title || ''
    isEditingName.value = true
  }

  const saveEditName = (e?: DomEvent) => {
    e?.stopPropagation()
    if (pendingBlurTask) {
      clearTimeout(pendingBlurTask)
      pendingBlurTask = null
    }
    if (editedName.value.trim()) {
      emit('name-updated', { taskId: props.task.id, newName: editedName.value.trim() })
    }
    isEditingName.value = false
  }

  const cancelEditName = (e?: DomEvent) => {
    e?.stopPropagation()
    if (pendingBlurTask) {
      clearTimeout(pendingBlurTask)
      pendingBlurTask = null
    }
    isEditingName.value = false
  }

  const handleBlur = (e: DomEvent) => {
    e.stopPropagation()
    pendingBlurTask = setTimeout(() => {
      if (editedName.value.trim()) {
        emit('name-updated', { taskId: props.task.id, newName: editedName.value.trim() })
      }
      isEditingName.value = false
      pendingBlurTask = null
    }, 200)
  }

  const handleKeydown = (e: DomEvent & { key: string }) => {
    if (e.key === 'Enter') {
      saveEditName(e)
    } else if (e.key === 'Escape') {
      cancelEditName(e)
    }
  }

  const toggleSelection = () => {
    emit('toggle-selection', props.task.id)
  }

  const handleAction = (action: string) => {
    emit('action', { action, task: props.task })
  }

  // 用例级被测设备类型 → 显示文本（差异#2 收尾：取代 task.type 徽标）
  const DEVICE_TYPE_TEXT: Record<string, string> = {
    physical: '物理设备',
    http_api: 'HTTP API',
    websocket_api: 'WebSocket API',
  }
  const getDeviceTypesText = (deviceTypes?: string[]): string => {
    if (!deviceTypes || deviceTypes.length === 0) return '测试任务'
    return deviceTypes.map(dt => DEVICE_TYPE_TEXT[dt] || dt).join(' / ')
  }
  const getDeviceTypeClass = (deviceTypes?: string[]): string => {
    if (!deviceTypes || deviceTypes.length === 0) return 'mixed'
    if (deviceTypes.length > 1) return 'mixed'
    return deviceTypes[0]
  }

  const getAlgorithmTypeText = (type: string): string => {
    return getAlgorithmLabel(type)
  }

  // ===== INT-301：任务级执行/评估双徽章 =====

  /**
   * 执行徽章状态：优先取后端派生的 executionStatus（纯执行域，评估推进
   * 不落此字段）；缺失（旧后端/回收站轻量行）时回退原始 task.status。
   */
  const getExecutionBadgeStatus = (task: { executionStatus?: string; status?: string }): string => {
    return task.executionStatus || task.status || TaskStatus.PENDING
  }

  /** 执行徽章图标（纯执行域，无评估过渡图标） */
  const getExecutionBadgeIcon = (status: string): string => {
    const iconMap: Record<string, string> = {
      [TaskStatus.PENDING]: 'fa-clock',
      [TaskStatus.QUEUED]: 'fa-hourglass',
      [TaskStatus.RUNNING]: 'fa-spinner fa-spin',
      [ExecutionStatus.COMPLETED]: 'fa-check-circle',
      [ExecutionStatus.FAILED]: 'fa-times-circle',
      [TaskStatus.PAUSED]: 'fa-pause-circle',
      [ExecutionStatus.STOPPED]: 'fa-stop-circle',
      [TaskStatus.SKIPPED]: 'fa-minus-circle',
      [TaskStatus.MERGED]: 'fa-object-group',
    }
    return iconMap[status] || 'fa-clock'
  }

  /** 评估徽章文案（INT-301 独立口径；未知值回退原文容错） */
  const getEvaluationStatusText = (status: string): string => {
    return getTaskEvaluationStatusLabel(status)
  }

  /** 评估徽章图标（评估域独立图标族，与执行侧区分） */
  const getEvaluationBadgeIcon = (status: string): string => {
    const iconMap: Record<string, string> = {
      [TaskEvaluationStatus.PENDING]: 'fa-hourglass-half',
      [TaskEvaluationStatus.EVALUATING]: 'fa-sync-alt fa-spin',
      [TaskEvaluationStatus.COMPLETED]: 'fa-check-circle',
      [TaskEvaluationStatus.FAILED]: 'fa-times-circle',
      [TaskEvaluationStatus.SKIPPED]: 'fa-forward',
    }
    return iconMap[status] || 'fa-hourglass-half'
  }

  const getStepStatusText = (status: string): string => {
    const statusMap: Record<string, string> = {
      [ExecutionStatus.PENDING]: '待执行',
      [ExecutionStatus.QUEUED]: '排队中',
      [ExecutionStatus.RUNNING]: '执行中',
      [TaskStatus.EVALUATING]: '评估中',
      [ExecutionStatus.COMPLETED]: '已完成',
      [ExecutionStatus.FAILED]: '执行失败',
      [TaskStatus.PAUSED]: '已暂停',
      [ExecutionStatus.STOPPED]: '已停止',
      [TaskStatus.SKIPPED]: '已跳过'
    }
    return statusMap[status] || status
  }

  // Task Domain 已是 camelCase：completedCases / totalCases
  const calculateCompletionRate = (task: { completedCases?: number; totalCases?: number; caseCount?: number }): number => {
    const completed = task.completedCases || 0
    const total = task.totalCases || task.caseCount || 0
    if (total === 0) return 0
    return Math.round((completed / total) * 100)
  }

  return {
    isEditingName,
    editedName,
    startEditName,
    saveEditName,
    cancelEditName,
    handleBlur,
    handleKeydown,
    toggleSelection,
    handleAction,
    getDeviceTypesText,
    getDeviceTypeClass,
    getAlgorithmTypeText,
    getStatusText,
    getExecutionBadgeStatus,
    getExecutionBadgeIcon,
    getEvaluationStatusText,
    getEvaluationBadgeIcon,
    getStepStatusText,
    calculateCompletionRate
  }
}
