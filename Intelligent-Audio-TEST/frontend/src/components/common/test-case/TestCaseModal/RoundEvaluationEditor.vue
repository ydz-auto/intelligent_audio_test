<template>
  <div class="round-evaluation-editor">
    <!-- 过滤提示 -->
    <div v-if="algorithmType && filteredDimensions.length > 0" class="eval-filter-hint">
      <i class="fas fa-filter"></i>
      已根据算法类型「{{ algorithmType }}」过滤可用维度
    </div>

    <!-- 维度 chips 选择区 -->
    <div class="eval-chip-grid">
      <div
        v-for="dim in filteredDimensions"
        :key="dim.id"
        class="eval-chip"
        :class="{ active: isDimSelected(dim) }"
        @click="toggleDim(dim)"
      >
        <i :class="isDimSelected(dim) ? 'fas fa-check' : 'fas fa-plus'"></i>
        {{ dim.name }}
      </div>
    </div>

    <div v-if="filteredDimensions.length === 0" class="eval-empty">
      <i class="fas fa-info-circle"></i>
      暂无可用维度{{ algorithmType ? '（当前算法类型无关联维度）' : '' }}
    </div>

    <!-- 已选维度参数卡片 -->
    <div v-if="localDimensions.length > 0" class="eval-selected-section">
      <div class="eval-sub-title">
        <i class="fas fa-cog"></i> 已选维度参数
      </div>
      <div class="eval-cards-row">
        <div
          v-for="(dim, idx) in localDimensions"
          :key="dim.id || dim.name"
          class="eval-dim-card"
        >
          <!-- 卡片头 -->
          <div class="eval-card-header">
            <div class="eval-card-title-group">
              <span class="eval-card-title">{{ dim.name }}</span>
              <!-- INT-1868：LLM Judge 只读徽章（由维度自身 task_type_code 派生，无模型 / Prompt 配置） -->
              <span v-if="isLlmJudge(dim)" class="eval-llm-badge">
                <i class="fas fa-robot"></i> LLM Judge
              </span>
            </div>
            <button
              type="button"
              class="eval-card-remove-btn"
              title="移除"
              @click="removeDim(idx)"
            >
              <i class="fas fa-times"></i>
            </button>
          </div>
          <!-- 卡片体 -->
          <div class="eval-card-body">
            <!-- 权重 -->
            <div class="eval-field">
              <label class="eval-field-label">权重</label>
              <input
                type="number"
                v-model.number="dim.weight"
                class="form-control form-control-sm"
                min="0"
                max="100"
                @input="emitUpdate"
              />
            </div>
            <!-- 阈值（非 LLM Judge 维度；LLM Judge 由维度任务类型决定，无阈值口径） -->
            <div v-if="!isLlmJudge(dim)" class="eval-field">
              <label class="eval-field-label">阈值</label>
              <input
                type="number"
                v-model.number="dim.threshold"
                class="form-control form-control-sm"
                min="0"
                max="100"
                @input="emitUpdate"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 评估开关（enabled） -->
    <div class="eval-toggle-row">
      <label class="eval-toggle-label">
        <input type="checkbox" v-model="localEnabled" @change="emitUpdate" />
        <span>启用本轮评估</span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../../assets/styles/test-common.css'
import '../../../../assets/styles/components/common.css'
import '../../../../assets/styles/components/button.css'
import '../../../../assets/styles/components/form.css'
import '../../../../assets/styles/components/card.css'
import '../../../../assets/styles/components/modal.css'
import '../../../../assets/styles/components/table.css'
import '../../../../assets/styles/components/navigation.css'
import '../../../../assets/styles/components/tag.css'
import '../../../../assets/styles/components/log.css'
import '../../../../assets/styles/layouts/main.css'

import { ref, computed, watch } from 'vue'
import { readCamel } from '@/utils/keyTransform'
import type {
  RoundEvaluationConfig,
  DimensionConfig,
} from '@/domain'
import type { Dimension } from '../../../../domain'

const props = defineProps<{
  modelValue?: RoundEvaluationConfig
  availableDimensions?: Dimension[]
  algorithmType?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: RoundEvaluationConfig]
}>()

// ---- 本地状态 ----
const localEnabled = ref(true)
const localDimensions = ref<DimensionConfig[]>([])

// 从 modelValue 同步到本地状态
watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      localEnabled.value = val.enabled !== false
      localDimensions.value = val.dimensions ? [...val.dimensions] : []
    }
  },
  { immediate: true, deep: true }
)

// ---- 按算法类型过滤维度 ----
const filteredDimensions = computed(() => {
  const dims = props.availableDimensions || []
  if (!props.algorithmType) return dims
  return dims.filter((dim) => {
    const algos = readCamel<unknown[]>(dim, 'associatedAlgorithms')
    if (!Array.isArray(algos) || algos.length === 0) return true
    return algos.some((a: any) => a.algorithmType === props.algorithmType)
  })
})

function isDimSelected(dim: Dimension): boolean {
  return localDimensions.value.some((d) => d.id === dim.id || d.name === dim.name)
}

function toggleDim(dim: Dimension) {
  const idx = localDimensions.value.findIndex(
    (d) => d.id === dim.id || d.name === dim.name
  )
  if (idx >= 0) {
    localDimensions.value.splice(idx, 1)
  } else {
    // INT-1868：新选维度只带权重 / 阈值；LLM Judge 由维度自身 task_type_code 表达，
    // 不再写 llmJudgeConfig（历史条目上的旧值原样透传，不删不清）
    localDimensions.value.push({
      id: dim.id,
      name: dim.name,
      weight: dim.weight ?? 50,
      threshold: 80,
    } as DimensionConfig)
  }
  emitUpdate()
}

function removeDim(index: number) {
  localDimensions.value.splice(index, 1)
  emitUpdate()
}

// ---- LLM Judge 判定（INT-1868：按维度列表里的后端派生 llm_judge 布尔） ----
/** 从可选维度列表找该参数项对应的维度定义（先按 id、再按名称兜底） */
function findDimension(dim: DimensionConfig): Dimension | undefined {
  const dims = props.availableDimensions || []
  return dims.find((d) => d.id === dim.id) ?? dims.find((d) => d.name === dim.name)
}

function isLlmJudge(dim: DimensionConfig): boolean {
  return findDimension(dim)?.llmJudge === true
}

// ---- 发射更新 ----
function emitUpdate() {
  emit('update:modelValue', {
    enabled: localEnabled.value,
    dimensions: [...localDimensions.value],
  })
}
</script>

<style scoped>
.round-evaluation-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 过滤提示 */
.eval-filter-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--info-light, var(--color-blue-50));
  color: var(--info, var(--secondary));
  border-radius: var(--radius-control);
  font-size: 12px;
}

/* 维度 chip 网格 */
.eval-chip-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.eval-chip {
  padding: 7px 14px;
  border-radius: var(--radius-pill);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid var(--border, var(--border));
  background: var(--background, var(--background));
  color: var(--muted-foreground, var(--color-gray-500));
  display: flex;
  align-items: center;
  gap: 5px;
  user-select: none;
}
.eval-chip:hover {
  border-color: var(--primary, var(--primary));
  color: var(--primary, var(--primary));
  transform: translateY(-1px);
}
.eval-chip.active {
  background: var(--primary, var(--primary));
  color: var(--background);
  border-color: var(--primary, var(--primary));
}
.eval-chip.active:hover {
  background: var(--primary-hover, var(--color-orange-600));
}
.eval-chip i {
  font-size: 10px;
}

/* 空状态 */
.eval-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-light, var(--color-gray-400));
  font-size: 13px;
}
.eval-empty i {
  margin-right: 4px;
}

/* 已选维度区域 */
.eval-selected-section {
  margin-top: 4px;
}

.eval-sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground, var(--foreground));
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.eval-sub-title i {
  font-size: 12px;
  color: var(--muted-foreground, var(--color-gray-500));
}

.eval-cards-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.eval-dim-card {
  flex: 1;
  min-width: 180px;
  max-width: 280px;
  background: var(--background, var(--background));
  border: 1px solid var(--border, var(--border));
  border-radius: var(--radius-control);
  overflow: hidden;
}

.eval-card-header {
  padding: 8px 12px;
  background: var(--muted, var(--muted));
  border-bottom: 1px solid var(--border, var(--border));
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.eval-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground, var(--foreground));
}

/* 卡片标题行（标题 + 只读徽章） */
.eval-card-title-group {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

/* INT-1868：LLM Judge 只读徽章（与列表页 dimension-table 的 llm-judge 徽章同口径） */
.eval-llm-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: var(--info-light, var(--color-blue-50));
  color: var(--info, var(--secondary));
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.eval-llm-badge i {
  font-size: 10px;
}

.eval-card-remove-btn {
  width: 22px;
  height: 22px;
  border: 1px solid var(--destructive-light);
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--destructive, var(--destructive));
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  transition: background 0.15s;
}
.eval-card-remove-btn:hover {
  background: var(--destructive-light);
}

.eval-card-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.eval-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.eval-field-label {
  font-size: 11px;
  color: var(--text-light, var(--color-gray-400));
  font-weight: 500;
}

.eval-field .form-control-sm {
  font-size: 13px;
  padding: 4px 8px;
}

/* 评估开关 */
.eval-toggle-row {
  padding-top: 4px;
}

.eval-toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--foreground, var(--foreground));
  cursor: pointer;
}
.eval-toggle-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary, var(--primary));
}
</style>
