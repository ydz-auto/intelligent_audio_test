<template>
  <div class="required-inputs-editor">
    <div class="inputs-header">
      <button type="button" class="btn-add" @click="addInput">
        <i class="fas fa-plus"></i>添加输入参数
      </button>
      <span class="inputs-hint">配置评估所需的输入参数</span>
    </div>

    <div class="inputs-table" v-if="localValue && localValue.length > 0">
      <div class="table-header">
        <span class="th-index">#</span>
        <span class="th-key">参数键名</span>
        <span class="th-label">显示标签</span>
        <span class="th-source">字段类型</span>
        <span class="th-required">必填</span>
        <span class="th-default">默认值</span>
        <span class="th-desc">描述</span>
        <span class="th-action">操作</span>
      </div>

      <div class="table-body">
        <div class="input-row" v-for="(input, index) in localValue" :key="index">
          <span class="row-index">{{ index + 1 }}</span>
          <input
            type="text"
            v-model="input.param_code"
            placeholder="如: asr_result"
            class="key-input"
            @input="handleChange"
          />
          <input
            type="text"
            v-model="input.param_name"
            placeholder="如: ASR识别结果"
            class="label-input"
            @input="handleChange"
          />
          <select v-model="input.field_type" @change="handleChange" class="source-select">
            <option value="text">文本</option>
            <option value="number">数字</option>
            <option value="audio">音频</option>
            <option value="boolean">布尔</option>
            <option value="json">JSON</option>
          </select>
          <label class="checkbox-wrapper">
            <input
              type="checkbox"
              v-model="input.required"
              @change="handleChange"
            />
          </label>
          <input
            type="text"
            v-model="input.default_value"
            placeholder="如: 0 或空字符串"
            class="default-input"
            @input="handleChange"
          />
          <input
            type="text"
            v-model="input.help_text"
            placeholder="参数说明"
            class="desc-input"
            @input="handleChange"
          />
          <button type="button" class="btn-remove" @click="removeInput(index)">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <div class="empty-state" v-else>
      <i class="fas fa-inbox"></i>
      <p>暂无输入参数配置</p>
      <p class="hint">点击上方"添加输入参数"按钮配置评估所需的输入数据</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const localValue = ref([])

watch(() => props.modelValue, (newVal) => {
  if (newVal && Array.isArray(newVal)) {
    localValue.value = JSON.parse(JSON.stringify(newVal))
  } else {
    localValue.value = []
  }
}, { immediate: true, deep: true })

function addInput() {
  if (!localValue.value) {
    localValue.value = []
  }
  localValue.value.push({
    param_code: '',
    param_name: '',
    field_type: 'text',
    required: true,
    default_value: '',
    help_text: ''
  })
  handleChange()
}

function removeInput(index) {
  localValue.value.splice(index, 1)
  handleChange()
}

function handleChange() {
  emit('update:modelValue', localValue.value)
  emit('change', localValue.value)
}
</script>

<style scoped>
.required-inputs-editor {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
}

.inputs-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.inputs-hint {
  font-size: 12px;
  color: #64748b;
}

.btn-add {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-add:hover {
  background: #2563eb;
}

.inputs-table {
  display: flex;
  flex-direction: column;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  background: white;
}

.table-header {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
}

.table-body {
  display: flex;
  flex-direction: column;
}

.input-row {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #f1f5f9;
  align-items: center;
}

.input-row:last-child {
  border-bottom: none;
}

.row-index {
  width: 24px;
  text-align: center;
  font-weight: 600;
  color: #64748b;
  font-size: 12px;
  flex-shrink: 0;
}

.th-index {
  width: 24px;
  text-align: center;
  flex-shrink: 0;
}

.th-key {
  flex: 1;
}

.th-label {
  flex: 1.2;
}

.th-source {
  width: 100px;
  flex-shrink: 0;
}

.th-required {
  width: 50px;
  text-align: center;
  flex-shrink: 0;
}

.th-default {
  flex: 1;
}

.th-desc {
  flex: 1.5;
}

.th-action {
  width: 40px;
  flex-shrink: 0;
}

.key-input,
.label-input,
.default-input,
.desc-input {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  width: 100%;
  box-sizing: border-box;
}

.key-input {
  flex: 1;
}

.label-input {
  flex: 1.2;
}

.default-input {
  flex: 1;
}

.desc-input {
  flex: 1.5;
}

.source-select {
  width: 100px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  flex-shrink: 0;
}

.key-input:focus,
.label-input:focus,
.default-input:focus,
.desc-input:focus,
.source-select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.checkbox-wrapper {
  width: 50px;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

.checkbox-wrapper input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.btn-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: #ef4444;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.btn-remove:hover {
  background: #fee2e2;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #94a3b8;
  background: white;
  border: 1px dashed #e2e8f0;
  border-radius: 8px;
}

.empty-state i {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.empty-state .hint {
  margin-top: 8px;
  font-size: 12px;
}
</style>
