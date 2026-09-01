<script setup lang="ts">
import { ref, computed, watch } from 'vue'

/** 维度配置项 */
interface DimensionItem {
  id: string | number
  name: string
  weight?: number
  threshold?: number
}

/** 组件输出数据结构 */
export interface DimensionConfigData {
  /** 统一模式下的维度列表 */
  dimensions: DimensionItem[]
  /** 轮次范围模式 */
  roundMode: 'all' | 'specific' | 'per_round'
  /** 指定轮次模式下选中的轮次号 */
  roundNumbers: number[]
  /** 逐轮模式下各轮次维度映射 */
  roundDimensions?: Record<number, DimensionItem[]>
  /** 多轮整体评估维度 */
  multiDimensions?: DimensionItem[]
}

interface Props {
  /** v-model 绑定（DimensionConfigData） */
  modelValue?: Partial<DimensionConfigData>
  /** 可选维度列表（已过滤、已搜索） */
  availableDimensions: any[]
  /** 是否正在加载维度 */
  loading?: boolean
  /** 加载错误信息 */
  error?: string
  /** 是否必选 */
  required?: boolean
  /** 搜索关键字（v-model:searchQuery） */
  searchQuery?: string
  /** 最大轮次数（用于初始化逐轮 tabs） */
  maxRoundNumbers?: number
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => ({}),
  loading: false,
  error: '',
  required: false,
  searchQuery: '',
  maxRoundNumbers: 3
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: DimensionConfigData): void
  (e: 'update:searchQuery', value: string): void
}>()

// === 从 modelValue 同步状态 ===
const roundMode = ref<'all' | 'specific' | 'per_round'>(
  props.modelValue.roundMode || 'all'
)
const roundNumbers = ref<number[]>(props.modelValue.roundNumbers || [])
const selectedDimensions = ref<DimensionItem[]>(props.modelValue.dimensions || [])
const dimConfigs = ref<Record<string, { weight: number; threshold: number }>>({})
const multiSelectedDimensions = ref<DimensionItem[]>(props.modelValue.multiDimensions || [])
const multiDimConfigs = ref<Record<string, { weight: number; threshold: number }>>({})

// === 逐轮设置模式状态 ===
const activeRoundTab = ref<number>(1)
const roundSelectedDimensions = ref<Record<number, DimensionItem[]>>({})
const roundDimConfigs = ref<Record<number, Record<string, { weight: number; threshold: number }>>>({})
const showCopySource = ref(false)
const copySourceRound = ref<number>(1)

// 可变轮次列表
const availableRoundNumbers = ref<number[]>(
  Array.from({ length: props.maxRoundNumbers }, (_, i) => i + 1)
)

// 所有轮次标签（包括最后一轮 -1）
const allRoundTabs = computed(() => [...availableRoundNumbers.value, -1])

// === 搜索 ===
const localSearchQuery = computed({
  get: () => props.searchQuery,
  set: (val) => emit('update:searchQuery', val)
})

// === 统一模式方法 ===
function toggleRoundNumber(rn: number) {
  const idx = roundNumbers.value.indexOf(rn)
  if (idx >= 0) {
    roundNumbers.value.splice(idx, 1)
  } else {
    roundNumbers.value.push(rn)
  }
  emitUpdate()
}

const isDimensionSelected = (dim: any) => {
  return selectedDimensions.value.some(d => d.id === dim.id)
}

function toggleDimension(dim: any) {
  if (isDimensionSelected(dim)) {
    selectedDimensions.value = selectedDimensions.value.filter(d => d.id !== dim.id)
    delete dimConfigs.value[dim.id]
  } else {
    selectedDimensions.value.push(dim)
    dimConfigs.value[dim.id] = { weight: 50, threshold: 60 }
  }
  emitUpdate()
}

function removeDimension(index: number) {
  const dim = selectedDimensions.value[index]
  delete dimConfigs.value[dim.id]
  selectedDimensions.value.splice(index, 1)
  emitUpdate()
}

// === 逐轮设置模式方法 ===
function ensureRoundState(rn: number) {
  if (!roundSelectedDimensions.value[rn]) {
    roundSelectedDimensions.value[rn] = []
  }
  if (!roundDimConfigs.value[rn]) {
    roundDimConfigs.value[rn] = {}
  }
}

function isRoundDimensionSelected(rn: number, dim: any) {
  ensureRoundState(rn)
  return roundSelectedDimensions.value[rn].some(d => d.id === dim.id)
}

function toggleRoundDimension(rn: number, dim: any) {
  ensureRoundState(rn)
  if (isRoundDimensionSelected(rn, dim)) {
    roundSelectedDimensions.value[rn] = roundSelectedDimensions.value[rn].filter(d => d.id !== dim.id)
    delete roundDimConfigs.value[rn][dim.id]
  } else {
    roundSelectedDimensions.value[rn].push(dim)
    roundDimConfigs.value[rn][dim.id] = { weight: 50, threshold: 60 }
  }
  emitUpdate()
}

function getRoundSelectedDimensions(rn: number): DimensionItem[] {
  ensureRoundState(rn)
  return roundSelectedDimensions.value[rn]
}

function removeRoundDimension(rn: number, index: number) {
  ensureRoundState(rn)
  const dim = roundSelectedDimensions.value[rn][index]
  delete roundDimConfigs.value[rn][dim.id]
  roundSelectedDimensions.value[rn].splice(index, 1)
  emitUpdate()
}

function addRound() {
  const next = availableRoundNumbers.value.length > 0
    ? Math.max(...availableRoundNumbers.value) + 1
    : 1
  availableRoundNumbers.value.push(next)
  ensureRoundState(next)
  activeRoundTab.value = next
}

function removeRound(rn: number) {
  const idx = availableRoundNumbers.value.indexOf(rn)
  if (idx < 0) return
  availableRoundNumbers.value.splice(idx, 1)
  delete roundSelectedDimensions.value[rn]
  delete roundDimConfigs.value[rn]
  // 如果删的是当前激活的 tab，切到第一个可用的
  if (activeRoundTab.value === rn) {
    activeRoundTab.value = availableRoundNumbers.value.length > 0
      ? availableRoundNumbers.value[0]
      : -1
  }
  // 至少保留1个轮次，没有则自动补一个
  if (availableRoundNumbers.value.length === 0) {
    availableRoundNumbers.value = [1]
    ensureRoundState(1)
    if (activeRoundTab.value === -1) {
      activeRoundTab.value = 1
    }
  }
  emitUpdate()
}

function copyFromRound(_rn: number) {
  showCopySource.value = true
  const otherRounds = allRoundTabs.value.filter(r => r !== activeRoundTab.value)
  if (otherRounds.length > 0) {
    copySourceRound.value = otherRounds[0]
  }
}

function doCopyFromRound() {
  const srcRn = copySourceRound.value
  const dstRn = activeRoundTab.value
  ensureRoundState(srcRn)
  ensureRoundState(dstRn)
  roundSelectedDimensions.value[dstRn] = roundSelectedDimensions.value[srcRn].map(d => ({ ...d }))
  roundDimConfigs.value[dstRn] = {}
  for (const key in roundDimConfigs.value[srcRn]) {
    roundDimConfigs.value[dstRn][key] = { ...roundDimConfigs.value[srcRn][key] }
  }
  showCopySource.value = false
  emitUpdate()
}

function clearRound(rn: number) {
  ensureRoundState(rn)
  roundSelectedDimensions.value[rn] = []
  roundDimConfigs.value[rn] = {}
  emitUpdate()
}

function applyToAllRounds(srcRn: number) {
  ensureRoundState(srcRn)
  for (const rn of allRoundTabs.value) {
    if (rn === srcRn) continue
    ensureRoundState(rn)
    roundSelectedDimensions.value[rn] = roundSelectedDimensions.value[srcRn].map(d => ({ ...d }))
    roundDimConfigs.value[rn] = {}
    for (const key in roundDimConfigs.value[srcRn]) {
      roundDimConfigs.value[rn][key] = { ...roundDimConfigs.value[srcRn][key] }
    }
  }
  emitUpdate()
}

// 切换到逐轮设置时初始化各轮次状态
watch(roundMode, (newMode) => {
  if (newMode === 'per_round') {
    for (const rn of allRoundTabs.value) {
      ensureRoundState(rn)
    }
  }
  if (newMode !== 'per_round') {
    showCopySource.value = false
  }
  emitUpdate()
})

// === 多轮整体评估维度方法 ===
const isMultiDimensionSelected = (dim: any) => {
  return multiSelectedDimensions.value.some(d => d.id === dim.id)
}

function toggleMultiDimension(dim: any) {
  if (isMultiDimensionSelected(dim)) {
    multiSelectedDimensions.value = multiSelectedDimensions.value.filter(d => d.id !== dim.id)
    delete multiDimConfigs.value[dim.id]
  } else {
    multiSelectedDimensions.value.push(dim)
    multiDimConfigs.value[dim.id] = { weight: 50, threshold: 60 }
  }
  emitUpdate()
}

function removeMultiDimension(index: number) {
  const dim = multiSelectedDimensions.value[index]
  delete multiDimConfigs.value[dim.id]
  multiSelectedDimensions.value.splice(index, 1)
  emitUpdate()
}

// === 发射更新 ===
function emitUpdate() {
  const multiDims = multiSelectedDimensions.value.map(dim => ({
    id: dim.id,
    name: dim.name,
    weight: multiDimConfigs.value[dim.id]?.weight ?? 50,
    threshold: multiDimConfigs.value[dim.id]?.threshold ?? 60
  }))

  if (roundMode.value === 'per_round') {
    const rd: Record<number, DimensionItem[]> = {}
    for (const rn of allRoundTabs.value) {
      ensureRoundState(rn)
      rd[rn] = roundSelectedDimensions.value[rn].map(dim => ({
        id: dim.id,
        name: dim.name,
        weight: roundDimConfigs.value[rn][dim.id]?.weight ?? 50,
        threshold: roundDimConfigs.value[rn][dim.id]?.threshold ?? 60
      }))
    }
    emit('update:modelValue', {
      dimensions: [],
      roundMode: 'per_round',
      roundNumbers: [],
      roundDimensions: rd,
      multiDimensions: multiDims
    })
  } else {
    const dims = selectedDimensions.value.map(dim => ({
      id: dim.id,
      name: dim.name,
      weight: dimConfigs.value[dim.id]?.weight ?? 50,
      threshold: dimConfigs.value[dim.id]?.threshold ?? 60
    }))
    emit('update:modelValue', {
      dimensions: dims,
      roundMode: roundMode.value,
      roundNumbers: roundNumbers.value,
      multiDimensions: multiDims
    })
  }
}

// === 计算属性 ===
const hasDimensions = computed(() => {
  if (roundMode.value === 'per_round') {
    return allRoundTabs.value.some(rn => getRoundSelectedDimensions(rn).length > 0)
  }
  return selectedDimensions.value.length > 0
})
const dimensionCount = computed(() => {
  if (roundMode.value === 'per_round') {
    return allRoundTabs.value.reduce((sum, rn) => sum + getRoundSelectedDimensions(rn).length, 0)
  }
  return selectedDimensions.value.length
})
</script>

<template>
  <div class="dimension-config-panel">
    <!-- 轮次范围模式选择 -->
    <div class="scope-section">
      <label>单轮评估维度 - 轮次范围</label>
      <div class="radio-group">
        <label class="radio-label">
          <input type="radio" value="all" v-model="roundMode" />
          <span>所有轮次（统一设置）</span>
        </label>
        <label class="radio-label">
          <input type="radio" value="specific" v-model="roundMode" />
          <span>指定轮次（统一设置）</span>
        </label>
        <label class="radio-label">
          <input type="radio" value="per_round" v-model="roundMode" />
          <span>逐轮设置（每轮可不同）</span>
        </label>
      </div>
      <p class="mode-hint" v-if="roundMode === 'all'">所有轮次共用同一套评估维度，每轮独立评分。不选任何维度点确定即清空已有的评估维度</p>
      <p class="mode-hint" v-else-if="roundMode === 'specific'">仅对选中的轮次统一设置评估维度，其他轮次不受影响。不选任何维度点确定即清空选中轮次的评估维度</p>
      <p class="mode-hint" v-else>每轮可独立选择不同的评估维度，未选维度的轮次将被清空</p>
    </div>

    <!-- 指定轮次选择 -->
    <div class="scope-section" v-if="roundMode === 'specific'">
      <label>选择轮次</label>
      <div class="round-checkboxs">
        <label
          v-for="rn in availableRoundNumbers"
          :key="rn"
          :class="{ checked: roundNumbers.includes(rn) }"
          @click="toggleRoundNumber(rn)"
        >
          第{{ rn }}轮
        </label>
        <label :class="{ checked: roundNumbers.includes(-1) }" @click="toggleRoundNumber(-1)">
          最后一轮
        </label>
      </div>
      <p class="level-hint">"最后一轮"会根据每个用例的实际轮次数动态解析</p>
    </div>

    <!-- 统一模式：所有/指定轮次共用同一套维度 -->
    <template v-if="roundMode === 'all' || roundMode === 'specific'">
      <!-- 搜索工具栏 + 已选计数 -->
      <div class="dimension-toolbar">
        <input
          type="text"
          class="form-input"
          placeholder="搜索评估维度"
          :value="localSearchQuery"
          @input="localSearchQuery = ($event.target as HTMLInputElement).value"
          @click.stop
        >
        <div class="dimension-summary" :class="{ 'has-error': required && !hasDimensions }">
            已选 {{ dimensionCount }} 项
          </div>
      </div>

      <div class="form-group">
        <label>单轮评价维度</label>
        <div class="dimension-cloud-container" v-if="!loading">
          <div
            v-for="dim in availableDimensions"
            :key="dim.id"
            class="dimension-tag"
            :class="{ 'selected': isDimensionSelected(dim) }"
            @click.stop.prevent="toggleDimension(dim)"
          >
            {{ dim.name }}
          </div>
          <p v-if="availableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
        </div>
        <div class="dimension-loading" v-else>加载中...</div>
        <p class="option-hint" v-if="error">{{ error }}</p>
        <p class="option-hint error" v-if="required && !hasDimensions">请至少选择一个评估维度</p>
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
                  <input type="number" v-model.number="dimConfigs[dim.id].weight" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
                <div class="form-group">
                  <label>阈值（0-100）</label>
                  <input type="number" v-model.number="dimConfigs[dim.id].threshold" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 逐轮设置模式：每个轮次独立配置维度 -->
    <template v-if="roundMode === 'per_round'">
      <div class="per-round-container">
        <div class="round-tabs">
          <div
            v-for="rn in availableRoundNumbers"
            :key="rn"
            class="round-tab"
            :class="{ active: activeRoundTab === rn }"
            @click="activeRoundTab = rn"
          >
            第{{ rn }}轮
            <span class="round-tab-count" v-if="getRoundSelectedDimensions(rn).length > 0">{{ getRoundSelectedDimensions(rn).length }}</span>
            <span class="round-tab-close" @click.stop="removeRound(rn)">
              <i class="fas fa-times"></i>
            </span>
          </div>
          <button type="button" class="round-tab-add" @click="addRound">
            <i class="fas fa-plus"></i> 添加轮次
          </button>
          <div
            class="round-tab round-tab-special"
            :class="{ active: activeRoundTab === -1 }"
            @click="activeRoundTab = -1"
          >
            <i class="fas fa-flag"></i> 最后一轮
            <span class="round-tab-count" v-if="getRoundSelectedDimensions(-1).length > 0">{{ getRoundSelectedDimensions(-1).length }}</span>
          </div>
        </div>

        <div class="round-content" v-if="activeRoundTab">
          <!-- 搜索工具栏 + 已选计数 -->
          <div class="dimension-toolbar">
            <input
              type="text"
              class="form-input"
              placeholder="搜索评估维度"
              :value="localSearchQuery"
              @input="localSearchQuery = ($event.target as HTMLInputElement).value"
              @click.stop
            >
            <div class="dimension-summary" :class="{ 'has-error': required && !hasDimensions }">
              已选 {{ dimensionCount }} 项
            </div>
          </div>

          <div class="form-group">
            <label>{{ activeRoundTab === -1 ? '最后一轮 - 评价维度' : `第${activeRoundTab}轮 - 评价维度` }}</label>
            <div class="dimension-cloud-container" v-if="!loading">
              <div
                v-for="dim in availableDimensions"
                :key="dim.id"
                class="dimension-tag"
                :class="{ 'selected': isRoundDimensionSelected(activeRoundTab, dim) }"
                @click.stop.prevent="toggleRoundDimension(activeRoundTab, dim)"
              >
                {{ dim.name }}
              </div>
              <p v-if="availableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
            </div>
            <div class="dimension-loading" v-else>加载中...</div>
            <p class="option-hint" v-if="error">{{ error }}</p>
            <p class="option-hint error" v-if="required && !hasDimensions">请至少选择一个评估维度</p>
          </div>

          <div v-if="getRoundSelectedDimensions(activeRoundTab).length > 0" class="form-group">
            <label>{{ activeRoundTab === -1 ? '最后一轮 - 维度权重和阈值配置' : `第${activeRoundTab}轮 - 维度权重和阈值配置` }}</label>
            <div class="dimension-config-list">
              <div v-for="(dim, index) in getRoundSelectedDimensions(activeRoundTab)" :key="dim.id" class="dimension-config-item">
                <div class="dimension-config-header">
                  <span class="dimension-config-name">{{ dim.name }}</span>
                  <button type="button" class="btn btn-xs btn-danger" @click="removeRoundDimension(activeRoundTab, index)">
                    <i class="fas fa-times"></i>
                  </button>
                </div>
                <div class="dimension-config-fields">
                  <div class="form-row">
                    <div class="form-group">
                      <label>权重（0-100）</label>
                      <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].weight" class="form-input" min="0" max="100" @input="emitUpdate" />
                    </div>
                    <div class="form-group">
                      <label>阈值（0-100）</label>
                      <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].threshold" class="form-input" min="0" max="100" @input="emitUpdate" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">请从上方选择评价维度</p>

          <p v-if="activeRoundTab === -1" class="last-round-hint">
            <i class="fas fa-info-circle"></i> "最后一轮"会根据每个用例的实际轮次数动态解析（如2轮用例→第2轮，3轮用例→第3轮）
          </p>
        </div>

        <!-- 快速操作工具栏 -->
        <div class="per-round-toolbar">
          <button type="button" class="btn btn-xs btn-secondary" @click="copyFromRound(activeRoundTab)" :disabled="allRoundTabs.length <= 1">
            从其他轮次复制
          </button>
          <button type="button" class="btn btn-xs btn-secondary" @click="clearRound(activeRoundTab)" :disabled="getRoundSelectedDimensions(activeRoundTab).length === 0">
            清空当前轮次
          </button>
          <button type="button" class="btn btn-xs btn-secondary" @click="applyToAllRounds(activeRoundTab)" :disabled="getRoundSelectedDimensions(activeRoundTab).length === 0 || allRoundTabs.length <= 1">
            应用到所有轮次
          </button>
        </div>

        <!-- 复制来源选择 -->
        <div class="copy-source" v-if="showCopySource">
          <span>从</span>
          <select v-model="copySourceRound" class="form-input copy-source-select">
            <option v-for="rn in allRoundTabs.filter(r => r !== activeRoundTab)" :key="rn" :value="rn">{{ rn === -1 ? '最后一轮' : `第${rn}轮` }}</option>
          </select>
          <span>复制</span>
          <button type="button" class="btn btn-xs btn-primary" @click="doCopyFromRound">确定</button>
          <button type="button" class="btn btn-xs btn-secondary" @click="showCopySource = false">取消</button>
        </div>
      </div>
    </template>

    <!-- 多轮整体评估维度 -->
    <div class="scope-section multi-section">
      <label>多轮整体评估维度（跨轮次聚合） <span class="optional-tag">可选</span></label>
      <p class="section-desc">这些维度基于所有轮次的整体表现进行评估，与单轮维度独立配置。不选任何维度将清空已有的整体评估维度</p>
      <div class="dimension-cloud-container" v-if="!loading">
        <div
          v-for="dim in availableDimensions"
          :key="'multi-' + dim.id"
          class="dimension-tag"
          :class="{ 'selected': isMultiDimensionSelected(dim) }"
          @click.stop.prevent="toggleMultiDimension(dim)"
        >
          {{ dim.name }}
        </div>
        <p v-if="availableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
      </div>
      <div class="dimension-loading" v-else>加载中...</div>

      <div v-if="multiSelectedDimensions.length > 0" class="form-group" style="margin-top: 12px;">
        <label>整体评估 - 权重和阈值配置</label>
        <div class="dimension-config-list">
          <div v-for="(dim, index) in multiSelectedDimensions" :key="'multi-cfg-' + dim.id" class="dimension-config-item">
            <div class="dimension-config-header">
              <span class="dimension-config-name">{{ dim.name }}</span>
              <button type="button" class="btn btn-xs btn-danger" @click="removeMultiDimension(index)">
                <i class="fas fa-times"></i>
              </button>
            </div>
            <div class="dimension-config-fields">
              <div class="form-row">
                <div class="form-group">
                  <label>权重（0-100）</label>
                  <input type="number" v-model.number="multiDimConfigs[dim.id].weight" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
                <div class="form-group">
                  <label>阈值（0-100）</label>
                  <input type="number" v-model.number="multiDimConfigs[dim.id].threshold" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dimension-config-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 搜索工具栏 */
.dimension-toolbar {
  display: flex;
  gap: 12px;
}

.dimension-toolbar .form-input {
  flex: 1;
}

.dimension-summary {
  padding: 10px 14px;
  background-color: #f8f9fa;
  border-radius: 6px;
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
  font-weight: 500;
  border: 1px solid #e9ecef;
}

.dimension-summary.has-error {
  background-color: #fee2e2;
  color: #dc2626;
  border-color: #dc2626;
}

/* 维度标签云 */
.dimension-cloud-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 16px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  max-height: 180px;
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

.dimension-loading {
  padding: 24px;
  text-align: center;
  color: #1976d2;
  font-size: 14px;
  width: 100%;
}

/* 提示 */
.option-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #94a3b8;
}

.option-hint.error {
  color: #dc2626;
}

/* 表单 */
.form-group {
  margin-bottom: 16px;
}

.form-group > label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
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

/* 维度配置列表 */
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

/* 按钮 */
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

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background-color: #5a6268;
}

.btn-secondary:disabled {
  background-color: #adb5bd;
  cursor: not-allowed;
}

.btn-primary {
  background-color: #007bff;
  color: white;
}

.btn-primary:hover {
  background-color: #0056b3;
}

/* 轮次范围模式选择 */
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
  gap: 16px;
  flex-wrap: wrap;
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

.mode-hint {
  font-size: 11px;
  color: #f59e0b;
  margin-top: 8px;
}

/* 指定轮次 */
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

.level-hint {
  font-size: 11px;
  color: #999;
  margin-left: 24px;
  margin-top: 8px;
}

/* 逐轮设置模式 */
.per-round-container {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.round-tabs {
  display: flex;
  border-bottom: 2px solid #e2e8f0;
  background: #f8fafc;
  overflow-x: auto;
}

.round-tab {
  padding: 10px 20px;
  cursor: pointer;
  font-size: 14px;
  color: #64748b;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.round-tab:hover {
  color: #1677ff;
  background: #f0f9ff;
}

.round-tab.active {
  color: #1677ff;
  border-bottom-color: #1677ff;
  background: #fff;
  font-weight: 600;
}

.round-tab-special {
  border-left: 1px solid #e2e8f0;
}

.round-tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 2px;
  border-radius: 50%;
  font-size: 10px;
  color: #94a3b8;
  transition: all 0.2s;
}

.round-tab-close:hover {
  background: #ef4444;
  color: #fff;
}

.round-tab-add {
  padding: 10px 16px;
  cursor: pointer;
  font-size: 13px;
  color: #1677ff;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.round-tab-add:hover {
  color: #0958d9;
  background: #f0f9ff;
}

.round-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: #1677ff;
  color: #fff;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
}

.round-content {
  padding: 16px;
}

.per-round-toolbar {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #e2e8f0;
  background: #f8fafc;
  flex-wrap: wrap;
}

.copy-source {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #fff3cd;
  border-top: 1px solid #ffe08a;
  font-size: 13px;
  color: #856404;
}

.copy-source-select {
  width: auto;
  min-width: 100px;
  padding: 6px 10px;
}

.last-round-hint {
  margin-top: 12px;
  padding: 8px 12px;
  background: #e6f4ff;
  border: 1px solid #91caff;
  border-radius: 6px;
  font-size: 12px;
  color: #0958d9;
}

/* 多轮整体评估维度区域 */
.multi-section {
  background: #f0fdf4;
  border-color: #bbf7d0;
}

.multi-section > label {
  color: #166534;
}

.optional-tag {
  display: inline-block;
  padding: 1px 8px;
  background: #dcfce7;
  color: #166534;
  border-radius: 10px;
  font-size: 11px;
  font-weight: normal;
  margin-left: 6px;
}

.section-desc {
  margin: 0 0 12px 0;
  font-size: 12px;
  color: #6b7280;
}
</style>
