<template>
  <div class="load-error-state" role="alert">
    <i class="fas fa-exclamation-triangle"></i>
    <div class="load-error-text">
      <p class="load-error-title">加载失败</p>
      <p class="load-error-message">{{ message }}</p>
    </div>
    <button class="load-error-retry" :disabled="retrying" @click="$emit('retry')">
      <i class="fas fa-redo" :class="{ 'fa-spin': retrying }"></i>
      {{ retrying ? '重试中...' : '重试' }}
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * LoadErrorState —— 统一错误态组件（INT-288 A 域列表页加载/错误态补齐）。
 *
 * 呈现「错误条 + 重试按钮」：与空态/加载态视觉区分，宿主在拉取失败时保留
 * 旧数据并展示本组件，用户点击重试触发宿主重取。错误文案由 composable 暴露
 * （string），组件自身不感知数据源。
 */
defineProps<{
  /** 用户可见错误文案（如「加载任务失败，请稍后重试」） */
  message: string;
  /** 重试进行中（禁用按钮 + 图标旋转），可选 */
  retrying?: boolean;
}>();

defineEmits<{
  (e: 'retry'): void;
}>();
</script>

<style scoped>
.load-error-state {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #b91c1c;
}

.load-error-state > i {
  font-size: 20px;
  color: #dc2626;
  flex-shrink: 0;
}

.load-error-text {
  flex: 1;
  min-width: 0;
}

.load-error-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #991b1b;
}

.load-error-message {
  margin: 2px 0 0;
  font-size: 12px;
  color: #b91c1c;
  word-break: break-word;
}

.load-error-retry {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  border-radius: 6px;
  background-color: #dc2626;
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity 0.2s;
}

.load-error-retry:hover {
  opacity: 0.88;
}

.load-error-retry:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
