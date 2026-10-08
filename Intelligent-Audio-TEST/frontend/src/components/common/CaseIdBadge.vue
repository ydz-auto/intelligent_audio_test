<template>
  <span class="case-id-badge"
        :title="copied ? '已复制' : '点击复制ID'"
        @click.stop="handleCopy"
        @keydown.enter.prevent.stop="handleCopy"
        tabindex="0"
        role="button"
        :aria-label="`用例ID: ${caseId}, 点击复制`">
    <i class="fas fa-copy"></i> 用例ID: {{ caseId }}
    <span class="case-id-copied" v-if="copied">已复制</span>
  </span>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue';
import { copyToClipboard } from '../../utils/utils';

const props = defineProps<{ caseId: string | number | null | undefined }>();

const copied = ref(false);
let timer: ReturnType<typeof setTimeout> | null = null;

const handleCopy = async () => {
  const id = props.caseId;
  if (id === undefined || id === null) return;
  const ok = await copyToClipboard(String(id));
  if (ok) {
    copied.value = true;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { copied.value = false; }, 1500);
  }
};

onUnmounted(() => { if (timer) clearTimeout(timer); });
</script>

<style scoped>
.case-id-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 3px;
  background: var(--color-slate-100);
  color: var(--color-slate-600);
  font-size: 12px;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.case-id-badge:hover {
  background: var(--color-slate-200);
  color: var(--color-slate-800);
}

.case-id-copied {
  color: var(--color-green-600);
  font-weight: 600;
}
</style>