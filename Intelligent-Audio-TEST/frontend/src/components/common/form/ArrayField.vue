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
import { ref, watch } from 'vue'

interface Field {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  [key: string]: any;
}

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

const fieldId = `field-${props.field.key}`

// 记录当前正在播放的索引
const playingIndex = ref<number | null>(null);

const getInitialValue = () => {
  if (props.modelValue !== undefined && Array.isArray(props.modelValue)) {
    return [...props.modelValue];
  }
  if (props.value !== undefined && Array.isArray(props.value)) {
    return [...props.value];
  }
  
  // 优先使用字段模板
  if (props.field && props.field.arrayItemTemplate) {
    return [{ ...props.field.arrayItemTemplate }];
  }
  
  // 根据类型返回默认模板
  if (props.field?.arrayItemType === 'apiEndpoint') {
    return [{
      endpoint: '',
      name: '',
      priority: 1,
      maxProcess: 5,
      maxTimeout: 30,
      maxAudioDuration: 60
    }];
  }
  
  // 默认返回一个最基本的模板项
  return [{ digital_gain: null, spl: null }];
};

const localValue = ref(getInitialValue())

watch(() => props.modelValue, (newVal) => {
  if (Array.isArray(newVal)) {
    localValue.value = [...newVal]
  } else if (newVal === undefined && localValue.value.length === 0) {
    // 防止 modelValue 变为 undefined 时清空数组
    const template = props.field?.arrayItemTemplate || { digital_gain: null, spl: null };
    if (localValue.value.length === 0) {
      localValue.value = [{ ...template }];
    }
  }
}, { deep: true })

watch(() => props.value, (newVal) => {
  if (Array.isArray(newVal)) {
    localValue.value = [...newVal]
  } else if (newVal === undefined && localValue.value.length === 0) {
    // 防止 value 变为 undefined 时清空数组
    const template = props.field?.arrayItemTemplate || { digital_gain: null, spl: null };
    if (localValue.value.length === 0) {
      localValue.value = [{ ...template }];
    }
  }
}, { deep: true })

const handleInput = () => {
  emit('update:value', [...localValue.value])
  emit('update:modelValue', [...localValue.value])
  emit('input', [...localValue.value])
}

const addArrayItem = () => {
  let template = props.field.arrayItemTemplate || { digital_gain: null, spl: null };
  
  if (props.field.arrayItemType === 'apiEndpoint') {
    const defaultMaxProcess = 5;
    const defaultMaxTimeout = 30;
    const defaultMaxAudioDuration = 60;
    
    template = {...template, maxProcess: defaultMaxProcess, maxTimeout: defaultMaxTimeout, maxAudioDuration: defaultMaxAudioDuration};
  }
  
  localValue.value.push({ ...template });
  handleInput();
};

const removeArrayItem = (index: number) => {
  if (localValue.value.length > 1) {
    localValue.value.splice(index, 1)
    handleInput()
  }
}

const updateAPIUrl = (event: Event, index: number) => {
  const value = (event.target as HTMLInputElement).value;
  const newItem = { ...localValue.value[index] };
  newItem.endpoint = value;
  newItem.url = value;
  localValue.value.splice(index, 1, newItem);
  handleInput();
}

const updateSPLValue = (event: Event, index: number) => {
  const value = Number((event.target as HTMLInputElement).value);
  const newItem = { ...localValue.value[index] };
  newItem.spl = value;
  localValue.value.splice(index, 1, newItem);
  handleInput();
}

const updateGainOffset = (event: Event, index: number) => {
  const rawValue = (event.target as HTMLInputElement).value;
  const newItem = { ...localValue.value[index] };
  
  if (rawValue === '' || rawValue === '-') {
    newItem.gainOffset = null;
  } else {
    const value = Number(rawValue);
    newItem.gainOffset = isNaN(value) ? null : value;
  }
  
  localValue.value.splice(index, 1, newItem);
  handleInput();
}

const BASE_LEVEL_DBFS = -30;
const MAX_FINAL_LEVEL_DBFS = -5;
const MAX_GAIN_OFFSET = MAX_FINAL_LEVEL_DBFS - BASE_LEVEL_DBFS;

const getGainOffset = (gainValue: number | null): string => {
  if (gainValue === null || gainValue === undefined) {
    return '0.00';
  }
  const offset = (gainValue - 50) * 0.24;
  return offset.toFixed(2);
}

const getFinalLevelDbfs = (item: any): number => {
  if (!item) {
    return BASE_LEVEL_DBFS;
  }
  let gainOffsetDb = 0;
  if (item.gainOffset !== undefined && item.gainOffset !== null) {
    const val = Number(item.gainOffset);
    if (!isNaN(val)) {
      gainOffsetDb = val;
    }
  } else if (item.digital_gain !== undefined && item.digital_gain !== null && item.digital_gain !== '') {
    const val = Number(item.digital_gain);
    if (!isNaN(val)) {
      gainOffsetDb = (val - 50) * 0.24;
    }
  } else if (item.gain !== undefined && item.gain !== null && item.gain !== '') {
    const val = Number(item.gain);
    if (!isNaN(val)) {
      gainOffsetDb = (val - 50) * 0.24;
    }
  }
  return BASE_LEVEL_DBFS + gainOffsetDb;
}

const getFinalLevel = (item: any): string => {
  const finalLevel = getFinalLevelDbfs(item);
  return `${finalLevel.toFixed(2)} dBFS`;
}

const canTestSPL = (index: number): boolean => {
  const item = localValue.value[index];
  if (!item) return false;
  
  // 检查 gainOffset 是否有值（包括 0）
  const hasGainOffset = item.gainOffset !== null && item.gainOffset !== undefined;
  if (hasGainOffset) return true;
  
  // 检查 digital_gain 或 gain 是否有值（兼容旧数据）
  const hasDigitalGain = (item.digital_gain !== null && item.digital_gain !== undefined && item.digital_gain !== '') ||
                         (item.gain !== null && item.gain !== undefined && item.gain !== '');
  return hasDigitalGain;
}

const testSPL = (index: number) => {
  // 如果当前有正在播放的其他测试音，先停止它
  if (playingIndex.value !== null && playingIndex.value !== index) {
    console.log(`[testSPL] 正在播放索引 ${playingIndex.value}，先停止它`);
    stopSPL(playingIndex.value);
  }

  let item = localValue.value[index];
  
  // 如果本地值不存在，尝试从 DOM 读取
  if (!item) {
    const arrayField = document.querySelector('.array-field');
    if (arrayField) {
      const arrayItems = arrayField.querySelectorAll('.array-item');
      if (arrayItems[index]) {
        const gainOffsetInput = arrayItems[index].querySelector('.gain-offset-wrapper input') as HTMLInputElement;
        const splInput = arrayItems[index].querySelector('.spl-input-wrapper input') as HTMLInputElement;
        
        if (gainOffsetInput) {
          item = {
            gainOffset: gainOffsetInput.value !== '' ? Number(gainOffsetInput.value) : null,
            spl: splInput && splInput.value !== '' ? Number(splInput.value) : null
          };
          console.log(`[testSPL] 从DOM读取数据:`, item);
        }
      }
    }
  }
  
  if (!item) {
    console.warn(`[testSPL] 未找到索引 ${index} 的校准点数据`);
    return;
  }
  
  // 确定 gainOffsetValue 和 gainValue
  let gainOffsetValue: number | null = null;
  let gainValue: number | null = null;

  if (item.gainOffset !== undefined && item.gainOffset !== null) {
    gainOffsetValue = Number(item.gainOffset);
    if (!isNaN(gainOffsetValue)) {
      gainValue = 50 + gainOffsetValue / 0.24;
    }
  } else {
    // 尝试从 digital_gain 或 gain 获取
    const digitalGain = item.digital_gain ?? item.gain;
    if (digitalGain !== undefined && digitalGain !== null && digitalGain !== '') {
      gainValue = Number(digitalGain);
      if (!isNaN(gainValue)) {
        gainOffsetValue = (gainValue - 50) * 0.24;
      }
    }
  }
    
  if (gainOffsetValue === null || isNaN(gainOffsetValue)) {
    console.warn(`[testSPL] 增益偏移无效:`, item.gainOffset);
    return;
  }
  
  const splValue = (item.spl !== undefined && item.spl !== null && item.spl !== '') 
    ? Number(item.spl) 
    : null;
    
  console.log(`[testSPL] 点击测试声压按钮: index=${index}, item=`, item, 'gainValue=', gainValue, 'gainOffset=', gainOffsetValue, 'splValue=', splValue);
  
  playingIndex.value = index;
  console.log(`[testSPL] 发送 test-spl 事件`);
  emit('test-spl', { index, gainValue: gainValue as number, splValue: splValue as any, gainOffset: gainOffsetValue });
}

const stopSPL = (index: number) => {
  console.log(`[stopSPL] 停止测试声压: index=${index}`);
  playingIndex.value = null;
  emit('stop-spl', { index });
}

const isPlaying = (index: number): boolean => {
  return playingIndex.value === index;
}


</script>

<style scoped>
.array-field-container {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 8px;
  border: 1px dashed #e2e8f0;
}

.field-label {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}

.array-field {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.array-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  background-color: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  position: relative;
}

.array-item-content {
  flex: 1;
}

.gain-spl-row {
  display: grid;
  grid-template-columns: 80px 100px 110px 100px auto;
  gap: 10px;
  align-items: end;
}

.gain-offset-wrapper,
.base-level-wrapper,
.final-level-wrapper {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.readonly-field {
  background-color: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  color: #64748b;
  cursor: default;
}

.readonly-field:focus {
  outline: none;
  border-color: #cbd5e1;
}

.readonly-field.error-field {
  border-color: #ef4444;
  background-color: rgba(239, 68, 68, 0.05);
  color: #ef4444;
  font-weight: 500;
}

.warning-text {
  font-size: 10px;
  color: #f59e0b;
  margin-top: 2px;
}

.has-error {
  border-color: #f59e0b !important;
  background-color: rgba(245, 158, 11, 0.05) !important;
}

.api-endpoint-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 12px;
}

.api-endpoint-advanced {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  padding: 12px;
  background-color: #f1f5f9;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.api-priority-wrapper, .api-name-wrapper, .api-url-wrapper,
.api-max-process-wrapper, .api-max-timeout-wrapper, .api-max-duration-wrapper,
.gain-input-wrapper, .spl-input-wrapper {
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
  margin-top: 8px;
}

.remove-array-item-btn:hover:not(:disabled) {
  background-color: rgba(239, 68, 68, 0.1);
}

.remove-array-item-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.add-array-item-btn {
  background: none;
  border: 1px dashed #94a3b8;
  padding: 10px 16px;
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
  transition: all 0.2s ease;
  font-size: 14px;
}

.add-array-item-btn:hover {
  background-color: rgba(148, 163, 184, 0.1);
  border-color: #64748b;
  color: #334155;
}

.test-spl-btn {
  background-color: var(--primary-color, #ff6a00);
  color: white;
  border: 2px solid transparent;
  padding: 6px 10px;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.test-spl-btn:hover:not(:disabled) {
  box-shadow: 0 2px 8px rgba(255, 106, 0, 0.3);
  border: 2px solid var(--primary-color, #ff6a00);
}

.test-spl-btn:disabled {
  background-color: #e9ecef;
  color: #adb5bd;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.test-spl-btn.stop-btn {
  background-color: #dc2626;
}

.test-spl-btn.stop-btn:hover:not(:disabled) {
  box-shadow: 0 2px 8px rgba(220, 38, 38, 0.3);
  border: 2px solid #dc2626;
}

.field-error {
  margin: 8px 0 0 0;
  font-size: 12px;
  color: #ef4444;
}

@media (max-width: 768px) {
  .gain-spl-row {
    grid-template-columns: 1fr;
  }
  
  .api-endpoint-row {
    grid-template-columns: 1fr;
  }
  
  .api-endpoint-advanced {
    grid-template-columns: 1fr;
  }
}
</style>
