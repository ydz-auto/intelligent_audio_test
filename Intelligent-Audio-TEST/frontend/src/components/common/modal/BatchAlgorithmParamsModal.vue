<template>
  <div class="batch-algorithm-params-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">{{ selectionMode === 'selected' ? '您勾选了' : '将对' }} {{ caseCount }} 个用例设置专属参数</p>
    </div>
    
    <div class="modal-body">
      <div class="form-group">
        <label>算法类型 <span class="required">*</span></label>
        <select v-model="selectedAlgorithmType" class="form-input custom-select" @change="onAlgorithmTypeChange">
          <option value="">请选择算法</option>
          <option v-for="opt in algorithmOptions" :key="opt.value" :value="opt.value">
            {{ opt.name }}
          </option>
        </select>
      </div>
      
      <div v-if="selectedAlgorithmType && algorithmFormSchema" class="params-section">
        <h4>参数配置</h4>
        <DynamicForm
          v-if="algorithmFormSchema.fields && algorithmFormSchema.fields.length > 0"
          ref="dynamicFormRef"
          :schema="algorithmFormSchema"
          :initial-values="algorithmParams"
          :show-group-header="true"
          :default-expanded-groups="['basic', 'model']"
          @field-change="onFieldChange"
        />
        <div v-else class="empty-state">
          <p>该算法暂无参数配置</p>
        </div>
      </div>

      <div class="scope-section">
        <label>轮次范围</label>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" :value="'all'" v-model="roundMode" />
            <span>所有轮次</span>
          </label>
          <label class="radio-label">
            <input type="radio" :value="'specific'" v-model="roundMode" />
            <span>指定轮次</span>
          </label>
        </div>
        <div class="round-checkboxs" v-if="roundMode === 'specific'">
          <label v-for="rn in availableRoundNumbers" :key="rn"
                 :class="{ checked: roundNumbers.includes(rn) }"
                 @click="toggleRoundNumber(rn)">
            第{{ rn }}轮
          </label>
        </div>
      </div>
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="!selectedAlgorithmType">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import DynamicForm from '../../algorithm/DynamicForm.vue'
import { useAlgorithmConfig } from '../../../composables/algorithm/useAlgorithmConfig'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  algorithmType?: string
  maxRoundNumbers?: number
  selectionMode?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { algorithmType: string; params: Record<string, any>; roundMode: string; roundNumbers: number[] }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置用例专属参数',
  caseCount: 0,
  algorithmType: '',
  maxRoundNumbers: 3,
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

const algorithmConfig = useAlgorithmConfig()
const getAlgorithmOptions = () => algorithmConfig.getAlgorithmOptions()
const getFormSchema = (type: string) => algorithmConfig.getFormSchema(type)

const algorithmOptions = ref<{ value: string; name: string }[]>([])
const selectedAlgorithmType = ref(props.algorithmType)
const algorithmFormSchema = ref<any>(null)
const algorithmParams = ref<Record<string, any>>({})
const dynamicFormRef = ref<any>(null)
const roundMode = ref<'all' | 'specific'>('all')
const roundNumbers = ref<number[]>([])

const availableRoundNumbers = computed(() => {
  return Array.from({ length: props.maxRoundNumbers }, (_, i) => i + 1)
})

function toggleRoundNumber(rn: number) {
  const idx = roundNumbers.value.indexOf(rn)
  if (idx >= 0) {
    roundNumbers.value.splice(idx, 1)
  } else {
    roundNumbers.value.push(rn)
  }
}

async function loadAlgorithmOptions() {
  try {
    const options = await getAlgorithmOptions()
    algorithmOptions.value = (options || []).map((opt: any) => ({
      value: opt.value,
      name: opt.name || opt.label || opt.value
    }))
  } catch (error) {
    console.error('加载算法选项失败:', error)
    algorithmOptions.value = []
  }
}

async function loadAlgorithmFormSchema(algorithmType: string) {
  if (!algorithmType) {
    algorithmFormSchema.value = null
    algorithmParams.value = {}
    return
  }

  try {
    const schema = await getFormSchema(algorithmType)
    algorithmFormSchema.value = schema
    
    const newParams: Record<string, any> = {}
    
    if (schema?.fields) {
      schema.fields.forEach((field: any) => {
        const fieldCode = field.fieldCode
        if (field.defaultValue !== undefined) {
          newParams[fieldCode] = field.defaultValue
        }
      })
    }
    
    algorithmParams.value = newParams
  } catch (error) {
    console.error('加载算法表单Schema失败:', error)
    algorithmFormSchema.value = null
  }
}

function onAlgorithmTypeChange() {
  loadAlgorithmFormSchema(selectedAlgorithmType.value)
}

function onFieldChange(field: string, value: any) {
  algorithmParams.value[field] = value
}

function handleConfirm() {
  if (!selectedAlgorithmType.value) {
    return
  }
  emit('confirm', {
    algorithmType: selectedAlgorithmType.value,
    params: algorithmParams.value,
    roundMode: roundMode.value,
    roundNumbers: roundNumbers.value
  })
}

function handleCancel() {
  emit('cancel')
}

loadAlgorithmOptions()
if (props.algorithmType) {
  loadAlgorithmFormSchema(props.algorithmType)
}
</script>

<style scoped>
.batch-algorithm-params-modal {
  padding: 20px;
}

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--foreground);
}

.modal-body {
  max-height: 400px;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
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
  border-radius: 4px;
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--secondary) 10%, transparent);
}

.params-section {
  margin-top: 20px;
}

.params-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: var(--foreground);
  font-weight: 500;
}

.empty-state {
  padding: 20px;
  text-align: center;
  color: var(--color-gray-400);
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
  border-radius: 4px;
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
.radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  cursor: pointer;
}
</style>
