<template>
  <div class="batch-spl-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">{{ selectionMode === 'selected' ? '您勾选了' : '将对' }} {{ caseCount }} 个用例设置声压级</p>
    </div>

    <div class="modal-body">
      <div class="form-group">
        <label>声压级 (dB) <span class="required">*</span></label>
        <input
          type="number"
          v-model.number="splValue"
          class="form-input"
          min="0"
          max="140"
          step="1"
          placeholder="请输入声压级，例如：65"
        />
        <p class="form-hint">建议值：65 dB</p>
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

      <div class="scope-section">
        <label>应用层级（可多选）</label>
        <div class="level-checkboxs">
          <label class="level-label">
            <input type="checkbox" value="audio" v-model="targets" />
            <span>目标人音频</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="caseBackgroundNoise" v-model="targets" />
            <span>case级背景噪声</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="segmentBackgroundNoise" v-model="targets" />
            <span>segment级背景噪声</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="interferer" v-model="targets" />
            <span>干扰人</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="voiceprint" v-model="targets" />
            <span>声纹</span>
          </label>
        </div>
      </div>
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="!isValid">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  initialValue?: number
  maxRoundNumbers?: number
  selectionMode?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { value: number; targets: string[]; roundMode: string; roundNumbers: number[] }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置声压级',
  caseCount: 0,
  initialValue: 94,
  maxRoundNumbers: 3,
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

const splValue = ref(props.initialValue)
const roundMode = ref<'all' | 'specific'>('all')
const roundNumbers = ref<number[]>([])
const targets = ref<string[]>(['audio'])

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

const isValid = computed(() => {
  return splValue.value >= 0 && splValue.value <= 140
})

function handleConfirm() {
  if (!isValid.value) {
    return
  }
  emit('confirm', {
    value: splValue.value,
    targets: targets.value,
    roundMode: roundMode.value,
    roundNumbers: roundNumbers.value
  })
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.batch-spl-modal {
  padding: 20px;
}

.modal-header {
  margin-bottom: 20px;
}

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #333;
}

.case-count {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.modal-body {
  padding: 10px 0;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
}

.required {
  color: #dc3545;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.form-hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #999;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.btn {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
}

.btn-secondary {
  background: #f5f5f5;
  color: #333;
}

.btn-secondary:hover {
  background: #e8e8e8;
}

.btn-primary {
  background: #1677ff;
  color: #fff;
}

.btn-primary:hover {
  background: #4096ff;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.scope-section {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.scope-section > label {
  display: block;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 14px;
  color: #333;
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
.round-checkboxs {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding-left: 24px;
}
.round-checkboxs label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 12px;
  border: 1px solid #d1d5db;
  border-radius: 20px;
  background: #fff;
}
.round-checkboxs label.checked {
  border-color: #1677ff;
  background: #e6f4ff;
  color: #1677ff;
}
.level-checkboxs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.level-checkboxs label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}
.level-hint {
  font-size: 11px;
  color: #999;
  margin-left: 20px;
}
</style>
