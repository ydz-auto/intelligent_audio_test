<template>
  <div class="round-evaluation-editor">
    <!-- 过滤提示 -->
    <div v-if="algorithmType && filteredDimensions.length > 0" class="eval-filter-hint">
      <i class="fas fa-filter"></i>
      已根据算法类型「{{ algorithmType }}」过滤可用维度
    </div>

    <!-- 搜索工具栏 -->
    <div class="eval-toolbar">
      <div class="eval-search-box">
        <i class="fas fa-search"></i>
        <input
          type="text"
          v-model="searchQuery"
          placeholder="搜索评估维度"
          class="eval-search-input"
        />
      </div>
      <span class="eval-dim-count">已选 {{ localDimensions.length }} 项</span>
    </div>

    <!-- 维度徽章（按主/子层级分组，默认收起子维度） -->
    <div v-if="cloudGroups.length > 0" class="eval-chip-groups">
      <div v-for="(group, gi) in cloudGroups" :key="gi" class="eval-chip-group">
        <div
          class="eval-chip eval-chip-main"
          :class="{ active: isDimSelected(group.main) }"
          @click="toggleMain(group)"
        >
          <i :class="isDimSelected(group.main) ? 'fas fa-check' : 'fas fa-plus'"></i>
          {{ group.main.name }}
          <span class="eval-badge eval-badge-main">主</span>
          <span
            v-if="group.children.length > 0"
            class="eval-expand-btn"
            :class="{ expanded: isGroupExpanded(group.main) }"
            :title="isGroupExpanded(group.main) ? '收起子维度' : '展开子维度'"
            @click.stop="toggleExpand(group.main)"
          >
            <i :class="isGroupExpanded(group.main) ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
            <span class="eval-sub-count">{{ group.children.length }}</span>
          </span>
        </div>
        <div v-if="group.children.length > 0 && isGroupExpanded(group.main)" class="eval-chip-subs">
          <div
            v-for="dim in group.children"
            :key="dim.id"
            class="eval-chip eval-chip-sub"
            :class="{ active: isDimSelected(dim) }"
            @click="toggleDim(dim)"
          >
            <i :class="isDimSelected(dim) ? 'fas fa-check' : 'fas fa-plus'"></i>
            {{ dim.name }}
            <span class="eval-badge eval-badge-sub">子</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="eval-empty">
      <i class="fas fa-info-circle"></i>
      {{ searchQuery ? '没有匹配的评估维度' : (algorithmType ? '暂无可用维度（当前算法类型无关联维度）' : '暂无可用维度') }}
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
import type { DimensionCloudGroup } from '../../DimensionCloud.vue'

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

// ---- 搜索 ----
const searchQuery = ref('')

// ---- 主/子层级分组（与批量评估维度设置的分组逻辑一致） ----
const getParentId = (dim: any): string | number | null =>
  dim?.parentDimensionId ?? dim?.parent_dimension_id ?? null

function buildCloudGroups(keyword: string): DimensionCloudGroup[] {
  const dims = filteredDimensions.value
  const kw = keyword.trim().toLowerCase()

  const matches = (d: any): boolean => {
    if (!kw) return true
    return String(d?.name || '').toLowerCase().includes(kw) ||
      String(d?.description || '').toLowerCase().includes(kw) ||
      String(d?.keywords || '').toLowerCase().includes(kw)
  }

  const matchedIds = new Set<string>()
  dims.forEach(d => { if (matches(d)) matchedIds.add(String(d.id)) })

  // 父子聚合：子维度命中带父维度；主维度命中整组展示（非搜索时仅展示命中的子维度）
  const visibleIds = new Set<string>()
  dims.forEach(d => {
    const pid = getParentId(d)
    if (!pid) {
      if (matchedIds.has(String(d.id))) {
        visibleIds.add(String(d.id))
        dims.forEach(c => {
          if (String(getParentId(c)) === String(d.id) && (kw || matchedIds.has(String(c.id)))) {
            visibleIds.add(String(c.id))
          }
        })
      }
    } else if (matchedIds.has(String(d.id))) {
      visibleIds.add(String(d.id))
      visibleIds.add(String(pid))
    }
  })

  const visible = dims.filter(d => visibleIds.has(String(d.id)))
  const mainDims = visible.filter(d => !getParentId(d))
  const childrenMap = new Map<string, any[]>()
  visible.forEach(d => {
    const pid = getParentId(d)
    if (!pid) return
    const key = String(pid)
    if (!childrenMap.has(key)) childrenMap.set(key, [])
    childrenMap.get(key)!.push(d)
  })

  const groups: DimensionCloudGroup[] = []
  mainDims.forEach(m => {
    const children = childrenMap.get(String(m.id)) || []
    groups.push({ main: m, children })
  })
  return groups
}

const cloudGroups = computed(() => buildCloudGroups(searchQuery.value))

// ---- 子维度展开/收起（默认收起，搜索时自动展开） ----
const expandedMainIds = ref<Set<string>>(new Set())

function isGroupExpanded(main: any): boolean {
  if (searchQuery.value.trim()) return true
  return expandedMainIds.value.has(String(main.id))
}

function toggleExpand(main: any) {
  const id = String(main.id)
  const next = new Set(expandedMainIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedMainIds.value = next
}

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
    localDimensions.value.push(makeDimConfig(dim))
  }
  emitUpdate()
}

// 勾选主维度：自动勾选/取消其所有子维度
function toggleMain(group: DimensionCloudGroup) {
  const main = group.main
  const children = group.children || []
  const ids = new Set([String(main.id), ...children.map(c => String(c.id))])
  const mainSelected = localDimensions.value.some(d => String(d.id) === String(main.id))
  if (mainSelected) {
    // 主维度已选 → 连同所有子维度一起取消
    localDimensions.value = localDimensions.value.filter(d => !ids.has(String(d.id)))
  } else {
    // 勾选主维度 → 主维度 + 所有子维度一并选中（已选过的跳过）
    const existingIds = new Set(localDimensions.value.map(d => String(d.id)))
    const toAdd: DimensionConfig[] = []
    for (const dim of [main, ...children]) {
      if (!existingIds.has(String(dim.id))) {
        toAdd.push(makeDimConfig(dim))
        existingIds.add(String(dim.id))
      }
    }
    localDimensions.value.push(...toAdd)
  }
  emitUpdate()
}

function makeDimConfig(dim: Dimension): DimensionConfig {
  const isLlm = isLlmJudgeDim(dim)
  return {
    id: dim.id,
    name: dim.name,
    weight: dim.weight ?? 50,
    threshold: isLlm ? 0 : (80),
    ...(isLlm ? { llmJudgeConfig: { model: 'gpt-4', promptTemplate: 'default' } } : {}),
  } as DimensionConfig
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

/* 搜索工具栏 */
.eval-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.eval-search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 320px;
  padding: 6px 12px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  background: var(--background-primary, #fff);
  transition: border-color 0.2s;
}
.eval-search-box:focus-within {
  border-color: var(--primary-color, #ff6a00);
}
.eval-search-box i {
  color: var(--text-light, #999);
  font-size: 12px;
}
.eval-search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  color: var(--text-primary, #333);
  background: transparent;
}
.eval-search-input::placeholder {
  color: var(--text-light, #aaa);
}
.eval-dim-count {
  font-size: 12px;
  color: var(--text-light, #999);
  white-space: nowrap;
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

/* 维度徽章：按主/子层级分组，流式换行 */
.eval-chip-groups {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.eval-chip-group {
  display: contents;
}
.eval-chip-subs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-left: 2px;
}

/* 主维度徽章 */
.eval-chip-main {
  background: rgba(255, 106, 0, 0.08);
  border-color: rgba(255, 106, 0, 0.4);
  color: #e85d04;
  font-weight: 600;
}
.eval-chip-main:hover {
  background: rgba(255, 106, 0, 0.14);
  border-color: var(--primary-color, #ff6a00);
  color: #e85d04;
}
.eval-chip-main.active {
  background: var(--primary-color, #ff6a00);
  border-color: var(--primary-color, #ff6a00);
  color: #fff;
}
.eval-chip-main.active:hover {
  background: var(--primary-dark, #e05500);
  color: #fff;
}

/* 主/子徽标 */
.eval-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 12px;
  height: 15px;
  padding: 0 3px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 3px;
  flex-shrink: 0;
}
.eval-badge-main {
  background: var(--primary-color, #ff6a00);
  color: #fff;
}
.eval-chip-main.active .eval-badge-main {
  background: #fff;
  color: var(--primary-color, #ff6a00);
}
.eval-badge-sub {
  background: rgba(255, 106, 0, 0.12);
  color: #e85d04;
  border: 1px solid rgba(255, 106, 0, 0.3);
}

/* 子维度展开/收起按钮 */
.eval-expand-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 2px;
  color: rgba(255, 106, 0, 0.7);
  border-radius: 6px;
  flex-shrink: 0;
  transition: all 0.2s;
}
.eval-expand-btn:hover {
  color: var(--primary-color, #ff6a00);
  background: rgba(255, 106, 0, 0.1);
}
.eval-expand-btn.expanded {
  color: var(--primary-color, #ff6a00);
}
.eval-chip-main.active .eval-expand-btn {
  color: #fff;
}

/* 主维度组内子维度数量角标 */
.eval-sub-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: rgba(255, 106, 0, 0.12);
  color: #e85d04;
  font-size: 10px;
  font-weight: 600;
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
