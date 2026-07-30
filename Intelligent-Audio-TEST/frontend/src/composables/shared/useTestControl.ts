import { ref, type Ref } from 'vue'
import { tasksApi } from '../../utils/api'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'

export interface UseTestControlOptions {
  currentTaskId: Ref<string | number | null>
  onPaused?: () => void
  onResumed?: () => void
  onStopped?: () => void
  onError?: (error: Error, action: string) => void
  addLog?: (log: { content: string; level: string }) => void
}

export function useTestControl(options: UseTestControlOptions) {
  const { currentTaskId, onPaused, onResumed, onStopped, onError, addLog } = options
  
  const modalManager = useModalControl()
  const isPaused = ref(false)
  const isControlling = ref(false)

  async function pauseTest() {
    if (!currentTaskId.value) {
      if (addLog) {
        addLog({ content: '无法暂停测试：当前任务ID为空', level: 'error' })
      }
      return
    }
    if (isControlling.value) return

    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '暂停测试',
      content: '确定要暂停当前的测试任务吗？',
      confirmText: '暂停',
      cancelText: '取消'
    })

    if (confirmed) {
      isControlling.value = true
      try {
        await tasksApi.control(currentTaskId.value, 'pause')
        isPaused.value = true
        if (addLog) {
          addLog({ content: '测试任务已暂停', level: 'warn' })
        }
        if (onPaused) onPaused()
      } catch (error) {
        console.error('暂停测试失败:', error)
        if (onError) onError(error instanceof Error ? error : new Error(String(error)), 'pause')
        if (addLog) {
          addLog({ content: `暂停测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
        }
      } finally {
        isControlling.value = false
      }
    }
  }

  async function resumeTest() {
    if (!currentTaskId.value) {
      if (addLog) {
        addLog({ content: '无法恢复测试：当前任务ID为空', level: 'error' })
      }
      return
    }
    if (isControlling.value) return

    isControlling.value = true
    try {
      await tasksApi.control(currentTaskId.value, 'resume')
      isPaused.value = false
      if (addLog) {
        addLog({ content: '测试任务已恢复', level: 'info' })
      }
      if (onResumed) onResumed()
    } catch (error) {
      console.error('恢复测试失败:', error)
      if (onError) onError(error instanceof Error ? error : new Error(String(error)), 'resume')
      if (addLog) {
        addLog({ content: `恢复测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
      }
    } finally {
      isControlling.value = false
    }
  }

  async function stopTest() {
    if (!currentTaskId.value) {
      if (addLog) {
        addLog({ content: '无法停止测试：当前任务ID为空', level: 'error' })
      }
      return
    }
    if (isControlling.value) return

    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '停止测试',
      content: '确定要停止当前的测试任务吗？停止后将无法恢复。',
      confirmText: '停止测试',
      cancelText: '取消',
      danger: true
    })

    if (confirmed) {
      isControlling.value = true
      try {
        await tasksApi.stop(currentTaskId.value)
        isPaused.value = false
        if (addLog) {
          addLog({ content: '测试任务已停止', level: 'warn' })
        }
        if (onStopped) onStopped()
      } catch (error) {
        console.error('停止测试失败:', error)
        if (onError) onError(error instanceof Error ? error : new Error(String(error)), 'stop')
        if (addLog) {
          addLog({ content: `停止测试失败: ${error instanceof Error ? error.message : String(error)}`, level: 'error' })
        }
      } finally {
        isControlling.value = false
      }
    }
  }

  function reset() {
    isPaused.value = false
    isControlling.value = false
  }

  return {
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest,
    reset
  }
}