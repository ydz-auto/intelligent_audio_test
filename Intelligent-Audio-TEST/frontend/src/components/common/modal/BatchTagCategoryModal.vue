<template>
  <div class="batch-tag-category-modal">
    <div class="modal-header">
      <p class="tag-count">将为 {{ tagCount }} 个标签修改所属分类</p>
    </div>

    <div class="modal-body">
      <div class="form-group">
        <label>目标分类 <span class="required">*</span></label>
        <select v-model="selectedCategoryId" class="form-input custom-select">
          <option :value="null">未分类</option>
          <option v-for="cat in categories" :key="cat.id" :value="cat.id">
            {{ cat.name }}
          </option>
        </select>
      </div>
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm">确定</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { ref } from 'vue'
import type { TagCategory } from '@/domain/model/tag'

interface Props {
  modalId: string
  title?: string
  tagCount?: number
  categories?: TagCategory[]
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { categoryId: number | null }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量改分类',
  tagCount: 0,
  categories: () => []
})

const emit = defineEmits<Emits>()

/** 目标分类：null = 未分类（后端 batch-category 接受 category_id 为 null 移入未分类） */
const selectedCategoryId = ref<number | null>(null)

function handleConfirm() {
  emit('confirm', { categoryId: selectedCategoryId.value })
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.batch-tag-category-modal {
  padding: 20px;
}

/* 标题由 BasicModal 注入（defaultConfig.title），本体内仅保留说明行 */
.tag-count {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground, var(--color-slate-500));
}

.modal-body {
  margin-top: 16px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group > label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: var(--foreground);
}

.required {
  color: var(--destructive);
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: var(--background);
  color: var(--foreground);
}

.form-input:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--secondary) 10%, transparent);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-gray-200);
}

.btn {
  padding: 8px 20px;
  border-radius: var(--radius-md);
  font-size: 14px;
  cursor: pointer;
  border: none;
}

.btn-secondary {
  background: var(--muted);
  color: var(--foreground);
}

.btn-primary {
  background: var(--secondary);
  color: var(--background);
}

.btn-primary:disabled {
  background: var(--color-gray-300);
  cursor: not-allowed;
}
</style>
