import { ref, onMounted } from 'vue'
import { useAlgorithmLabels } from '../../composables/algorithm/useAlgorithmLabels'

export function useTaskCard(props: any, emit: any) {
  const { loadAlgorithms, getAlgorithmLabel } = useAlgorithmLabels()

  onMounted(() => {
    loadAlgorithms()
  })

  const isEditingName = ref(false)
  const editedName = ref('')
  let pendingBlurTask = null

  const startEditName = (e) => {
    e.stopPropagation()
    editedName.value = props.task.name || props.task.title || ''
    isEditingName.value = true
  }

  const saveEditName = (e) => {
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

  const cancelEditName = (e) => {
    e?.stopPropagation()
    if (pendingBlurTask) {
      clearTimeout(pendingBlurTask)
      pendingBlurTask = null
    }
    isEditingName.value = false
  }

  const handleBlur = (e) => {
    e.stopPropagation()
    pendingBlurTask = setTimeout(() => {
      if (editedName.value.trim()) {
        emit('name-updated', { taskId: props.task.id, newName: editedName.value.trim() })
      }
      isEditingName.value = false
      pendingBlurTask = null
    }, 200)
  }

  const handleKeydown = (e) => {
    if (e.key === 'Enter') {
      saveEditName(e)
    } else if (e.key === 'Escape') {
      cancelEditName(e)
    }
  }

  const toggleSelection = () => {
    emit('toggle-selection', props.task.id)
  }

  const handleAction = (action) => {
    emit('action', { action, task: props.task })
  }

  const getTaskTypeText = (type) => {
    const typeMap = {api: 'API测试', e2e: '端到端测试', playback: '回放任务', evaluation: '评估任务', report: '报告任务', task: '通用任务', execution: '执行任务', comparison: '对比任务', performance: '性能测试', stress: '压力测试', audioImport: '语音导入'}
    return typeMap[type] || type
  }

  const getAlgorithmTypeText = (type) => {
    return getAlgorithmLabel(type)
  }

  const getStatusText = (status) => {
    const statusMap = {pending: '待执行', queued: '排队中', running: '执行中', evaluating: '评估中', reevaluate_queued: '重新评估排队中', reevaluating: '重新评估中', completed: '已完成', failed: '执行失败', paused: '已暂停', stopped: '已停止', skipped: '已跳过', merged: '已合并'}
    return statusMap[status] || status
  }

  const getStepStatusText = (status) => {
    const statusMap = {pending: '待执行', queued: '排队中', running: '执行中', evaluating: '评估中', completed: '已完成', failed: '执行失败', paused: '已暂停', stopped: '已停止', skipped: '已跳过'}
    return statusMap[status] || status
  }

  const calculateCompletionRate = (task) => {
    const completed = task.completed_cases || 0
    const total = task.total_cases || task.case_count || 0
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
