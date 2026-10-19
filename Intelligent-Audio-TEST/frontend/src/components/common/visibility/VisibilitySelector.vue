<template>
  <div class="visibility-selector" role="radiogroup" :aria-label="'可见性'">
    <label class="vis-option" :class="{ 'vis-option--active': modelValue === Visibility.SHARED }">
      <input
        type="radio"
        :name="name"
        :value="Visibility.SHARED"
        :checked="modelValue === Visibility.SHARED"
        @change="onChange(Visibility.SHARED)"
      >
      <span class="vis-option__icon"><i class="fas fa-users"></i></span>
      <span class="vis-option__main">
        <span class="vis-option__label">共享</span>
        <span class="vis-option__desc">所有有权限的用户可见（默认）</span>
      </span>
    </label>
    <label class="vis-option" :class="{ 'vis-option--active': modelValue === Visibility.PRIVATE }">
      <input
        type="radio"
        :name="name"
        :value="Visibility.PRIVATE"
        :checked="modelValue === Visibility.PRIVATE"
        @change="onChange(Visibility.PRIVATE)"
      >
      <span class="vis-option__icon"><i class="fas fa-lock"></i></span>
      <span class="vis-option__main">
        <span class="vis-option__label">私有</span>
        <span class="vis-option__desc">仅自己可见和操作</span>
      </span>
    </label>
  </div>
</template>

<script setup lang="ts">
/**
 * VisibilitySelector —— 新建/编辑表单可见性选择器（INT-423/467）。
 * 默认共享；切换时父级负责落 localStorage 偏好（setVisibilityPref）。
 */
import { Visibility, type VisibilityType } from '@/domain/enums'

withDefaults(defineProps<{
  modelValue?: VisibilityType
  name?: string
}>(), {
  modelValue: Visibility.SHARED,
  name: 'visibility',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: VisibilityType): void
  (e: 'change', value: VisibilityType): void
}>()

function onChange(value: VisibilityType) {
  emit('update:modelValue', value)
  emit('change', value)
}
</script>

<style scoped>
.visibility-selector {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.vis-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid var(--border-color, #d0d5dd);
  border-radius: var(--radius-control);
  cursor: pointer;
  background: var(--background-primary, #fff);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  min-width: 180px;
}

.vis-option input[type='radio'] {
  margin-top: 3px;
}

.vis-option--active {
  border-color: var(--primary-color, #ff6a00);
  box-shadow: 0 0 0 1px var(--primary-color, #ff6a00);
}

.vis-option__icon {
  color: var(--text-secondary, #64748b);
  font-size: 14px;
  margin-top: 1px;
}

.vis-option--active .vis-option__icon {
  color: var(--primary-color, #ff6a00);
}

.vis-option__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.vis-option__label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
}

.vis-option__desc {
  font-size: 12px;
  color: var(--text-light, #94a3b8);
}
</style>
