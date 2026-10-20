<template>
  <div class="progress-nav">
    <template v-for="(label, index) in visibleSteps" :key="index">
      <div
        class="progress-step"
        :class="{ active: currentStep === index }"
        @click="goToStep(index)"
        :data-tooltip="tooltipFor(index)"
      >
        <div class="progress-step-number">{{ index + 1 }}</div>
        <div class="progress-step-label">{{ label }}</div>
        <div class="progress-tooltip">{{ tooltipFor(index) }}</div>
      </div>
      <div v-if="index < visibleSteps.length - 1" class="progress-line" :class="{ active: currentStep > index }"></div>
    </template>
  </div>
</template>

<script setup>
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed } from 'vue';

const props = defineProps({
  currentStep: { type: Number, default: 0 },
  stepLabels: { type: Array, default: () => [] },
  /** 步骤数（INT-486 合并流程 4 步；缺省 5 步兼容 E2E/API 向导） */
  stepCount: { type: Number, default: 5 },
  /** 每步 tooltips（与步骤一一对应，index 0..stepCount-1；合并流程四步传入覆盖默认） */
  stepTooltips: { type: Array, default: () => [] },
  stepTwoTooltip: { type: String, default: '' }
});

const emit = defineEmits(['go-to-step']);

const DEFAULT_LABELS = ['选择算法', '选择测试用例', '选择被测API', '执行测试', '查看结果'];
const DEFAULT_TOOLTIPS = [
  '选择测试算法',
  '选择要执行的测试用例和配置参数',
  '选择要测试的API端点或测试设备',
  '开始执行测试并监控进度',
  '查看和分析测试结果'
];

const visibleSteps = computed(() => {
  const count = Math.max(1, Math.min(props.stepCount, 5));
  return Array.from({ length: count }, (_, i) => props.stepLabels[i] || DEFAULT_LABELS[i]);
});

const tooltipFor = (index) => {
  if (props.stepTooltips && props.stepTooltips.length > index && props.stepTooltips[index] !== undefined) {
    return props.stepTooltips[index];
  }
  if (index === 2) return props.stepTwoTooltip || DEFAULT_TOOLTIPS[2];
  return DEFAULT_TOOLTIPS[index] || '';
};

const goToStep = (step) => {
  emit('go-to-step', step);
};
</script>

<style scoped>
/* 流程图样式将从全局CSS中继承，无需单独定义 */
</style>
