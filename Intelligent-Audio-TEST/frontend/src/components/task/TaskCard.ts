import { ref, onMounted } from 'vue'
import { useAlgorithmLabels } from '../../composables/algorithm/useAlgorithmLabels'
import { TaskStatus, ExecutionStatus } from '@/domain/enums'
import { getStatusText } from '../../utils/statusUtils'

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

  // 任务类型 → 显示文本映射（enum 化常量，消除魔法字符串散落）
  const TASK_TYPE_TEXT: Record<string, string> = {api: 'API测试', e2e: '端到端测试', playback: '回放任务', evaluation: '评估任务', report: '报告任务', task: '通用任务', execution: '执行任务', comparison: '对比任务', performance: '性能测试', stress: '压力测试', audioImport: '语音导入'}
  const getTaskTypeText = (type: string): string => {
    return TASK_TYPE_TEXT[type] || type
  }

  const getAlgorithmTypeText = (type: string): string => {
    return getAlgorithmLabel(type)
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
    getTaskTypeText,
    getAlgorithmTypeText,
    getStatusText,
    getStepStatusText,
    calculateCompletionRate
  }
}
