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

      <!-- 维度徽章（按主/子层级分组展示） -->
      <div v-if="cloudGroups.length > 0" class="eval-chip-groups">
        <div v-for="(group, gi) in cloudGroups" :key="gi" class="eval-chip-group">
          <template v-if="group.main">
            <div
              class="eval-chip eval-chip-main"
              :class="{ active: isDimSelected(group.main) }"
              :title="dimTitle(group.main)"
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
              <i v-if="(group.main as any).requiresAudio" class="fas fa-music" style="margin-left: 2px; font-size: 9px;"></i>
            </div>
            <div v-if="group.children.length > 0 && isGroupExpanded(group.main)" class="eval-chip-subs">
              <div
                v-for="dim in group.children"
                :key="dim.id"
                class="eval-chip eval-chip-sub"
                :class="{ active: isDimSelected(dim) }"
                :title="dimTitle(dim)"
                @click="toggleDim(dim)"
              >
                <i :class="isDimSelected(dim) ? 'fas fa-check' : 'fas fa-plus'"></i>
                {{ dim.name }}
                <span class="eval-badge eval-badge-sub">子</span>
                <i v-if="(dim as any).requiresAudio" class="fas fa-music" style="margin-left: 2px; font-size: 9px;"></i>
              </div>
            </div>
          </template>
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { DimensionConfig } from './types'
import type { Dimension } from '../../../../shared/types'
import type { DimensionCloudGroup } from '../../DimensionCloud.vue'

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
  // 搜索时自动展开，便于看到命中的子维度
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

function dimTitle(dim: any): string {
  return (dim as any).requiresAudio ? '该维度需要音频文件，将随多轮音频一起上传' : ''
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
    threshold: isLlm ? 0 : 80,
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
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  background: #FFF;
  transition: border-color 0.2s;
}
.eval-search-box:focus-within {
  border-color: #FF6A00;
}
.eval-search-box i {
  color: #999;
  font-size: 12px;
}
.eval-search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  color: #333;
  background: transparent;
}
.eval-search-input::placeholder {
  color: #aaa;
}
.eval-dim-count {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

/* Eval chips：按主/子层级分组，流式换行 */
.eval-chip-groups {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.eval-chip-group {
  display: contents;
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
/* 主维度徽章 */
.eval-chip-main {
  background: rgba(255, 106, 0, 0.08);
  border-color: rgba(255, 106, 0, 0.4);
  color: #e85d04;
  font-weight: 600;
}
.eval-chip-main:hover {
  background: rgba(255, 106, 0, 0.14);
  border-color: #FF6A00;
}
.eval-chip-main.active {
  background: #FF6A00;
  border-color: #FF6A00;
  color: #FFF;
}
/* 子维度徽章（展开后跟随主维度流式展示） */
.eval-chip-subs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: 2px;
}
.eval-chip-sub {
  background: #FFF;
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
  background: #FF6A00;
  color: #FFF;
}
.eval-chip-main .eval-badge-main {
  background: #FFF;
  color: #FF6A00;
}
.eval-badge-sub {
  background: rgba(255, 106, 0, 0.12);
  color: #e85d04;
  border: 1px solid rgba(255, 106, 0, 0.3);
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
  color: #FF6A00;
  background: rgba(255, 106, 0, 0.1);
}
.eval-expand-btn.expanded {
  color: #FF6A00;
}
.eval-chip-main.active .eval-expand-btn {
  color: #FFF;
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
