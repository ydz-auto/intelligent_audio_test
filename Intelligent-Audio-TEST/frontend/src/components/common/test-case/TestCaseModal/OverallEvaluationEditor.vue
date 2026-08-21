<template>
  <div class="overall-eval-editor">
    <!-- 标题区 -->
    <div class="overall-header">
      <div class="overall-icon">
        <i class="fas fa-layer-group"></i>
      </div>
      <div class="overall-title-group">
        <div class="overall-title">
          整体评估维度
          <span class="overall-badge">所有轮次</span>
        </div>
        <div class="overall-subtitle">config.dimensions — 对多轮测试结果的综合评估</div>
      </div>
    </div>

    <!-- 描述说明 -->
    <div class="overall-description">
      整体评估在<span class="highlight">所有轮次执行完成后</span>触发，将多轮结果汇总后统一送给评估端点。
      与单轮评估（每轮独立打分）不同，整体评估关注的是跨轮次的综合指标，例如
      <span class="highlight">多轮平均 WER</span>、<span class="highlight">对话连贯性</span>、
      <span class="highlight">上下文一致性</span> 等。
    </div>

    <!-- 启用开关 -->
    <div class="overall-toggle-row" @click="enabled = !enabled">
      <div class="toggle-switch" :class="{ active: enabled }">
        <div class="toggle-knob"></div>
      </div>
      <span class="toggle-label">启用整体评估</span>
    </div>

    <!-- 可折叠内容 -->
    <div v-if="enabled" class="overall-content">
      <!-- 维度 chips 选择区 -->
      <div class="eval-chip-grid">
        <div
          v-for="dim in filteredDimensions"
          :key="dim.id"
          class="eval-chip"
          :class="{ active: isDimSelected(dim) }"
          :title="(dim as any).requiresAudio ? '该维度需要音频文件，将随多轮音频一起上传' : ''"
          @click="toggleDim(dim)"
        >
          <i :class="isDimSelected(dim) ? 'fas fa-check' : 'fas fa-plus'"></i>
          {{ dim.name }}
          <i v-if="(dim as any).requiresAudio" class="fas fa-music" style="margin-left: 2px; font-size: 9px;"></i>
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { DimensionConfig } from './types'
import type { Dimension } from '../../../../shared/types'

const props = defineProps<{
  modelValue?: DimensionConfig[]
  availableDimensions?: Dimension[]
  algorithmType?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: DimensionConfig[]]
}>()

// ---- llm_judge 配置选项 ----
const llmModelOptions = ['gpt-4', 'gpt-4o', 'gpt-3.5-turbo', 'claude-3-opus', 'claude-3-sonnet']
const llmPromptOptions = ['default', 'accuracy', 'fluency', 'relevance']

// ---- 本地状态 ----
const enabled = ref(true)
const localDimensions = ref<DimensionConfig[]>([])

// 从 modelValue 同步到本地状态
watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      localDimensions.value = Array.isArray(val) ? [...val] : []
      // 如果有维度数据则自动启用
      if (localDimensions.value.length > 0) {
        enabled.value = true
      }
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
      threshold: isLlm ? 0 : 80,
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
  // 启用时返回维度数组，禁用时返回空数组
  emit('update:modelValue', enabled.value ? [...localDimensions.value] : [])
}

// 监听 enabled 变化
watch(enabled, () => {
  emitUpdate()
})
</script>

<style scoped>
.overall-eval-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 24px;
  border-top: 2px dashed var(--primary-color, #FF6A00);
  padding-top: 24px;
}

/* 标题区 */
.overall-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.overall-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(255, 106, 0, 0.1);
  color: #FF6A00;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.overall-title-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.overall-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  display: flex;
  align-items: center;
}
.overall-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: rgba(255, 106, 0, 0.1);
  color: #FF6A00;
  border-radius: 100px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 8px;
}
.overall-subtitle {
  font-size: 12px;
  color: #777;
}

/* 描述说明 */
.overall-description {
  font-size: 12px;
  color: #777;
  background: #F5F5F5;
  border-radius: 8px;
  padding: 8px 16px;
  line-height: 1.6;
  border-left: 3px solid #FF6A00;
}
.overall-description .highlight {
  color: #FF6A00;
  font-weight: 600;
}

/* 启用开关 */
.overall-toggle-row {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 14px;
  color: #777;
  user-select: none;
  padding: 4px 0;
}
.overall-toggle-row:hover {
  color: #FF6A00;
}
.toggle-switch {
  width: 36px;
  height: 20px;
  border-radius: 100px;
  background: #E5E7EB;
  position: relative;
  transition: background 0.2s;
  flex-shrink: 0;
}
.toggle-switch.active {
  background: #FF6A00;
}
.toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: white;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.toggle-switch.active .toggle-knob {
  transform: translateX(16px);
}

/* 可折叠内容 */
.overall-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Eval chips */
.eval-chip-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.eval-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 16px;
  border: 1px solid #E5E7EB;
  border-radius: 100px;
  font-size: 12px;
  color: #777;
  cursor: pointer;
  transition: all 0.2s;
  background: #FFF;
  user-select: none;
}
.eval-chip:hover {
  border-color: #FF6A00;
  color: #FF6A00;
}
.eval-chip.active {
  background: rgba(255, 106, 0, 0.1);
  border-color: #FF6A00;
  color: #FF6A00;
  font-weight: 600;
}
.eval-chip.disabled {
  opacity: 0.4;
  cursor: not-allowed;
  border-style: dashed;
}
.eval-chip.disabled:hover {
  border-color: #E5E7EB;
  color: #999;
}
.eval-chip i {
  font-size: 10px;
}

.eval-empty {
  padding: 16px;
  text-align: center;
  color: #999;
  font-size: 14px;
}

/* 已选维度卡片 */
.eval-selected-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.eval-sub-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #777;
  font-weight: 500;
}
.eval-cards-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.eval-dim-card {
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 12px;
  background: #FFF;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 280px;
}
.eval-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.eval-card-title {
  font-size: 14px;
  font-weight: 600;
  color: #FF6A00;
}
.eval-card-remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #999;
  font-size: 14px;
  padding: 0 4px;
}
.eval-card-remove-btn:hover {
  color: #DC2626;
}
.eval-card-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.eval-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.eval-field-label {
  font-size: 11px;
  color: #999;
}
.form-control-sm {
  padding: 4px 8px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  font-size: 12px;
  color: #333;
  background: #FFF;
}
</style>
