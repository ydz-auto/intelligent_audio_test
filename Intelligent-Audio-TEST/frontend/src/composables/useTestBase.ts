import { ref } from 'vue'

export interface UseTestBaseOptions {
  totalSteps: number
  initialStep?: number
}

export function useTestBase(options: UseTestBaseOptions) {
  const { totalSteps, initialStep = 0 } = options

  const currentStep = ref(initialStep)
  const currentTaskId = ref<string | number | null>(null)

  function nextStep() {
    if (currentStep.value < totalSteps - 1) {
      currentStep.value++
    }
  }

  function prevStep() {
    if (currentStep.value > 0) {
      currentStep.value--
    }
  }

  function goToStep(step: number) {
    if (step >= 0 && step < totalSteps) {
      currentStep.value = step
    }
  }

  function setCurrentTaskId(taskId: string | number | null) {
    currentTaskId.value = taskId
  }

  function reset() {
    currentStep.value = initialStep
    currentTaskId.value = null
  }

  return {
    currentStep,
    currentTaskId,
    nextStep,
    prevStep,
    goToStep,
    setCurrentTaskId,
    reset
  }
}