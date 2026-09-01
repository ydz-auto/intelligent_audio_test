<template>
  <div class="batch-dimension-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">将为 {{ caseCount }} 个用例设置评价维度</p>
    </div>

    <div class="modal-body">
      <DimensionConfigPanel
        v-model="dimensionConfig"
        v-model:searchQuery="searchQuery"
        :available-dimensions="searchedDimensions"
        :loading="loading"
        :error="loadError"
        :max-round-numbers="maxRoundNumbers"
      />
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import DimensionConfigPanel from '../DimensionConfigPanel.vue'
import { useDimensions } from '../../../composables/useDimensions'
import type { DimensionConfigData } from '../DimensionConfigPanel.vue'

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
  testType?: string
  maxRoundNumbers?: number
  selectionMode?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: {
    dimensions: Array<{ id: string; name: string; weight: number; threshold: number }>;
    testType: string;
    roundMode: string;
    roundNumbers: number[];
    roundDimensions?: Record<number, Array<{ id: string; name: string; weight: number; threshold: number }>>;
    multiDimensions?: Array<{ id: string; name: string; weight: number; threshold: number }>;
  }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置评价维度',
  caseCount: 0,
  algorithmType: '',
  testType: 'e2e',
  maxRoundNumbers: 3,
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

const { fetchAllDimensions, fetchDimensionsByAlgorithmType, getDimensionsByAlgorithmType } = useDimensions()

const availableDimensions = ref<Dimension[]>([])
const loading = ref(false)
const loadError = ref('')
const searchQuery = ref('')

// DimensionConfigPanel 的数据模型
const dimensionConfig = ref<DimensionConfigData>({
  dimensions: [],
  roundMode: 'all',
  roundNumbers: [],
  roundDimensions: {},
  multiDimensions: []
})

// 按算法类型过滤
const filteredByAlgorithm = computed(() => {
  if (!props.algorithmType) {
    return availableDimensions.value
  }
  const associatedIds = new Set(availableDimensions.value.map(d => d.id))
  const dimsByAlgo = getDimensionsByAlgorithmType(props.algorithmType)
  const filtered = dimsByAlgo.filter((dim: any) => associatedIds.has(dim.id))
  return filtered.length > 0 ? filtered : availableDimensions.value
})

// 按搜索关键字过滤
const searchedDimensions = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) {
    return filteredByAlgorithm.value
  }
  return filteredByAlgorithm.value.filter(dim =>
    dim.name.toLowerCase().includes(query)
  )
})

async function loadDimensions() {
  loading.value = true
  loadError.value = ''
  try {
    let dims: any[]
    if (props.algorithmType) {
      dims = await fetchDimensionsByAlgorithmType(props.algorithmType)
    } else {
      dims = await fetchAllDimensions({ forceRefresh: true })
    }
    availableDimensions.value = dims.map((d: any) => ({
      id: d.id?.toString() || d.dimension_id?.toString() || '',
      name: d.name || d.dimension_name || '',
      description: d.description
    }))
  } catch (error) {
    console.error('加载评价维度失败:', error)
    loadError.value = '加载评价维度失败'
    availableDimensions.value = []
  } finally {
    loading.value = false
  }
}

function handleConfirm() {
  const cfg = dimensionConfig.value
  const multiDimensions = (cfg.multiDimensions || []).map(dim => ({
    id: String(dim.id),
    name: dim.name,
    weight: dim.weight ?? 50,
    threshold: dim.threshold ?? 60
  }))

  if (cfg.roundMode === 'per_round') {
    const roundDimensions: Record<number, Array<{ id: string; name: string; weight: number; threshold: number }>> = {}
    for (const [rn, dims] of Object.entries(cfg.roundDimensions || {})) {
      const roundNum = Number(rn)
      roundDimensions[roundNum] = (dims || []).map(dim => ({
        id: String(dim.id),
        name: dim.name,
        weight: dim.weight ?? 50,
        threshold: dim.threshold ?? 60
      }))
    }
    emit('confirm', {
      dimensions: [],
      testType: props.testType,
      roundMode: 'per_round',
      roundNumbers: [],
      roundDimensions,
      multiDimensions
    })
  } else {
    const dimensions = (cfg.dimensions || []).map(dim => ({
      id: String(dim.id),
      name: dim.name,
      weight: dim.weight ?? 50,
      threshold: dim.threshold ?? 60
    }))
    emit('confirm', {
      dimensions,
      testType: props.testType,
      roundMode: cfg.roundMode,
      roundNumbers: cfg.roundNumbers || [],
      multiDimensions
    })
  }
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
  max-height: 560px;
  overflow-y: auto;
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
</style>
