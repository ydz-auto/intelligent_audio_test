<template>
  <!-- 全局 Toast：Teleport 到固定元素容器，避免被 .main-content 的 transform 截获 fixed 包含块 -->
  <teleport to="#global-fixed-elements">
    <div v-if="toast" class="app-toast" :class="`app-toast--${toast.type}`" role="status">
      <i :class="toastIcon" aria-hidden="true"></i>
      <span>{{ toast.message }}</span>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ToastMessage } from '@/domain/model/ui';

const props = defineProps<{
  /** 当前 Toast 消息（null = 不渲染） */
  toast: ToastMessage | null;
}>();

const toastIcon = computed(() => {
  switch (props.toast?.type) {
    case 'success':
      return 'fas fa-check-circle';
    case 'error':
      return 'fas fa-exclamation-circle';
    case 'warning':
      return 'fas fa-exclamation-triangle';
    default:
      return 'fas fa-info-circle';
  }
});
</script>

<style scoped>
/* 样式全部走 token（--z-index-toast / --radius-md / --shadow-md / spacing），不硬编码 */
.app-toast {
  position: fixed;
  top: var(--spacing-lg);
  right: var(--spacing-lg);
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  z-index: var(--z-index-toast);
  animation: app-toast-slide-in 0.3s ease;
  box-shadow: var(--shadow-md);
  font-size: var(--font-size-sm);
}

.app-toast i {
  font-size: 1.2rem;
}

.app-toast--success {
  background-color: var(--color-green-50);
  color: var(--color-green-600);
  border: 1px solid var(--color-green-600);
}

.app-toast--error {
  background-color: var(--color-red-50);
  color: var(--color-red-600);
  border: 1px solid var(--color-red-600);
}

.app-toast--warning {
  background-color: var(--color-amber-50);
  color: var(--color-amber-600);
  border: 1px solid var(--color-amber-600);
}

.app-toast--info {
  background-color: var(--color-blue-50);
  color: var(--color-blue-600);
  border: 1px solid var(--color-blue-600);
}

@keyframes app-toast-slide-in {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
</style>
