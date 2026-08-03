<template>
  <div class="array-field-container" :data-field-key="field.key">
    <label v-if="field.label" class="field-label">{{ field.label }}</label>
    <div class="array-field">
      <div 
        v-for="(item, index) in localValue" 
        :key="index"
        class="array-item"
        :class="{ 'has-error': getFinalLevelDbfs(item) > -5 }"
      >
        <div class="array-item-content">
          <template v-if="field.arrayItemType === 'gainSpl'">
            <div class="gain-spl-row">
              <div class="gain-offset-wrapper">
                <label :for="`${fieldId}-${index}-gainOffset`" class="sub-label">增益偏移 (dB)</label>
                <input
                  :id="`${fieldId}-${index}-gainOffset`"
                  type="number"
                  :value="localValue[index]?.gainOffset"
                  @input="updateGainOffset($event, index)"
                  placeholder="dB"
                  :min="-12"
                  :max="25"
                  step="0.1"
                />
                <span v-if="getFinalLevelDbfs(item) > -5" class="warning-text">最大 +25dB</span>
              </div>
              <div class="base-level-wrapper">
                <label :for="`${fieldId}-${index}-baseLevel`" class="sub-label">基础电平</label>
                <input
                  :id="`${fieldId}-${index}-baseLevel`"
                  type="text"
                  value="-30 dBFS"
                  readonly
                  class="readonly-field"
                />
              </div>
              <div class="final-level-wrapper">
                <label :for="`${fieldId}-${index}-finalLevel`" class="sub-label">最终电平</label>
                <input
                  :id="`${fieldId}-${index}-finalLevel`"
                  type="text"
                  :value="getFinalLevel(item)"
                  readonly
                  class="readonly-field"
                  :class="{ 'error-field': getFinalLevelDbfs(item) > -5 }"
                />
              </div>
              <div class="spl-input-wrapper">
                <label :for="`${fieldId}-${index}-spl`" class="sub-label">实测SPL (dB)</label>
                <input
                  :id="`${fieldId}-${index}-spl`"
                  type="number"
                  :value="localValue[index]?.spl"
                  @input="updateSPLValue($event, index)"
                  placeholder="SPL (dB)"
                  :min="0"
                  :max="150"
                  step="0.1"
                />
              </div>
              <button
                type="button"
                class="test-spl-btn"
                :class="{ 'stop-btn': isPlaying(index) }"
                @click="isPlaying(index) ? stopSPL(index) : testSPL(index)"
                :disabled="!canTestSPL(index) && !isPlaying(index)"
              >
                <i :class="isPlaying(index) ? 'fas fa-stop' : 'fas fa-volume-up'"></i>
                {{ isPlaying(index) ? '停止' : '测试' }}
              </button>
            </div>
          </template>
          
          <template v-else-if="field.arrayItemType === 'apiEndpoint'">
            <div class="api-endpoint-row">
              <div class="api-url-wrapper">
                <label :for="`${fieldId}-${index}-url`" class="sub-label">端点URL</label>
                <input
                  :id="`${fieldId}-${index}-url`"
                  type="text"
                  :value="localValue[index].url || localValue[index].endpoint || ''"
                  @input="updateAPIUrl($event, index)"
                  placeholder="请输入API端点URL"
                  class="full-width"
                />
              </div>
              <div class="api-name-wrapper">
                <label :for="`${fieldId}-${index}-name`" class="sub-label">端点名称 (可选)</label>
                <input
                  :id="`${fieldId}-${index}-name`"
                  type="text"
                  v-model="localValue[index].name"
                  placeholder="请输入端点名称 (选填)"
                  @input="handleInput"
                />
              </div>
              <div class="api-priority-wrapper">
                <label :for="`${fieldId}-${index}-priority`" class="sub-label">优先级</label>
                <input
                  :id="`${fieldId}-${index}-priority`"
                  type="number"
                  v-model="localValue[index].priority"
                  placeholder="优先级 (1-10)"
                  :min="1"
                  :max="10"
                  step="1"
                  @input="handleInput"
                />
              </div>
            </div>
            <div class="api-endpoint-advanced">
              <div class="api-max-process-wrapper">
                <label :for="`${fieldId}-${index}-max-process`" class="sub-label">最大进程数</label>
                <input
                  :id="`${fieldId}-${index}-max-process`"
                  type="number"
                  v-model="localValue[index].maxProcess"
                  placeholder="最大进程数 (1-100)"
                  :min="1"
                  :max="100"
                  step="1"
                  @input="handleInput"
                />
              </div>
              <div class="api-max-timeout-wrapper">
                <label :for="`${fieldId}-${index}-max-timeout`" class="sub-label">最大超时时间</label>
                <input
                  :id="`${fieldId}-${index}-max-timeout`"
                  type="number"
                  v-model="localValue[index].maxTimeout"
                  placeholder="超时时间 (秒)"
                  :min="1"
                  :max="300"
                  step="1"
                  @input="handleInput"
                />
              </div>
              <div class="api-max-duration-wrapper">
                <label :for="`${fieldId}-${index}-max-duration`" class="sub-label">最大音频时长</label>
                <input
                  :id="`${fieldId}-${index}-max-duration`"
                  type="number"
                  v-model="localValue[index].maxAudioDuration"
                  placeholder="音频时长 (秒)"
                  :min="1"
                  :max="3600"
                  step="1"
                  @input="handleInput"
                />
              </div>
            </div>
          </template>
        </div>
        <button 
          type="button" 
          class="remove-array-item-btn"
          @click="removeArrayItem(index)"
          :disabled="localValue.length <= 1"
        >
          <i class="fas fa-trash"></i>
        </button>
      </div>
    </div>
    <button 
      type="button" 
      class="add-array-item-btn"
      @click="addArrayItem"
    >
      <i class="fas fa-plus"></i>
      {{ field.arrayItemType === 'apiEndpoint' ? '添加API端点' : '添加增益点' }}
    </button>
    
    <p v-if="error" class="field-error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { useArrayField, type Field } from './ArrayField'

const props = defineProps<{
  field: Field;
  value: any[];
  modelValue: any[];
  error: string;
}>();

const emit = defineEmits<{
  (e: 'update:value', value: any[]): void;
  (e: 'update:modelValue', value: any[]): void;
  (e: 'input', value: any[]): void;
  (e: 'test-spl', data: { index: number; gainValue: number; splValue: number; gainOffset: number }): void;
  (e: 'stop-spl', data: { index: number }): void;
  (e: 'test-spl-complete', index: number): void;
}>();

const {
  fieldId,
  localValue,
  handleInput,
  addArrayItem,
  removeArrayItem,
  updateAPIUrl,
  updateSPLValue,
  updateGainOffset,
  getFinalLevelDbfs,
  getFinalLevel,
  canTestSPL,
  testSPL,
  stopSPL,
  isPlaying
} = useArrayField(props, emit)
</script>

<style scoped>
@import './ArrayField.css';
</style>
