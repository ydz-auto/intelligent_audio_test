<template>
  <div class="tag-edit-form">
    <div class="form-group">
      <label>标签名称 <span class="required">*</span></label>
      <input 
        type="text" 
        v-model="form.name" 
        placeholder="如：1人、2人、会议室"
        :maxlength="50"
        class="form-input"
        ref="nameInput"
      />
      <span class="char-count">{{ form.name.length }}/50</span>
    </div>
    <div class="form-group">
      <label>所属分类</label>
      <select v-model="form.categoryId" class="form-input">
        <option :value="null">未分类</option>
        <option v-for="cat in categories" :key="cat.id" :value="cat.id">
          {{ cat.name }}
        </option>
      </select>
    </div>
    <div class="form-group">
      <label>描述</label>
      <textarea 
        v-model="form.description" 
        placeholder="标签描述"
        :maxlength="500"
        class="form-input"
      ></textarea>
      <span class="char-count">{{ form.description.length }}/500</span>
    </div>
    <div class="form-group">
      <label>颜色</label>
      <div class="color-picker">
        <input type="color" v-model="form.color" />
        <span class="color-value">{{ form.color }}</span>
      </div>
    </div>
    <div v-if="errorMessage" class="error-message">{{ errorMessage }}</div>
    <div class="form-actions">
      <button class="btn btn-secondary" @click="handleCancel">取消</button>
      <button class="btn btn-primary" @click="handleConfirm" :disabled="!isFormValid || saving">
        {{ saving ? '保存中...' : (isEdit ? '保存' : '创建') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import api from '@/utils/api';
import type { TagItem, TagCategory } from '@/utils/api';

const props = defineProps<{
  tag?: TagItem | null;
  categoryId?: number | null;
  categories?: TagCategory[];
}>();

const emit = defineEmits<{
  (e: 'confirm', data: TagItem): void;
  (e: 'cancel'): void;
}>();

const nameInput = ref<HTMLInputElement | null>(null);
const saving = ref(false);
const errorMessage = ref('');

const isEdit = computed(() => !!props.tag);

const form = ref({
  name: '',
  description: '',
  color: '#10b981',
  categoryId: null as number | null
});

const isFormValid = computed(() => {
  const name = form.value.name.trim();
  return name.length > 0 && name.length <= 50;
});

onMounted(async () => {
  if (props.tag) {
    form.value = {
      name: props.tag.name,
      description: props.tag.description || '',
      color: props.tag.color || '#10b981',
      categoryId: props.tag.categoryId || null
    };
  } else {
    form.value.categoryId = props.categoryId || null;
  }
  
  await nextTick();
  nameInput.value?.focus();
});

async function handleConfirm() {
  if (!isFormValid.value || saving.value) return;
  
  errorMessage.value = '';
  saving.value = true;
  try {
    const data = {
      name: form.value.name.trim(),
      description: form.value.description.trim(),
      color: form.value.color,
      categoryId: form.value.categoryId
    };
    
    let result: TagItem;
    if (props.tag) {
      result = await api.tags.updateTag(props.tag.id, data);
    } else {
      result = await api.tags.createTag(data);
    }
    
    emit('confirm', result);
  } catch (e: any) {
    console.error('保存标签失败:', e);
    errorMessage.value = e?.message || '保存标签失败，请重试';
  } finally {
    saving.value = false;
  }
}

function handleCancel() {
  emit('cancel');
}
</script>

<style scoped>
.tag-edit-form {
  padding: 0;
}

.form-group {
  margin-bottom: 20px;
  position: relative;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: var(--text-primary, #334155);
  font-size: 14px;
}

.required {
  color: var(--danger-color, #ef4444);
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  transition: all 0.2s;
  background: var(--input-bg, #fff);
}

.form-input:focus {
  outline: none;
  border-color: var(--primary-color, #6366f1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

textarea.form-input {
  min-height: 80px;
  resize: vertical;
}

.char-count {
  position: absolute;
  right: 0;
  bottom: -18px;
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
}

.color-picker {
  display: flex;
  align-items: center;
  gap: 12px;
}

input[type="color"] {
  height: 40px;
  padding: 4px;
  width: 60px;
  cursor: pointer;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
}

.color-value {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  font-family: monospace;
}

.error-message {
  color: var(--danger-color, #ef4444);
  font-size: 13px;
  margin-bottom: 12px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color, #e2e8f0);
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-primary {
  background: var(--primary-color, #6366f1);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover, #4f46e5);
}

.btn-primary:disabled {
  background: var(--disabled-bg, #cbd5e1);
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--btn-secondary-bg, #f1f5f9);
  color: var(--text-secondary, #475569);
  border: 1px solid var(--border-color, #e2e8f0);
}

.btn-secondary:hover {
  background: var(--btn-secondary-hover, #e2e8f0);
}
</style>
