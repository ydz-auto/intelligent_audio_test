<template>
  <span
    v-if="visibility === Visibility.PRIVATE"
    class="vis-badge vis-badge--private"
    :title="'私有：仅创建者和管理员可见'"
  >
    <i class="fas fa-lock"></i>
    私有
  </span>
</template>

<script setup lang="ts">
/**
 * VisibilityBadge —— 列表行可见性徽标（INT-423/467）。
 * 仅私有资源展示（带小锁图标）；共享为默认态不展示，减少视觉噪音。
 */
import { Visibility } from '@/domain/enums'

defineProps<{
  visibility?: string | null
}>()
</script>

<style scoped>
.vis-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
  vertical-align: middle;
}

.vis-badge--private {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.vis-badge--private i {
  font-size: 10px;
}
</style>
