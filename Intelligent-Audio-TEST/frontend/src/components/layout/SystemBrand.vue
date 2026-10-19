<template>
  <router-link to="/" class="system-brand" :class="{ 'system-brand--compact': compact }">
    <span class="system-brand__icon">
      <i class="fas fa-headset"></i>
    </span>
    <span v-if="!compact" class="system-brand__text">
      <span class="system-brand__name">{{ brandName }}</span>
      <span class="system-brand__sub">智能语音测试</span>
    </span>
  </router-link>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSiteName } from '../../infrastructure/api/optionsApi'

defineProps<{
  compact?: boolean
}>()

const brandName = ref('智能语音测试系统')

onMounted(async () => {
  const name = await getSiteName()
  if (name) brandName.value = name
})
</script>

<style scoped>
.system-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  height: 100%;
}
.system-brand__icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-10);
  background: var(--accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--primary);
  flex-shrink: 0;
}
.system-brand__text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
  white-space: nowrap;
}
.system-brand__name {
  font-size: 16px;
  font-weight: 700;
  color: var(--foreground);
}
.system-brand__sub {
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
