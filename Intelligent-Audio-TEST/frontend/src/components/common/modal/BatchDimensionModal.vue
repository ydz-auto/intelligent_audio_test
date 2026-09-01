<template>
  <div class="batch-dimension-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">{{ selectionMode === 'selected' ? '您勾选了' : '将对' }} {{ caseCount }} 个用例设置评价维度</p>
    </div>

    <div class="modal-body">
      <!-- 轮次范围模式选择 -->
      <div class="scope-section">
        <label>单轮评估维度 - 轮次范围</label>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" :value="'all'" v-model="roundMode" />
            <span>所有轮次（统一设置）</span>
          </label>
          <label class="radio-label">
            <input type="radio" :value="'specific'" v-model="roundMode" />
            <span>指定轮次（统一设置）</span>
          </label>
          <label class="radio-label">
            <input type="radio" :value="'per_round'" v-model="roundMode" />
            <span>逐轮设置（每轮可不同）</span>
          </label>
        </div>
        <p class="mode-hint" v-if="roundMode === 'per_round'">提示：逐轮设置模式下，未选维度的轮次将被清空</p>
        <p class="mode-hint" v-else>提示：不选任何维度点确定即清除选中轮次的评估维度</p>
      </div>
      <div class="scope-section" v-if="roundMode === 'specific'">
        <label>选择轮次</label>
        <div class="round-checkboxs">
          <label v-for="rn in availableRoundNumbers" :key="rn"
                 :class="{ checked: roundNumbers.includes(rn) }"
                 @click="toggleRoundNumber(rn)">
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
        <div class="form-group">
          <label>单轮评价维度</label>
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
              <span v-if="availableRoundNumbers.length > 1" class="round-tab-close" @click.stop="removeRound(rn)">
                <i class="fas fa-times"></i>
              </span>
            </div>
            <button type="button" class="round-tab-add" @click="addRound">
              <i class="fas fa-plus"></i> 添加轮次
            </button>
            <!-- 最后一轮特殊标签 -->
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
            <div class="form-group">
              <label>{{ activeRoundTab === -1 ? '最后一轮 - 评价维度' : `第${activeRoundTab}轮 - 评价维度` }}</label>
              <div class="dimension-cloud-container">
                <div
                  v-for="dim in filteredAvailableDimensions"
                  :key="dim.id"
                  class="dimension-tag"
                  :class="{ 'selected': isRoundDimensionSelected(activeRoundTab, dim) }"
                  @click="toggleRoundDimension(activeRoundTab, dim)"
                >
                  {{ dim.name }}
                </div>
              </div>
              <p v-if="filteredAvailableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
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
                        <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].weight" class="form-input" min="0" max="100" />
                      </div>
                      <div class="form-group">
                        <label>阈值（0-100）</label>
                        <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].threshold" class="form-input" min="0" max="100" />
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
        <div class="dimension-cloud-container">
          <div
            v-for="dim in filteredAvailableDimensions"
            :key="'multi-' + dim.id"
            class="dimension-tag"
            :class="{ 'selected': isMultiDimensionSelected(dim) }"
            @click="toggleMultiDimension(dim)"
          >
            {{ dim.name }}
          </div>
        </div>
        <p v-if="filteredAvailableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>

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
                    <input type="number" v-model.number="multiDimConfigs[dim.id].weight" class="form-input" min="0" max="100" />
                  </div>
                  <div class="form-group">
                    <label>阈值（0-100）</label>
                    <input type="number" v-model.number="multiDimConfigs[dim.id].threshold" class="form-input" min="0" max="100" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useDimensions } from '../../../composables/shared/useDimensions'
import { TestType } from '@/shared/types/enums'

// === 常量定义 ===
/** 默认权重 */
const DEFAULT_WEIGHT = 50
/** 默认阈值 */
const DEFAULT_THRESHOLD = 60
/** 最后一轮的特殊标识（-1 代表动态解析的"最后一轮"） */
const LAST_ROUND_NUMBER = -1
/** 轮次范围模式枚举 */
const ROUND_MODE = {
  ALL: 'all',
  SPECIFIC: 'specific',
  PER_ROUND: 'per_round',
} as const

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
    dimensions: Array<{id: string; name: string; weight: number; threshold: number}>;
    testType: string;
    roundMode: string;
    roundNumbers: number[];
    roundDimensions?: Record<number, Array<{id: string; name: string; weight: number; threshold: number}>>;
    multiDimensions?: Array<{id: string; name: string; weight: number; threshold: number}>;
  }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置评价维度',
  caseCount: 0,
  algorithmType: '',
  testType: TestType.E2E,
  maxRoundNumbers: 3,
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

const { fetchAllDimensions, fetchDimensionsByAlgorithmType, getDimensionsByAlgorithmType } = useDimensions()

const availableDimensions = ref<Dimension[]>([])

// === 统一模式状态 ===
const selectedDimensions = ref<Dimension[]>([])
const dimConfigs = ref<Record<string, { weight: number; threshold: number }>>({})
const roundMode = ref<'all' | 'specific' | 'per_round'>(ROUND_MODE.ALL)
const roundNumbers = ref<number[]>([])

// === 逐轮设置模式状态 ===
// -1 代表"最后一轮"，正数代表具体轮次
const activeRoundTab = ref<number>(1)
const roundSelectedDimensions = ref<Record<number, Dimension[]>>({})
const roundDimConfigs = ref<Record<number, Record<string, { weight: number; threshold: number }>>>({})
const showCopySource = ref(false)
const copySourceRound = ref<number>(1)

// === 多轮整体评估维度状态 ===
const multiSelectedDimensions = ref<Dimension[]>([])
const multiDimConfigs = ref<Record<string, { weight: number; threshold: number }>>({})

// 可变轮次列表（从 props.maxRoundNumbers 初始化，用户可动态增减）
const availableRoundNumbers = ref<number[]>(
  Array.from({ length: props.maxRoundNumbers }, (_, i) => i + 1)
)

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
}

// 所有轮次标签（包括最后一轮）
const allRoundTabs = computed(() => {
  return [...availableRoundNumbers.value, -1]
})

// === 统一模式方法 ===
function toggleRoundNumber(rn: number) {
  const idx = roundNumbers.value.indexOf(rn)
  if (idx >= 0) {
    roundNumbers.value.splice(idx, 1)
  } else {
    roundNumbers.value.push(rn)
  }
}

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
    dimConfigs.value[dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
  }
}

const removeDimension = (index: number) => {
  const dim = selectedDimensions.value[index]
  delete dimConfigs.value[dim.id]
  selectedDimensions.value.splice(index, 1)
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

function isRoundDimensionSelected(rn: number, dim: Dimension) {
  ensureRoundState(rn)
  return roundSelectedDimensions.value[rn].some(d => d.id === dim.id)
}

function toggleRoundDimension(rn: number, dim: Dimension) {
  ensureRoundState(rn)
  if (isRoundDimensionSelected(rn, dim)) {
    roundSelectedDimensions.value[rn] = roundSelectedDimensions.value[rn].filter(d => d.id !== dim.id)
    delete roundDimConfigs.value[rn][dim.id]
  } else {
    roundSelectedDimensions.value[rn].push(dim)
    roundDimConfigs.value[rn][dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
  }
}

function getRoundSelectedDimensions(rn: number): Dimension[] {
  ensureRoundState(rn)
  return roundSelectedDimensions.value[rn]
}

function removeRoundDimension(rn: number, index: number) {
  ensureRoundState(rn)
  const dim = roundSelectedDimensions.value[rn][index]
  delete roundDimConfigs.value[rn][dim.id]
  roundSelectedDimensions.value[rn].splice(index, 1)
}

function copyFromRound(_rn: number) {
  showCopySource.value = true
  const otherRounds = allRoundTabs.value.filter(r => r !== activeRoundTab.value)
  if (otherRounds.length > 0) {
    copySourceRound.value = otherRounds[0]
  }
}

// 复制源轮次的维度和配置到目标轮次（提取公共逻辑，消除重复）
function copyRoundState(srcRn: number, dstRn: number) {
  ensureRoundState(srcRn)
  ensureRoundState(dstRn)
  roundSelectedDimensions.value[dstRn] = roundSelectedDimensions.value[srcRn].map(d => ({ ...d }))
  roundDimConfigs.value[dstRn] = {}
  for (const key in roundDimConfigs.value[srcRn]) {
    roundDimConfigs.value[dstRn][key] = { ...roundDimConfigs.value[srcRn][key] }
  }
}

function doCopyFromRound() {
  copyRoundState(copySourceRound.value, activeRoundTab.value)
  showCopySource.value = false
}

function clearRound(rn: number) {
  ensureRoundState(rn)
  roundSelectedDimensions.value[rn] = []
  roundDimConfigs.value[rn] = {}
}

function applyToAllRounds(srcRn: number) {
  ensureRoundState(srcRn)
  for (const rn of allRoundTabs.value) {
    if (rn === srcRn) continue
    copyRoundState(srcRn, rn)
  }
}

// 切换到逐轮设置时初始化各轮次状态
watch(roundMode, (newMode) => {
  if (newMode === ROUND_MODE.PER_ROUND) {
    for (const rn of allRoundTabs.value) {
      ensureRoundState(rn)
    }
  }
  if (newMode !== ROUND_MODE.PER_ROUND) {
    showCopySource.value = false
  }
})

// === 多轮整体评估维度方法 ===
const isMultiDimensionSelected = (dim: Dimension) => {
  return multiSelectedDimensions.value.some(d => d.id === dim.id)
}

const toggleMultiDimension = (dim: Dimension) => {
  if (isMultiDimensionSelected(dim)) {
    multiSelectedDimensions.value = multiSelectedDimensions.value.filter(d => d.id !== dim.id)
    delete multiDimConfigs.value[dim.id]
  } else {
    multiSelectedDimensions.value.push(dim)
    multiDimConfigs.value[dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
  }
}

const removeMultiDimension = (index: number) => {
  const dim = multiSelectedDimensions.value[index]
  delete multiDimConfigs.value[dim.id]
  multiSelectedDimensions.value.splice(index, 1)
}

// 将后端维度对象转换为前端 Dimension 接口（提取公共逻辑，消除两处重复映射）
function toDimension(d: any): Dimension {
  return {
    id: d.id?.toString() || d.dimension_id?.toString() || '',
    name: d.name || d.dimension_name || '',
    description: d.description
  }
}

async function loadDimensions() {
  try {
    const dims = props.algorithmType
      ? await fetchDimensionsByAlgorithmType(props.algorithmType)
      : await fetchAllDimensions({ forceRefresh: true })
    availableDimensions.value = dims.map(toDimension)
  } catch (error) {
    console.error('加载评价维度失败:', error)
    availableDimensions.value = []
  }
}

// 将维度数组转换为带权重和阈值的配置对象（提取公共逻辑，消除三处重复）
function buildDimensionConfigs(
  dims: Dimension[],
  configs: Record<string, { weight: number; threshold: number }>
): Array<{id: string; name: string; weight: number; threshold: number}> {
  return dims.map(dim => ({
    id: dim.id,
    name: dim.name,
    weight: configs[dim.id]?.weight ?? DEFAULT_WEIGHT,
    threshold: configs[dim.id]?.threshold ?? DEFAULT_THRESHOLD
  }))
}

function handleConfirm() {
  const multiDimensions = buildDimensionConfigs(multiSelectedDimensions.value, multiDimConfigs.value)

  if (roundMode.value === ROUND_MODE.PER_ROUND) {
    const roundDimensions: Record<number, Array<{id: string; name: string; weight: number; threshold: number}>> = {}
    for (const rn of allRoundTabs.value) {
      ensureRoundState(rn)
      roundDimensions[rn] = buildDimensionConfigs(
        roundSelectedDimensions.value[rn],
        roundDimConfigs.value[rn]
      )
    }
    emit('confirm', {
      dimensions: [],
      testType: props.testType,
      roundMode: ROUND_MODE.PER_ROUND,
      roundNumbers: [],
      roundDimensions,
      multiDimensions
    })
  } else {
    const dimensions = buildDimensionConfigs(selectedDimensions.value, dimConfigs.value)
    emit('confirm', {
      dimensions,
      testType: props.testType,
      roundMode: roundMode.value,
      roundNumbers: roundNumbers.value,
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

/* 逐轮设置模式样式 */
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

.level-hint {
  font-size: 11px;
  color: #999;
  margin-left: 24px;
  margin-top: 8px;
}

.mode-hint {
  font-size: 11px;
  color: #f59e0b;
  margin-top: 8px;
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
