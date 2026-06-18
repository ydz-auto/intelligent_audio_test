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
            <span class="eval-card-title">{{ dim.name }}</span>
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
            <!-- 阈值（非 llm_judge 类型） -->
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
            <!-- llm_judge 扩展字段 -->
            <template v-if="isLlmJudge(dim)">
              <div class="eval-field">
                <label class="eval-field-label">模型</label>
                <select
                  class="form-control form-control-sm"
                  :value="getLlmParam(dim, 'model')"
                  @change="setLlmParam(dim, 'model', ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="m in llmModelOptions" :key="m" :value="m">{{ m }}</option>
                </select>
              </div>
              <div class="eval-field">
                <label class="eval-field-label">Prompt 模板</label>
                <select
                  class="form-control form-control-sm"
                  :value="getLlmParam(dim, 'promptTemplate')"
                  @change="setLlmParam(dim, 'promptTemplate', ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="p in llmPromptOptions" :key="p" :value="p">{{ p }}</option>
                </select>
              </div>
            </template>
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
import { ref, computed, watch } from 'vue'
import type {
  RoundEvaluationConfig,
  DimensionConfig,
} from './types'
import type { Dimension } from '../../../../shared/types'

const props = defineProps<{
  modelValue?: RoundEvaluationConfig
  availableDimensions?: Dimension[]
  algorithmType?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: RoundEvaluationConfig]
}>()

// ---- llm_judge 配置选项 ----
const llmModelOptions = ['gpt-4', 'gpt-4o', 'gpt-3.5-turbo', 'claude-3-opus', 'claude-3-sonnet']
const llmPromptOptions = ['default', 'accuracy', 'fluency', 'relevance']

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
    const algos = (dim as any).associated_algorithms
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
    const isLlm = isLlmJudgeDim(dim)
    localDimensions.value.push({
      id: dim.id,
      name: dim.name,
      weight: dim.weight ?? 50,
      threshold: isLlm ? 0 : (80),
      ...(isLlm ? { llmJudgeConfig: { model: 'gpt-4', promptTemplate: 'default' } } : {}),
    } as DimensionConfig)
  }
  emitUpdate()
}

function removeDim(index: number) {
  localDimensions.value.splice(index, 1)
  emitUpdate()
}

// ---- llm_judge 判定 ----
function isLlmJudgeDim(dim: Dimension): boolean {
  return (dim as any).resultType === 'llm_judge'
}

function isLlmJudge(dim: DimensionConfig): boolean {
  return !!(dim as any).llmJudgeConfig
}

function getLlmParam(dim: DimensionConfig, key: string): string {
  const cfg = (dim as any).llmJudgeConfig
  return cfg?.[key] ?? ''
}

function setLlmParam(dim: DimensionConfig, key: string, value: string) {
  if (!(dim as any).llmJudgeConfig) {
    (dim as any).llmJudgeConfig = {}
  }
  (dim as any).llmJudgeConfig[key] = value
  emitUpdate()
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
  background: var(--info-light, #e8f4fd);
  color: var(--info-color, #1890ff);
  border-radius: 6px;
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
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid var(--border-color, #e0e0e0);
  background: var(--background-primary, #fff);
  color: var(--text-secondary, #666);
  display: flex;
  align-items: center;
  gap: 5px;
  user-select: none;
}
.eval-chip:hover {
  border-color: var(--primary-color, #ff6a00);
  color: var(--primary-color, #ff6a00);
  transform: translateY(-1px);
}
.eval-chip.active {
  background: var(--primary-color, #ff6a00);
  color: #fff;
  border-color: var(--primary-color, #ff6a00);
}
.eval-chip.active:hover {
  background: var(--primary-dark, #e05500);
}
.eval-chip i {
  font-size: 10px;
}

/* 空状态 */
.eval-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-light, #999);
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
  color: var(--text-primary, #333);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.eval-sub-title i {
  font-size: 12px;
  color: var(--text-secondary, #666);
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
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}

.eval-card-header {
  padding: 8px 12px;
  background: var(--background-secondary, #f5f5f5);
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.eval-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.eval-card-remove-btn {
  width: 22px;
  height: 22px;
  border: 1px solid #ffcdd2;
  border-radius: 4px;
  background: transparent;
  color: var(--danger-color, #f44336);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  transition: background 0.15s;
}
.eval-card-remove-btn:hover {
  background: #ffebee;
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
  color: var(--text-light, #999);
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
  color: var(--text-primary, #333);
  cursor: pointer;
}
.eval-toggle-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary-color, #ff6a00);
}
</style>
