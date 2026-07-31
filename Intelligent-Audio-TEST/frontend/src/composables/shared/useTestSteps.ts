import { ref, computed } from 'vue'

/**
 * 步骤导航：管理 currentStep 和下一步/上一步/跳转
 * 不包含任何测试业务逻辑，仅做步骤指针的移动
 */
export function useTestSteps(maxStep = 4) {
  const currentStep = ref(0)

  const goToStep = (step: number) => {
    if (step >= 0 && step <= maxStep) {
      currentStep.value = step
    }
  }

  return {
    currentStep,
    goToStep,
  }
}
