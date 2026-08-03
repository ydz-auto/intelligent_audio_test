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

    <OutputFieldsEditor
      v-else-if="field.type === 'outputFields'"
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
import AlgorithmParamsConfig from '../../algorithm/AlgorithmParamsConfig.vue'
import RequiredInputsEditor from './RequiredInputsEditor.vue'
import OutputFieldsEditor from './OutputFieldsEditor.vue'
import APISettingsEditor from './APISettingsEditor.vue'
import RuleEditor from './RuleEditor.vue'
import { useFormField } from './FormField'

const props = defineProps({
  field: {type: Object, required: true},
  value: {type: [String, Number, Boolean, Array, Object], default: ''},
  error: {type: String, default: ''},
  modelValue: {type: [String, Number, Boolean, Array, Object], default: ''}
})

const emit = defineEmits(['update:value', 'update:modelValue', 'input', 'file-upload', 'button-action'])

const {
  fieldId,
  fieldKey,
  uploadedFile,
  isEmptySelect,
  localValue,
  algorithmConfigsValue,
  supportedAlgorithmsValue,
  algorithmOptions,
  handleInput,
  handleAlgorithmChange,
  handleAlgorithmConfigsChange,
  toggleSwitch,
  isTagSelected,
  toggleTag,
  addArrayItem,
  removeArrayItem,
  updateGainValue,
  handleFileUpload,
  removeFile,
  getFileName,
  handleButtonAction,
  handleSelectClick
} = useFormField(props, emit)
</script>

<style scoped>
@import './FormField.css';
</style>
