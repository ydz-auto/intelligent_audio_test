<template>
  <div class="progress-nav">
    <div 
      class="progress-step" 
      :class="{ active: currentStep === 0 }" 
      @click="goToStep(0)" 
      data-tooltip="选择测试算法"
    >
      <div class="progress-step-number">1</div>
      <div class="progress-step-label">{{ stepLabels[0] || '选择算法' }}</div>
      <div class="progress-tooltip">选择测试算法</div>
    </div>
    <div class="progress-line" :class="{ active: currentStep > 0 }"></div>
    <div 
      class="progress-step" 
      :class="{ active: currentStep === 1 }" 
      @click="goToStep(1)" 
      data-tooltip="选择要执行的测试用例和配置参数"
    >
      <div class="progress-step-number">2</div>
      <div class="progress-step-label">{{ stepLabels[1] || '选择测试用例' }}</div>
      <div class="progress-tooltip">选择要执行的测试用例和配置参数</div>
    </div>
    <div class="progress-line" :class="{ active: currentStep > 1 }"></div>
    <div 
      class="progress-step" 
      :class="{ active: currentStep === 2 }" 
      @click="goToStep(2)" 
      data-tooltip="选择要测试的API端点或测试设备"
    >
      <div class="progress-step-number">3</div>
      <div class="progress-step-label">{{ stepLabels[2] || '选择被测API' }}</div>
      <div class="progress-tooltip">{{ stepTwoTooltip || '选择要测试的API端点或测试设备' }}</div>
    </div>
    <div class="progress-line" :class="{ active: currentStep > 2 }"></div>
    <div 
      class="progress-step" 
      :class="{ active: currentStep === 3 }" 
      @click="goToStep(3)" 
      data-tooltip="开始执行测试并监控进度"
    >
      <div class="progress-step-number">4</div>
      <div class="progress-step-label">{{ stepLabels[3] || '执行测试' }}</div>
      <div class="progress-tooltip">开始执行测试并监控进度</div>
    </div>
    <div class="progress-line" :class="{ active: currentStep > 3 }"></div>
    <div 
      class="progress-step" 
      :class="{ active: currentStep === 4 }" 
      @click="goToStep(4)" 
      data-tooltip="查看和分析测试结果"
    >
      <div class="progress-step-number">5</div>
      <div class="progress-step-label">{{ stepLabels[4] || '查看结果' }}</div>
      <div class="progress-tooltip">查看和分析测试结果</div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  currentStep: {type: Number, default: 0},
  stepLabels: {type: Array, default: () => []},
  stepTwoTooltip: {type: String, default: ''}
});

const emit = defineEmits(['go-to-step']);

const goToStep = (step) => {
  emit('go-to-step', step);
};
</script>

<style scoped>
/* 流程图样式将从全局CSS中继承，无需单独定义 */
</style>
