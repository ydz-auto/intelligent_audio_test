<template>
  <div class="rule-editor">
    <div class="editor-header">
      <button type="button" class="btn-add" @click="addRule">
        <i class="fas fa-plus"></i>添加规则
      </button>
      <span class="editor-hint">配置评分规则：根据结果值区间映射得分</span>
    </div>

    <div class="rules-table" v-if="localValue && localValue.rules && localValue.rules.length > 0">
      <div class="table-header">
        <span class="th-condition">条件</span>
        <span class="th-value">结果值</span>
        <span class="th-score">得分</span>
        <span class="th-action">操作</span>
      </div>
      
      <div class="table-body">
        <div class="rule-row" v-for="(rule, index) in localValue.rules" :key="index">
          <span class="row-label">如果结果</span>
          <select v-model="rule.condition" @change="handleChange" class="condition-select">
            <option value=">=">≥ 大于等于</option>
            <option value=">">> 大于</option>
            <option value="==">= 等于</option>
            <option value="<">< 小于</option>
            <option value="<=">≤ 小于等于</option>
          </select>
          <input 
            type="number" 
            v-model.number="rule.value" 
            placeholder="结果值"
            class="value-input"
            @input="handleChange"
            step="0.1"
          />
          <span class="row-label">则得分</span>
          <input 
            type="number" 
            v-model.number="rule.score" 
            placeholder="分数"
            class="score-input"
            @input="handleChange"
            step="0.1"
          />
          <button type="button" class="btn-remove" @click="removeRule(index)">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>
    
    <div class="empty-state" v-else>
      <i class="fas fa-list-ol"></i>
      <p>暂无评分规则配置</p>
      <p class="hint">点击上方"添加规则"按钮配置评分规则</p>
    </div>

    <div class="default-score">
      <label>默认得分：</label>
      <input 
        type="number" 
        v-model.number="localValue.defaultScore" 
        placeholder="0"
        class="default-input"
        @input="handleChange"
        step="0.1"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({
      rules: [],
      defaultScore: 0
    })
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const localValue = ref({
  rules: [],
  defaultScore: 0
})

watch(() => props.modelValue, (newVal) => {
  if (newVal && typeof newVal === 'object') {
    localValue.value = {
      rules: newVal.rules ? [...newVal.rules] : [],
      defaultScore: newVal.defaultScore !== undefined ? newVal.defaultScore : 0
    }
  } else {
    localValue.value = { rules: [], defaultScore: 0 }
  }
}, { immediate: true, deep: true })

function addRule() {
  if (!localValue.value.rules) {
    localValue.value.rules = []
  }
  localValue.value.rules.push({
    condition: '>=',
    value: 0,
    score: 0
  })
  handleChange()
}

function removeRule(index) {
  localValue.value.rules.splice(index, 1)
  handleChange()
}

function handleChange() {
  emit('update:modelValue', localValue.value)
  emit('change', localValue.value)
}
</script>

<style scoped>
.rule-editor {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.editor-hint {
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

.rules-table {
  display: flex;
  flex-direction: column;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  background: white;
  margin-bottom: 16px;
}

.table-header {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  align-items: center;
}

.th-condition {
  flex: 1;
}

.th-value {
  width: 100px;
}

.th-score {
  width: 100px;
}

.th-action {
  width: 40px;
}

.table-body {
  display: flex;
  flex-direction: column;
}

.rule-row {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #f1f5f9;
  align-items: center;
}

.rule-row:last-child {
  border-bottom: none;
}

.row-label {
  font-size: 14px;
  color: #64748b;
  white-space: nowrap;
}

.condition-select {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  flex: 1;
  min-width: 120px;
}

.value-input {
  width: 100px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
}

.score-input {
  width: 100px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
}

.condition-select:focus,
.value-input:focus,
.score-input:focus {
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
  margin-bottom: 16px;
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

.default-score {
  display: flex;
  align-items: center;
  gap: 12px;
}

.default-score label {
  font-size: 14px;
  font-weight: 500;
  color: #334155;
}

.default-input {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  width: 100px;
}

.default-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
</style>
