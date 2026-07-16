<template>
  <div class="output-fields-editor">
    <div class="inputs-header">
      <button type="button" class="btn-add" @click="addField">
        <i class="fas fa-plus"></i>添加输出字段
      </button>
      <span class="inputs-hint">配置评估结果提取字段及聚合角色（用于报告统计）</span>
    </div>

    <div class="inputs-table" v-if="localValue && localValue.length > 0">
      <div class="table-header">
        <span class="th-index">#</span>
        <span class="th-key">字段代码</span>
        <span class="th-label">显示标签</span>
        <span class="th-path">提取路径</span>
        <span class="th-type">字段类型</span>
        <span class="th-role">字段角色</span>
        <span class="th-agg">聚合角色</span>
        <span class="th-default">默认值</span>
        <span class="th-visible">显示</span>
        <span class="th-action">操作</span>
      </div>

      <div class="table-body">
        <div class="input-row" v-for="(field, index) in localValue" :key="index">
          <span class="row-index">{{ index + 1 }}</span>
          <input
            type="text"
            v-model="field.param_code"
            placeholder="如: wer"
            class="key-input"
            @input="handleChange"
          />
          <input
            type="text"
            v-model="field.param_name"
            placeholder="如: WER值"
            class="label-input"
            @input="handleChange"
          />
          <input
            type="text"
            v-model="field.field_path"
            placeholder="如: wer 或 data.result.wer"
            class="path-input"
            @input="handleChange"
          />
          <select v-model="field.field_type" @change="handleChange" class="type-select">
            <option value="number">数字</option>
            <option value="text">文本</option>
            <option value="boolean">布尔</option>
            <option value="json">JSON</option>
          </select>
          <select v-model="field.output_role" @change="handleChange" class="role-select">
            <option value="main">主结果</option>
            <option value="aux">辅助字段</option>
          </select>
          <select v-model="field.agg_role" @change="handleChange" class="agg-select">
            <option value="">无</option>
            <option value="value">直接值</option>
            <option value="numerator">分子</option>
            <option value="denominator">分母</option>
          </select>
          <input
            type="text"
            v-model="field.default_value"
            placeholder="如: 0 或空"
            class="default-input"
            @input="handleChange"
          />
          <label class="visible-checkbox">
            <input
              type="checkbox"
              :checked="field.visible_in_report !== false"
              @change="field.visible_in_report = $event.target.checked; handleChange()"
            />
          </label>
          <button type="button" class="btn-remove" @click="removeField(index)">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <div class="empty-state" v-else>
      <i class="fas fa-inbox"></i>
      <p>暂无输出字段配置</p>
      <p class="hint">配置从评估响应中提取哪些字段作为结果（如 WER 维度配 wer/errors/length）</p>
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

function addField() {
  if (!localValue.value) {
    localValue.value = []
  }
  localValue.value.push({
    param_code: '',
    param_name: '',
    field_path: '',
    field_type: 'number',
    output_role: 'main',
    agg_role: '',
    default_value: '',
    visible_in_report: true
  })
  handleChange()
}

function removeField(index) {
  localValue.value.splice(index, 1)
  handleChange()
}

function handleChange() {
  emit('update:modelValue', localValue.value)
  emit('change', localValue.value)
}
</script>

<style scoped>
.output-fields-editor {
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

.th-index { width: 24px; text-align: center; flex-shrink: 0; }
.th-key { flex: 1; }
.th-label { flex: 1; }
.th-path { flex: 1.3; }
.th-type { width: 80px; flex-shrink: 0; }
.th-role { width: 90px; flex-shrink: 0; }
.th-agg { width: 90px; flex-shrink: 0; }
.th-default { flex: 1; }
.th-visible { width: 50px; flex-shrink: 0; text-align: center; }
.th-action { width: 40px; flex-shrink: 0; }

.key-input,
.label-input,
.path-input,
.default-input {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  width: 100%;
  box-sizing: border-box;
}

.key-input { flex: 1; }
.label-input { flex: 1; }
.path-input { flex: 1.3; }
.default-input { flex: 1; }

.type-select,
.role-select,
.agg-select {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  flex-shrink: 0;
}

.type-select { width: 80px; }
.role-select { width: 90px; }
.agg-select { width: 90px; }

.visible-checkbox {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  flex-shrink: 0;
}

.visible-checkbox input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.key-input:focus,
.label-input:focus,
.path-input:focus,
.default-input:focus,
.type-select:focus,
.role-select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
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
