<template>
  <div class="batch-refresh-reference-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">{{ selectionMode === 'selected' ? '您勾选了' : '将对' }} {{ caseCount }} 个用例刷新参考参数吗？</p>
    </div>

    <div class="modal-body">
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
      <button type="button" class="btn btn-primary" @click="handleConfirm">确定</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  maxRoundNumbers?: number
  selectionMode?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { roundMode: string; roundNumbers: number[] }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '用例参考更新',
  caseCount: 0,
  maxRoundNumbers: 3,
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

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

function handleConfirm() {
  emit('confirm', {
    roundMode: roundMode.value,
    roundNumbers: roundNumbers.value
  })
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.batch-refresh-reference-modal {
  padding: 20px;
}

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--foreground);
}

.modal-body {
  padding: 10px 0;
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
