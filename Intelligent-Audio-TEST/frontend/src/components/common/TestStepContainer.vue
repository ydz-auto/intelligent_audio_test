<template>
  <div class="step-panel" :class="{ active: isActive }" :id="panelId">
    <!-- 步骤头部 -->
    <div v-if="title && showHeader" class="step-header">
      <h3 class="step-title">{{ title }}</h3>
      <slot name="header-extra"></slot>
    </div>

    <!-- 步骤主要内容 -->
    <div class="step-body">
      <slot></slot>
    </div>

    <!-- 步骤底部导航按钮 -->
    <div v-if="showActions" class="step-actions">
      <slot name="actions">
        <button v-if="showPrev" class="btn btn-secondary" @click="$emit('prev')">
          <i class="fas fa-arrow-left"></i> {{ prevLabel }}
        </button>
        <div class="actions-spacer"></div>
        <button v-if="showNext" class="btn btn-primary" :disabled="nextDisabled" @click="$emit('next')">
          {{ nextLabel }} <i class="fas fa-arrow-right"></i>
        </button>
      </slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  isActive: { type: Boolean, default: false },
  panelId: String,
  title: String,
  showHeader: { type: Boolean, default: true },
  showActions: { type: Boolean, default: true },
  showPrev: { type: Boolean, default: true },
  showNext: { type: Boolean, default: true },
  prevLabel: { type: String, default: '上一步' },
  nextLabel: { type: String, default: '下一步' },
  nextDisabled: { type: Boolean, default: false }
});

defineEmits(['prev', 'next']);
</script>

<style scoped>
.step-panel {
  display: none;
  animation: fadeIn 0.3s ease;
}

.step-panel.active {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.step-header {
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.step-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #2d3748;
}

.step-body {
  flex: 1;
  padding-bottom: 20px;
}

.actions-spacer {
  flex: 1;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
