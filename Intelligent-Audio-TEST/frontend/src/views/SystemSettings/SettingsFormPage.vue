<template>
  <div class="settings-form-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i :class="icon"></i>
          {{ title }}
        </h2>
        <p v-if="description" class="page-description">{{ description }}</p>
      </div>
      <div v-if="dirty" class="dirty-indicator">
        <i class="fas fa-circle"></i>
        未保存的更改
      </div>
    </div>

    <p v-if="error" class="error-msg">{{ error }}</p>
    <p v-if="notice" class="success-msg">{{ notice }}</p>

    <div class="card settings-card">
      <div v-if="loading" class="card-body empty-state">
        <i class="fas fa-spinner fa-spin"></i> 加载中...
      </div>
      <div v-else class="card-body">
        <div class="settings-form-grid">
          <FormField
            v-for="field in fields"
            :key="field.key"
            v-model="values[field.key]"
            :field="toFormField(field)"
          />
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" :disabled="saving || !dirty" @click="save">
            <i class="fas fa-save btn-icon"></i>{{ saving ? '保存中...' : '保存设置' }}
          </button>
          <button class="btn btn-secondary" :disabled="saving" @click="reset">
            <i class="fas fa-undo btn-icon"></i>重置
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import FormField from '@/components/common/form/FormField.vue'
import { useOptionForm, type OptionFieldDef } from './useSettingsForm'

export interface SettingsFormField extends OptionFieldDef {
  label: string
  hint?: string
  required?: boolean
  placeholder?: string
}

const props = defineProps<{
  title: string
  description?: string
  icon?: string
  fields: SettingsFormField[]
}>()

const { values, loading, saving, dirty, error, notice, save, reset } =
  useOptionForm(props.fields)

function toFormField(field: SettingsFormField) {
  return {
    label: field.label,
    type: field.type === 'textarea' ? 'textarea' : field.type,
    hint: field.hint,
    required: field.required,
    placeholder: field.placeholder,
    rows: field.type === 'textarea' ? 6 : undefined,
  }
}
</script>

<style scoped>
.settings-form-page {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
}

.page-title {
  font-size: var(--font-size-xl);
  color: var(--foreground);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.page-title i {
  color: var(--primary-color);
}

.page-description {
  margin-top: var(--spacing-xs);
  font-size: 13px;
  color: var(--text-secondary);
}

.dirty-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--warning-dark);
}

.dirty-indicator i {
  font-size: 8px;
}

.settings-card {
  max-width: 720px;
}

.settings-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-md) var(--spacing-lg);
}

.settings-form-grid :deep(.form-group.full-width) {
  grid-column: 1 / -1;
}

.form-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--gray-light-color);
}

.error-msg {
  color: var(--destructive);
  font-size: 14px;
  margin-bottom: var(--spacing-sm);
}

.success-msg {
  color: var(--success-dark);
  font-size: 14px;
  margin-bottom: var(--spacing-sm);
}
</style>
