<template>
  <span
    class="case-id-badge"
    :title="copied ? '已复制' : '点击复制ID'"
    @click.stop="handleCopy"
    @keydown.enter.prevent.stop="handleCopy"
    tabindex="0"
    role="button"
    :aria-label="`用例ID: ${caseId}, 点击复制`"
  >
    <i class="fas fa-copy"></i> 用例ID: {{ caseId }}
    <span class="case-id-copied" v-if="copied">已复制</span>
  </span>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue';
import { copyToClipboard } from '../../utils/utils';

const props = defineProps<{
  caseId: string | number | null | undefined;
}>();

const copied = ref(false);
let timer: ReturnType<typeof setTimeout> | null = null;

const handleCopy = async () => {
  const id = props.caseId;
  if (id === undefined || id === null) return;
  const ok = await copyToClipboard(String(id));
  if (ok) {
    copied.value = true;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      copied.value = false;
    }, 1500);
  }
};

onUnmounted(() => {
  if (timer) clearTimeout(timer);
});
</script>

<style scoped>
.case-id-badge {
  padding: 2px 10px;
  background: white;
  color: #1677ff;
  border-radius: var(--border-radius-sm, 4px);
  font-size: var(--font-size-xs, 12px);
  font-weight: var(--font-weight-medium, 500);
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.case-id-badge:hover,
.case-id-badge:focus-visible {
  background: #f8fafc;
  color: #1677ff;
  outline: none;
}

.case-id-badge:active {
  transform: translateY(1px);
}

.case-id-badge .fa-copy {
  font-size: 10px;
}

.case-id-copied {
  color: #16a34a;
  font-weight: 600;
  margin-left: 2px;
}
</style>
