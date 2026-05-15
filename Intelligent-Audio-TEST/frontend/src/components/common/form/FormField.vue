<template>
  <div class="form-group" :class="{ 'full-width': field.fullWidth || false }">
    <label :for="fieldId">
      {{ field.label }}
      <span v-if="field.required" class="required-mark">*</span>
    </label>
    
    <input
      v-if="field.type === 'text' || field.type === 'number' || field.type === 'email' || field.type === 'url'"
      :id="fieldId"
      :type="field.type === 'url' ? 'text' : field.type"
      v-model="localValue"
      :placeholder="field.placeholder || `请输入${field.label}`"
      :required="field.required || false"
      :min="field.min"
      :max="field.max"
      :step="field.step"
      :disabled="field.disabled || false"
      @input="handleInput"
    />
    
    <textarea
      v-else-if="field.type === 'textarea'"
      :id="fieldId"
      v-model="localValue"
      :placeholder="field.placeholder || `请输入${field.label}`"
      :required="field.required || false"
      :rows="field.rows || 3"
      :maxlength="field.maxlength"
      :disabled="field.disabled || false"
      @input="handleInput"
    ></textarea>
    
    <template v-if="field.type === 'select'">
      <div v-if="field.action" class="select-with-button" :class="{ 'no-button': !field.text }">
        <div v-if="isEmptySelect && field.text" class="empty-select-guidance">
          <i class="fas fa-info-circle"></i>
          <span>无可用设备。请点击下方按钮扫描并添加设备。</span>
        </div>
        <select
          :id="fieldId"
          v-model="localValue"
          :required="field.required || false"
          @change="handleInput"
          @mousedown="handleSelectClick"
          :class="{ 'empty-select': isEmptySelect }"
          :disabled="field.disabled || false"
        >
          <option value="" v-if="!field.required">请选择</option>
          <option 
            v-for="option in field.options" 
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
        <button 
          v-if="field.text"
          type="button" 
          class="select-button"
          @click="handleButtonAction"
        >
          <i v-if="field.icon" :class="field.icon"></i>
          {{ field.text || '操作' }}
        </button>
      </div>
      <select
        v-else
        :id="fieldId"
        v-model="localValue"
        :required="field.required || false"
        @change="handleInput"
        :disabled="field.disabled || false"
      >
        <option value="" v-if="!field.required">请选择</option>
        <option 
          v-for="option in field.options" 
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </option>
      </select>
    </template>
    
    <div v-else-if="field.type === 'radio'" class="radio-group">
      <div 
        v-for="option in field.options" 
        :key="option.value"
        class="radio-item"
      >
        <input
          :id="`${fieldId}-${option.value}`"
          type="radio"
          v-model="localValue"
          :value="option.value"
          :name="fieldId"
          :required="field.required || false"
          :disabled="field.disabled || false"
          @change="handleInput"
        />
        <label :for="`${fieldId}-${option.value}`">{{ option.label }}</label>
      </div>
    </div>
    
    <div v-else-if="field.type === 'checkbox'" class="checkbox-group">
      <div 
        v-for="option in field.options" 
        :key="option.value"
        class="checkbox-item"
      >
        <input
          :id="`${fieldId}-${option.value}`"
          type="checkbox"
          v-model="localValue"
          :value="option.value"
          :disabled="field.disabled || false"
          @change="handleInput"
        />
        <label :for="`${fieldId}-${option.value}`">{{ option.label }}</label>
      </div>
    </div>
    
    <div v-else-if="field.type === 'switch'" class="switch-group">
      <input
        :id="fieldId"
        type="checkbox"
        v-model="localValue"
        class="switch-input"
        :disabled="field.disabled || false"
        @change="handleInput"
      />
      <label :for="fieldId" class="switch-label" @click="toggleSwitch"></label>
      <span class="switch-text">{{ localValue ? '开启' : '关闭' }}</span>
    </div>

    <div v-else-if="field.type === 'info'" class="info-field">
      <i class="fas fa-info-circle"></i>
      <span>{{ field.helpText || field.label || '' }}</span>
    </div>
    
    <input
      v-else-if="field.type === 'date' || field.type === 'datetime-local'"
      :id="fieldId"
      :type="field.type"
      v-model="localValue"
      :required="field.required || false"
      :disabled="field.disabled || false"
      @change="handleInput"
    />
    
    <div v-else-if="field.type === 'apiMeta'" class="api-meta-field">
      <div class="api-meta-row">
        <div class="api-protocol-wrapper">
          <label :for="`${fieldId}-protocol`" class="sub-label">协议</label>
          <select
              :id="`${fieldId}-protocol`"
              v-model="localValue.protocol"
              :disabled="field.disabled || false"
              @change="handleInput"
            >
            <option value="http">HTTP</option>
            <option value="https">HTTPS</option>
            <option value="ws">WebSocket (ws)</option>
            <option value="wss">WebSocket (wss)</option>
          </select>
        </div>
        <div class="api-environment-wrapper">
          <label :for="`${fieldId}-environment`" class="sub-label">环境</label>
          <select
              :id="`${fieldId}-environment`"
              v-model="localValue.environment"
              :disabled="field.disabled || false"
              @change="handleInput"
            >
            <option value="development">开发环境</option>
            <option value="testing">测试环境</option>
            <option value="production">生产环境</option>
          </select>
        </div>
        <div class="api-version-wrapper">
          <label :for="`${fieldId}-version`" class="sub-label">版本</label>
          <input
              :id="`${fieldId}-version`"
              type="text"
              v-model="localValue.version"
              placeholder="API版本 (如 v1)"
              :disabled="field.disabled || false"
              @input="handleInput"
            />
        </div>
      </div>
      <div class="api-meta-row">
        <div class="api-key-wrapper">
          <label :for="`${fieldId}-apiKey`" class="sub-label">API Key</label>
          <input
              :id="`${fieldId}-apiKey`"
              type="text"
              v-model="localValue.apiKey"
              placeholder="请输入API Key"
              class="full-width"
              :disabled="field.disabled || false"
              @input="handleInput"
            />
        </div>
      </div>
    </div>
    
    <div v-else-if="field.type === 'file'" class="file-upload">
      <input
        :id="fieldId"
        type="file"
        :accept="field.accept || '*/*'"
        @change="handleFileUpload"
        :multiple="field.multiple || false"
      />
      <div class="file-info" v-if="uploadedFile">
        <span class="file-name">{{ getFileName(uploadedFile) }}</span>
        <button 
          type="button" 
          class="remove-file-btn"
          @click="removeFile"
        >
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
    
    <div v-else-if="field.type === 'array'" class="array-field">
      <div 
        v-for="(item, index) in localValue" 
        :key="index" 
        class="array-item"
      >
        <div class="array-item-content">
          <div class="array-item-fields">
            <div class="array-item-field">
              <label class="sub-label">数字增益</label>
              <input
          type="number"
          :value="item.digitalGain || item.gain"
          @input="updateGainValue($event, item, index)"
          :placeholder="'请输入数字增益'"
          min="1"
          max="100"
          :disabled="field.disabled || false"
        />
            </div>
            <div class="array-item-field">
              <label class="sub-label">声压级 (dB)</label>
              <input
          type="number"
          v-model="item.spl"
          :placeholder="'请输入声压级'"
          @input="handleInput"
          min="0"
          max="120"
          step="0.1"
          :disabled="field.disabled || false"
        />
            </div>
          </div>
        </div>
        <button 
          type="button" 
          class="remove-array-item-btn"
          @click="removeArrayItem(index)"
        >
          <i class="fas fa-trash"></i>
        </button>
      </div>
      
      <button 
        type="button" 
        class="add-array-item-btn"
        @click="addArrayItem"
      >
        <i class="fas fa-plus"></i>
        添加增益点
      </button>
    </div>
    
    <button 
      v-else-if="field.type === 'button'" 
      type="button" 
      class="btn btn-primary"
      @click="handleButtonAction"
    >
      <i v-if="field.icon" :class="field.icon"></i>
      {{ field.text || '操作' }}
    </button>
    
    <div v-else-if="field.type === 'algorithmMultiSelect'" class="algorithm-multi-select">
      <AlgorithmParamsConfig
        v-model:supported-algorithms="localValue"
        v-model:algorithm-configs="algorithmConfigsValue"
        @update:supported-algorithms="handleAlgorithmChange"
      />
    </div>
    
    <div v-else-if="field.type === 'algorithmSelect'" class="algorithm-select">
      <select 
        :id="fieldKey" 
        v-model="localValue" 
        class="form-input"
        :disabled="field.disabled"
        @change="handleInput"
      >
        <option value="" disabled>{{ field.placeholder || '请选择算法类型' }}</option>
        <option 
          v-for="option in algorithmOptions" 
          :key="option.value" 
          :value="option.value"
        >
          {{ option.label }}
        </option>
      </select>
    </div>
    
    <div v-else-if="field.type === 'algorithmConfigs'" class="algorithm-configs-field">
      <AlgorithmParamsConfig
        v-model:supported-algorithms="supportedAlgorithmsValue"
        v-model:algorithm-configs="localValue"
        @update:algorithm-configs="handleAlgorithmConfigsChange"
      />
    </div>
    
    <div v-else-if="field.type === 'multi-select-tags'" class="multi-select-tags-field">
      <div class="tags-container">
        <div 
          v-for="option in field.options" 
          :key="option.value"
          class="tag-item"
          :class="{ 'selected': isTagSelected(option.value) }"
          @click="toggleTag(option.value)"
        >
          <span class="tag-label">{{ option.label }}</span>
          <span class="tag-check" v-if="isTagSelected(option.value)">✓</span>
        </div>
      </div>
    </div>
    
    <RequiredInputsEditor
      v-else-if="field.type === 'requiredInputs'"
      v-model="localValue"
      @change="handleInput"
    />
    
    <APISettingsEditor
      v-else-if="field.type === 'apiSettingsEditor'"
      v-model="localValue"
      @change="handleInput"
    />
    
    <RuleEditor
      v-else-if="field.type === 'ruleEditor'"
      v-model="localValue"
      @change="handleInput"
    />
    
    <p v-if="field.hint" class="field-hint">{{ field.hint }}</p>
    
    <p v-if="error" class="field-error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import AlgorithmParamsConfig from '../../algorithm/AlgorithmParamsConfig.vue'
import RequiredInputsEditor from './RequiredInputsEditor.vue'
import APISettingsEditor from './APISettingsEditor.vue'
import RuleEditor from './RuleEditor.vue'
import { useAlgorithmConfig } from '../../../composables/useAlgorithmConfig'

const props = defineProps({
  field: {type: Object, required: true},
  value: {type: [String, Number, Boolean, Array, Object], default: ''},
  error: {type: String, default: ''},
  modelValue: {type: [String, Number, Boolean, Array, Object], default: ''}
})

const emit = defineEmits(['update:value', 'update:modelValue', 'input', 'file-upload', 'button-action'])

const fieldId = `field-${props.field.key}`
const uploadedFile = ref(null)

const isEmptySelect = computed(() => {
  if (props.field.type !== 'select' || !props.field.options) return false
  
  if (props.field.options.length === 0) return true
  
  if (props.field.options.length === 1) {
    const opt = props.field.options[0]
    return opt.value === '' && (opt.label.includes('无设备可用') || opt.label.includes('无可用设备'))
  }
  
  return false
})

const getInitialValue = () => {
  const val = props.modelValue !== undefined ? props.modelValue : props.value;
  
  switch (props.field.type) {
    case 'array':
      return Array.isArray(val) ? val : [props.field.arrayItemTemplate || { spl: null, digitalGain: null }];
    case 'checkbox':
      return Array.isArray(val) ? val : [];
    case 'number':
      return val !== undefined && val !== null ? val : 0;
    case 'switch':
      return val !== undefined && val !== null ? val : false;
    case 'apiMeta':
      return val !== undefined && val !== null && typeof val === 'object' ? val : {protocol: 'https', environment: 'development', version: 'v1', apiKey: ''};
    case 'algorithmMultiSelect':
      return Array.isArray(val) ? val : [];
    case 'algorithmSelect':
      if (Array.isArray(val) && val.length > 0) {
        return val[0]
      }
      return '';
    case 'algorithmConfigs':
      return val !== undefined && val !== null && typeof val === 'object' ? val : {};
    case 'requiredInputs':
      return Array.isArray(val) ? val : [];
    case 'multi-select-tags':
      return Array.isArray(val) ? val : [];
    case 'apiSettingsEditor':
      return val !== undefined && val !== null && typeof val === 'object' ? val : {method: 'POST', headers: {}, body_template: {}, timeout: 30000};
    case 'ruleEditor':
      return val !== undefined && val !== null && typeof val === 'object' ? val : {rules: [], defaultScore: 0};
    default:
      return val !== undefined && val !== null ? val : '';
  }
};

const localValue = ref(getInitialValue())
const algorithmConfigsValue = ref({})
const supportedAlgorithmsValue = ref([])

const { algorithms, loadAlgorithms } = useAlgorithmConfig()

const algorithmOptions = computed(() => {
  return (algorithms.value || []).map(algo => ({
    value: algo.type,
    label: algo.name
  }))
})

onMounted(async () => {
  if (algorithmOptions.value.length === 0) {
    await loadAlgorithms()
  }
})

watch(() => props.modelValue, (newVal) => {
  if (newVal !== undefined) {
    if (props.field.type === 'algorithmSelect' && Array.isArray(newVal) && newVal.length > 0) {
      localValue.value = newVal[0]
    } else {
      localValue.value = newVal
    }
  }
})

watch(() => props.value, (newVal) => {
  if (newVal !== undefined) {
    if (props.field.type === 'algorithmSelect' && Array.isArray(newVal) && newVal.length > 0) {
      localValue.value = newVal[0]
    } else {
      localValue.value = newVal
    }
  }
})

watch(() => props.field.options, (newOptions) => {
  console.log(`[FormField] ${props.field.key} options changed: ${newOptions ? newOptions.length : 0} items`);
}, { deep: true })

const handleInput = () => {
  let valueToEmit = localValue.value
  if (props.field.type === 'algorithmSelect' && localValue.value && !Array.isArray(localValue.value)) {
    valueToEmit = [localValue.value]
  }
  emit('update:value', valueToEmit)
  emit('update:modelValue', valueToEmit)
  emit('input', valueToEmit)
  
  console.log(`[FormField] ${props.field.key} value changed to:`, valueToEmit)
}

const handleAlgorithmChange = (value) => {
  localValue.value = value
  handleInput()
}

const handleAlgorithmConfigsChange = (value) => {
  localValue.value = value
  handleInput()
}

const toggleSwitch = (event) => {
  if (!field.disabled) {
    localValue.value = !localValue.value
    handleInput()
  }
  event.stopPropagation()
}

const isTagSelected = (value) => {
  if (!localValue.value || !Array.isArray(localValue.value)) return false
  return localValue.value.includes(value)
}

const toggleTag = (value) => {
  if (!localValue.value) {
    localValue.value = []
  }
  if (!Array.isArray(localValue.value)) {
    localValue.value = []
  }
  
  const index = localValue.value.indexOf(value)
  if (index === -1) {
    localValue.value.push(value)
  } else {
    localValue.value.splice(index, 1)
  }
  handleInput()
}

const addArrayItem = () => {
  const newItem = props.field.arrayItemTemplate || { spl: null, digitalGain: null };
  localValue.value.push({ ...newItem });
  handleInput();
}

const removeArrayItem = (index) => {
  if (localValue.value.length > 1) {
    localValue.value.splice(index, 1);
    handleInput();
  }
}

const updateGainValue = (event, item, index) => {
  const value = Number(event.target.value);
  if (props.field.arrayItemTemplate && 'gain' in props.field.arrayItemTemplate) {
    localValue.value[index].gain = value;
  } else {
    localValue.value[index].digitalGain = value;
  }
  handleInput();
}

const handleFileUpload = (event) => {
  const file = event.target.files[0]
  if (file) {
    uploadedFile.value = file
    emit('file-upload', { fieldKey: props.field.key, file })
    emit('update:value', file)
    emit('update:modelValue', file)
  }
}

const removeFile = () => {
  uploadedFile.value = null
  emit('file-upload', { fieldKey: props.field.key, file: null })
  emit('update:value', '')
  emit('update:modelValue', '')
  const input = document.getElementById(fieldId)
  if (input) {
    input.value = ''
  }
}

const getFileName = (file) => {
  if (!file) return ''
  return file.name
}

const handleButtonAction = () => {
  emit('button-action', { field: props.field, value: localValue.value })
}

const handleSelectClick = () => {
  if (props.field.action && !props.field.text) {
    emit('button-action', { field: props.field, value: localValue.value })
  }
}
</script>

<style scoped>
.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

label {
  font-size: 14px;
  font-weight: 500;
  color: #334155;
  display: flex;
  align-items: center;
  gap: 4px;
}

.required-mark {
  color: #ef4444;
  font-size: 16px;
}

input, textarea, select {
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s ease;
}

select {
  max-height: 200px;
  overflow-y: auto;
  cursor: pointer;
}

select::-webkit-scrollbar {
  width: 6px;
}

select::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

select::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

select::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

input:focus, textarea:focus, select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.select-with-button {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  width: 100%;
  position: relative;
}

.select-with-button.no-button {
  flex-direction: row;
}

.select-with-button.no-button select {
  width: 100%;
}

.select-with-button select {
  width: 100%;
  border-radius: 6px;
}

.empty-select-guidance {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background-color: #fff1f2;
  border: 1px solid #fda4af;
  border-radius: 8px;
  color: #be123c;
  font-size: 14px;
  margin-bottom: 8px;
  animation: fadeIn 0.3s ease-out;
  box-shadow: 0 2px 4px rgba(225, 29, 72, 0.05);
}

.empty-select-guidance i {
  color: #e11d48;
  font-size: 16px;
}

.empty-select-guidance span {
  font-weight: 500;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-5px); }
  to { opacity: 1; transform: translateY(0); }
}

.select-with-button select.empty-select {
  border-color: #fda4af;
  background-color: #fff1f2;
  color: #991b1b;
}

.select-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 16px;
  background-color: #3b82f6;
  color: white;
  border: 1px solid #3b82f6;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  width: 100%;
}

.select-button:hover {
  background-color: #2563eb;
  border-color: #2563eb;
}

.select-button i {
  font-size: 12px;
}

textarea {
  resize: vertical;
  min-height: 80px;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.radio-item input {
  margin: 0;
}

.radio-item label {
  margin: 0;
  font-weight: 400;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.checkbox-item input {
  margin: 0;
}

.checkbox-item label {
  margin: 0;
  font-weight: 400;
}

.switch-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.info-field {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background-color: #e7f3ff;
  border: 1px solid #91d5ff;
  border-radius: 4px;
  color: #1890ff;
  font-size: 14px;
  grid-column: 1 / -1;
}

.info-field i {
  font-size: 16px;
}

.switch-input {
  display: none;
}

.switch-label {
  position: relative;
  display: inline-block;
  width: 50px;
  height: 24px;
  background-color: #e2e8f0;
  border-radius: 12px;
  transition: all 0.3s ease;
  cursor: pointer;
  flex-shrink: 0;
}

.switch-label::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  background-color: white;
  border-radius: 50%;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.switch-input:checked + .switch-label {
  background-color: #3b82f6;
}

.switch-input:checked + .switch-label::after {
  transform: translateX(26px);
}

.switch-text {
  font-size: 14px;
  color: #64748b;
}

.file-upload {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background-color: #f1f5f9;
  border-radius: 6px;
  font-size: 14px;
}

.file-name {
  flex: 1;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-file-btn {
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ef4444;
  transition: all 0.2s ease;
}

.remove-file-btn:hover {
  background-color: rgba(239, 68, 68, 0.1);
}

.api-meta-field {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.api-meta-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.api-protocol-wrapper, .api-environment-wrapper, .api-version-wrapper, .api-key-wrapper {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sub-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
  margin: 0;
}

.field-hint {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
}

.field-error {
  margin: 0;
  font-size: 12px;
  color: #ef4444;
}

.array-field {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.array-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background-color: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.array-item-content {
  flex: 1;
}

.array-item-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.array-item-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.remove-array-item-btn {
  background: none;
  border: none;
  padding: 8px;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ef4444;
  transition: all 0.2s ease;
}

.remove-array-item-btn:hover {
  background-color: rgba(239, 68, 68, 0.1);
}

.add-array-item-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background-color: #f1f5f9;
  border: 1px dashed #cbd5e1;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #64748b;
  transition: all 0.2s ease;
}

.add-array-item-btn:hover {
  background-color: #e2e8f0;
  border-color: #94a3b8;
}

.algorithm-multi-select,
.algorithm-configs-field {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  background-color: #fafafa;
}

.multi-select-tags-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background-color: #f8fafc;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
  color: #64748b;
}

.tag-item:hover {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.tag-item.selected {
  border-color: #3b82f6;
  background-color: #3b82f6;
  color: white;
}

.tag-check {
  font-size: 12px;
  font-weight: bold;
}
</style>
