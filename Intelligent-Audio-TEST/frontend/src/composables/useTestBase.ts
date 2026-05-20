import { ref } from 'vue'
import { modalManager, MODAL_TYPES } from '@/utils/modalManager'
import { tasksApi } from '@/api/tasks'

export interface UseTestBaseOptions {
  totalSteps: number
  initialStep?: number
}

export function useTestBase(options: UseTestBaseOptions) {
  const { totalSteps, initialStep = 1 } = options

  const currentStep = ref(initialStep)
  const currentTaskId = ref<string | null>(null)
  const isPaused = ref(false)
  const isControlling = ref(false)

  function nextStep() {
    if (currentStep.value < totalSteps) {
      currentStep.value++
    }
  }

  function prevStep() {
    if (currentStep.value > 1) {
      currentStep.value--
    }
  }

  function goToStep(step: number) {
    if (step >= 1 && step <= totalSteps) {
      currentStep.value = step
    }
  }

  async function pauseTest() {
    if (currentTaskId.value && !isControlling.value) {
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
        } catch (error: any) {
          console.error('暂停测试失败:', error)
        } finally {
          isControlling.value = false
        }
      }
    }
  }

  async function stopTest() {
    if (currentTaskId.value && !isControlling.value) {
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
          await tasksApi.control(currentTaskId.value, 'stop')
          isPaused.value = false
        } catch (error: any) {
          console.error('停止测试失败:', error)
        } finally {
          isControlling.value = false
        }
      }
    }
  }

  async function resumeTest() {
    if (currentTaskId.value && !isControlling.value) {
      isControlling.value = true
      try {
        await tasksApi.control(currentTaskId.value, 'resume')
        isPaused.value = false
      } catch (error: any) {
        console.error('继续测试失败:', error)
      } finally {
        isControlling.value = false
      }
    }
  }

  function setCurrentTaskId(taskId: string | null) {
    currentTaskId.value = taskId
  }

  function reset() {
    currentStep.value = initialStep
    currentTaskId.value = null
    isPaused.value = false
    isControlling.value = false
  }

  return {
    currentStep,
    currentTaskId,
    isPaused,
    isControlling,
    nextStep,
    prevStep,
    goToStep,
    pauseTest,
    stopTest,
    resumeTest,
    setCurrentTaskId,
    reset
  }
}