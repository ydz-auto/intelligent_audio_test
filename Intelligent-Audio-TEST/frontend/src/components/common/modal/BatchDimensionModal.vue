<template>
  <div class="batch-dimension-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">将为 {{ caseCount }} 个用例设置评价维度</p>
    </div>
    
    <div class="modal-body">
      <div class="form-group">
        <label>测试类型</label>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" v-model="testType" value="api" />
            <span>API测试</span>
          </label>
          <label class="radio-label">
            <input type="radio" v-model="testType" value="e2e" />
            <span>E2E测试</span>
          </label>
        </div>
      </div>
      
      <div class="form-group">
        <label>评价维度</label>
        <div class="dimension-cloud-container">
          <div 
            v-for="dim in filteredAvailableDimensions" 
            :key="dim.id"
            class="dimension-tag"
            :class="{ 'selected': isDimensionSelected(dim) }"
            @click="toggleDimension(dim)"
          >
            {{ dim.name }}
          </div>
        </div>
        <p v-if="filteredAvailableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
      </div>
      
      <div v-if="selectedDimensions.length > 0" class="form-group">
        <label>维度权重和阈值配置</label>
        <div class="dimension-config-list">
          <div v-for="(dim, index) in selectedDimensions" :key="dim.id" class="dimension-config-item">
            <div class="dimension-config-header">
              <span class="dimension-config-name">{{ dim.name }}</span>
              <button type="button" class="btn btn-xs btn-danger" @click="removeDimension(index)">
                <i class="fas fa-times"></i>
              </button>
            </div>
            <div class="dimension-config-fields">
              <div class="form-row">
                <div class="form-group">
                  <label>权重（0-100）</label>
                  <input type="number" v-model.number="dimConfigs[dim.id].weight" class="form-input" min="0" max="100" />
                </div>
                <div class="form-group">
                  <label>阈值（0-100）</label>
                  <input type="number" v-model.number="dimConfigs[dim.id].threshold" class="form-input" min="0" max="100" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="selectedDimensions.length === 0">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useDimensions } from '../../../composables/useDimensions'

interface Dimension {
  id: string
  name: string
  description?: string
}

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  algorithmType?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { dimensions: Array<{id: string; name: string; weight: number; threshold: number}>; testType: string }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置评价维度',
  caseCount: 0,
  algorithmType: ''
})

const emit = defineEmits<Emits>()

const { fetchAllDimensions, fetchDimensionsByAlgorithmType, getDimensionsByAlgorithmType } = useDimensions()

const availableDimensions = ref<Dimension[]>([])
const selectedDimensions = ref<Dimension[]>([])
const dimConfigs = ref<Record<string, { weight: number; threshold: number }>>({})
const testType = ref('api')

const filteredAvailableDimensions = computed(() => {
  if (!props.algorithmType) {
    return availableDimensions.value
  }
  const associatedIds = new Set(availableDimensions.value.map(d => d.id))
  const dimsByAlgo = getDimensionsByAlgorithmType(props.algorithmType)
  const filtered = dimsByAlgo.filter((dim: any) => associatedIds.has(dim.id))
  return filtered.length > 0 ? filtered : availableDimensions.value
})

const isDimensionSelected = (dim: Dimension) => {
  return selectedDimensions.value.some(d => d.id === dim.id)
}

const toggleDimension = (dim: Dimension) => {
  if (isDimensionSelected(dim)) {
    selectedDimensions.value = selectedDimensions.value.filter(d => d.id !== dim.id)
    delete dimConfigs.value[dim.id]
  } else {
    selectedDimensions.value.push(dim)
    dimConfigs.value[dim.id] = { weight: 50, threshold: 60 }
  }
}

const removeDimension = (index: number) => {
  const dim = selectedDimensions.value[index]
  delete dimConfigs.value[dim.id]
  selectedDimensions.value.splice(index, 1)
}

async function loadDimensions() {
  try {
    if (props.algorithmType) {
      const dims = await fetchDimensionsByAlgorithmType(props.algorithmType)
      availableDimensions.value = dims.map((d: any) => ({
        id: d.id?.toString() || d.dimension_id?.toString() || '',
        name: d.name || d.dimension_name || '',
        description: d.description
      }))
    } else {
      const dims = await fetchAllDimensions({ forceRefresh: true })
      availableDimensions.value = dims.map((d: any) => ({
        id: d.id?.toString() || d.dimension_id?.toString() || '',
        name: d.name || d.dimension_name || '',
        description: d.description
      }))
    }
  } catch (error) {
    console.error('加载评价维度失败:', error)
    availableDimensions.value = []
  }
}

function handleConfirm() {
  if (selectedDimensions.value.length === 0) {
    return
  }

  const dimensions = selectedDimensions.value.map(dim => ({
    id: dim.id,
    name: dim.name,
    weight: dimConfigs.value[dim.id]?.weight ?? 50,
    threshold: dimConfigs.value[dim.id]?.threshold ?? 60
  }))

  emit('confirm', { dimensions, testType: testType.value })
}

function handleCancel() {
  emit('cancel')
}

onMounted(async () => {
  await loadDimensions()
})
</script>

<style scoped>
.batch-dimension-modal {
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
  max-height: 400px;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 16px;
}

.form-group > label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
}

.radio-group {
  display: flex;
  gap: 16px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.radio-label input[type="radio"] {
  width: 16px;
  height: 16px;
}

.dimension-cloud-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 16px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  max-height: 150px;
  overflow-y: auto;
}

.dimension-tag {
  display: inline-block;
  padding: 8px 16px;
  background-color: #e3f2fd;
  color: #1976d2;
  border: 1px solid #bbdefb;
  border-radius: 20px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  user-select: none;
}

.dimension-tag:hover {
  background-color: #bbdefb;
  border-color: #1976d2;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.2);
}

.dimension-tag.selected {
  background-color: #1976d2;
  color: white;
  border-color: #1976d2;
}

.dimension-tag.selected:hover {
  background-color: #1565c0;
  border-color: #1565c0;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.3);
}

.empty-hint {
  margin: 8px 0;
  color: #999;
  font-size: 13px;
}

.dimension-config-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.dimension-config-item {
  padding: 16px;
  background-color: white;
  border: 1px solid #dee2e6;
  border-radius: 4px;
}

.dimension-config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e9ecef;
}

.dimension-config-name {
  font-weight: 600;
  color: #495057;
  font-size: 14px;
}

.dimension-config-fields {
  margin-top: 12px;
}

.dimension-config-fields .form-row {
  gap: 16px;
}

.dimension-config-fields .form-group {
  min-width: 150px;
  flex: 1;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .form-group {
  flex: 1;
  margin-bottom: 0;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
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
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background-color: #5a6268;
}

.btn-primary {
  background-color: #007bff;
  color: white;
}

.btn-primary:hover {
  background-color: #0056b3;
}

.btn-primary:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
}

.btn-xs {
  padding: 6px 12px;
  font-size: 12px;
}

.btn-danger {
  background-color: #dc3545;
  color: white;
}

.btn-danger:hover {
  background-color: #c82333;
}
</style>
