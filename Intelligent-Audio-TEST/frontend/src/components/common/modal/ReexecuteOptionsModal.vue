<template>
  <div class="reexecute-select">
    <p class="reexecute-title">{{ content }}</p>

    <!-- 第 1 步：范围选择（全部 / 仅失败用例 / 手动选择） -->
    <div class="reexecute-options">
      <div
        class="reexecute-option"
        :class="{ active: scope === SCOPE_ALL }"
        @click="scope = SCOPE_ALL"
      >
        <div class="option-radio"><div class="radio-circle"></div></div>
        <div class="option-content">
          <span class="option-title">{{ scopeAllLabel }}</span>
          <span class="option-desc">{{ isReevaluate ? '对该任务下所有执行成功的用例进行重新评估' : '重置并重新执行该任务的全部用例' }}</span>
        </div>
      </div>
      <div
        class="reexecute-option"
        :class="{ active: scope === SCOPE_FAILED }"
        @click="scope = SCOPE_FAILED"
      >
        <div class="option-radio"><div class="radio-circle"></div></div>
        <div class="option-content">
          <span class="option-title">仅失败用例</span>
          <span class="option-desc">{{ isReevaluate ? '仅对评估结果为失败的用例进行重新评估' : '仅重新执行执行失败或评估失败的用例' }}</span>
        </div>
      </div>
      <div
        class="reexecute-option"
        :class="{ active: scope === SCOPE_SELECTED }"
        @click="scope = SCOPE_SELECTED"
      >
        <div class="option-radio"><div class="radio-circle"></div></div>
        <div class="option-content">
          <span class="option-title">手动选择用例</span>
          <span class="option-desc">从本任务已执行的用例集中勾选（支持按标签/分组过滤）</span>
        </div>
      </div>
    </div>

    <!-- 手动选择：复用 E2E 页勾选式用例选择交互（checkbox 多选 + 全选 + 标签/分组过滤），
         数据源为本任务已执行的用例集（task_cases），不是全库用例 -->
    <div v-if="scope === SCOPE_SELECTED" class="case-selector">
      <div class="case-selector-toolbar">
        <label class="select-all-label">
          <input
            type="checkbox"
            class="checkbox-input"
            :checked="isAllCasesSelected"
            @change="toggleSelectAllCases"
          />
          全选
        </label>
        <select v-model="caseFilter" class="form-input filter-select-input">
          <option value="all">全部标签/分组</option>
          <option v-for="name in caseFilterOptions" :key="name" :value="name">{{ name }}</option>
        </select>
      </div>
      <div class="case-list">
        <div v-if="filteredCases.length === 0" class="case-list-empty">
          <i :class="loadingCases ? 'fas fa-spinner fa-spin' : 'fas fa-inbox'"></i>
          <span>{{ loadingCases ? '正在加载本任务用例...' : '本任务暂无已执行用例' }}</span>
        </div>
        <label
          v-for="tc in filteredCases"
          :key="tc.caseId"
          class="case-item"
        >
          <input
            type="checkbox"
            class="checkbox-input"
            :checked="selectedCaseIdSet.has(String(tc.caseId))"
            @change="toggleCaseSelection(tc.caseId)"
          />
          <span class="case-item-name" :title="tc.name">{{ tc.name }}</span>
          <span class="case-item-meta">{{ tc.groupName || '' }}</span>
        </label>
      </div>
    </div>

    <!-- 第 2 步（仅重新评估）：维度勾选（默认全选） -->
    <div v-if="isReevaluate && dimensionOptions.length > 0" class="dimension-selector">
      <div class="selector-section-title">
        <i class="fas fa-layer-group"></i> 评估维度（默认全选）
      </div>
      <div class="dimension-grid">
        <label
          v-for="dim in dimensionOptions"
          :key="dim.id"
          class="dimension-item"
        >
          <input
            type="checkbox"
            class="checkbox-input"
            :checked="selectedDimensionIdSet.has(Number(dim.id))"
            @change="toggleDimensionSelection(dim.id)"
          />
          <span class="dimension-item-name" :title="dim.name">{{ dim.name }}</span>
        </label>
      </div>
    </div>

    <!-- 底部：选中计数 + 确认 -->
    <div class="reexecute-actions">
      <button class="btn btn-secondary" @click="handleCancel">取消</button>
      <button
        class="btn btn-primary"
        :disabled="!canConfirm"
        @click="handleConfirm"
      >
        确认{{ confirmCountText }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { tasksPort } from '../../../composables/task/tasksPort'
import { evaluationPort } from '../../../composables/evaluation/evaluationPort'

/**
 * INT-302：重执行/重评估范围选择模态窗。
 *
 * 两段式：
 * - 第 1 步选范围（全部/仅失败用例/手动选择）；手动选择复用 E2E 页勾选式
 *   用例交互（checkbox + 全选 + 标签/分组过滤），数据源为本任务已执行的
 *   用例集（任务详情 task.cases），不是全库用例；
 * - 重新评估时第 2 步加维度勾选（全库维度列表多选，默认全选）。
 *
 * 确认后 emit('confirm', {mode, caseIds, dimensionIds})，由调用方发起重执行/
 * 重评估请求；底部显示选中计数。
 */

const SCOPE_ALL = 'all'
const SCOPE_FAILED = 'failed_only'
const SCOPE_SELECTED = 'selected'

const props = defineProps({
  modalId: { type: String, required: true },
  content: { type: String, default: '请选择执行范围' },
  /** 'retry' = 重新执行（无维度步）；'reevaluate' = 重新评估（加维度勾选） */
  actionType: { type: String, default: 'retry' },
  taskId: { type: [String, Number], required: true }
})

const emit = defineEmits(['close', 'confirm'])

const scope = ref<string>(SCOPE_ALL)
const taskCases = ref<{ caseId: string; name: string; groupName?: string; tags?: string[] }[]>([])
const selectedCaseIds = ref<(string | number)[]>([])
const dimensionOptions = ref<{ id: number; name: string }[]>([])
const selectedDimensionIds = ref<number[]>([])
const caseFilter = ref<string>('all')
const loadingCases = ref(false)

const isReevaluate = computed(() => props.actionType === 'reevaluate')
const scopeAllLabel = computed(() => (isReevaluate.value ? '全部用例' : '全部用例'))

// 标签/分组过滤选项（标签优先，无标签回退分组名；对齐 E2E 页过滤交互）
const caseFilterOptions = computed(() => {
  const names = new Set<string>()
  taskCases.value.forEach(tc => {
    (tc.tags || []).forEach(t => names.add(t))
    if (tc.groupName) names.add(tc.groupName)
  })
  return Array.from(names).sort()
})

const filteredCases = computed(() => {
  if (caseFilter.value === 'all') return taskCases.value
  return taskCases.value.filter(tc =>
    (tc.tags || []).includes(caseFilter.value) || tc.groupName === caseFilter.value)
})

const selectedCaseIdSet = computed(() => new Set(selectedCaseIds.value.map(String)))
const selectedDimensionIdSet = computed(() => new Set(selectedDimensionIds.value))

const isAllCasesSelected = computed(() =>
  filteredCases.value.length > 0 &&
  filteredCases.value.every(tc => selectedCaseIdSet.value.has(String(tc.caseId))))

const canConfirm = computed(() => {
  if (scope.value !== SCOPE_SELECTED) return true
  return selectedCaseIds.value.length > 0
})

const confirmCountText = computed(() => {
  if (scope.value === SCOPE_SELECTED) {
    const n = selectedCaseIds.value.length
    return `（已选 ${n} 个用例${isReevaluate.value && selectedDimensionIds.value.length < dimensionOptions.value.length ? ` / ${selectedDimensionIds.value.length} 个维度` : ''}）`
  }
  return ''
})

const toggleCaseSelection = (caseId: string | number) => {
  const key = String(caseId)
  const idx = selectedCaseIds.value.findIndex(id => String(id) === key)
  if (idx > -1) {
    selectedCaseIds.value.splice(idx, 1)
  } else {
    selectedCaseIds.value.push(caseId)
  }
}

const toggleSelectAllCases = () => {
  if (isAllCasesSelected.value) {
    const removeSet = new Set(filteredCases.value.map(tc => String(tc.caseId)))
    selectedCaseIds.value = selectedCaseIds.value.filter(id => !removeSet.has(String(id)))
  } else {
    filteredCases.value.forEach(tc => {
      if (!selectedCaseIdSet.value.has(String(tc.caseId))) {
        selectedCaseIds.value.push(tc.caseId)
      }
    })
  }
}

const toggleDimensionSelection = (dimId: number | string) => {
  const key = Number(dimId)
  const idx = selectedDimensionIds.value.indexOf(key)
  if (idx > -1) {
    selectedDimensionIds.value.splice(idx, 1)
  } else {
    selectedDimensionIds.value.push(key)
  }
}

const handleConfirm = () => {
  if (!canConfirm.value) return
  emit('confirm', {
    mode: scope.value,
    caseIds: scope.value === SCOPE_SELECTED ? [...selectedCaseIds.value] : [],
    // 空数组 = 全选（不过滤），仅显式子集时下发
    dimensionIds: isReevaluate.value
      ? (selectedDimensionIds.value.length === dimensionOptions.value.length ? [] : [...selectedDimensionIds.value])
      : [],
  })
}

const handleCancel = () => {
  emit('close')
}

onMounted(async () => {
  // 数据源为本任务已执行的用例集（task 详情 task.cases），不是全库用例（INT-302）
  loadingCases.value = true
  try {
    const taskData = await tasksPort.getOne(props.taskId) as any
    taskCases.value = (taskData?.cases || []).map((tc: any) => ({
      caseId: tc.caseId,
      name: tc.name,
      groupName: tc.groupName,
      tags: tc.tags || []
    }))
  } catch (e) {
    console.error('[ReexecuteOptionsModal] 加载任务用例失败:', e)
    taskCases.value = []
  } finally {
    loadingCases.value = false
  }

  // 重新评估：加载维度列表（默认全选）
  if (isReevaluate.value) {
    try {
      const res = await evaluationPort.getAll({ page: 1, perPage: 500 }) as any
      const items: any[] = Array.isArray(res?.items) ? res.items : []
      dimensionOptions.value = items
        .filter(d => d?.id && d?.name)
        .map(d => ({ id: Number(d.id), name: d.name }))
      // 默认全选
      selectedDimensionIds.value = dimensionOptions.value.map(d => d.id)
    } catch (e) {
      console.error('[ReexecuteOptionsModal] 加载评估维度失败:', e)
      dimensionOptions.value = []
    }
  }
})
</script>

<style scoped>
.reexecute-select {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.reexecute-title {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  color: var(--foreground);
  text-align: center;
}

.reexecute-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.reexecute-option {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border: 2px solid var(--border);
  border-radius: 10px;
  background-color: var(--background);
  cursor: pointer;
  transition: all 0.2s ease;
}

.reexecute-option:hover {
  border-color: var(--secondary);
  background-color: var(--color-slate-50);
}

.reexecute-option.active {
  border-color: var(--secondary);
  background-color: var(--color-blue-50);
}

.option-radio {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 2px;
}

.radio-circle {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-gray-300);
  border-radius: 50%;
  transition: all 0.2s ease;
}

.reexecute-option:hover .radio-circle {
  border-color: var(--secondary);
}

.reexecute-option.active .radio-circle {
  border-color: var(--secondary);
  background-color: var(--secondary);
  box-shadow: inset 0 0 0 3px var(--background);
}

.option-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--color-gray-700);
}

.reexecute-option.active .option-title {
  color: var(--secondary);
}

.option-desc {
  font-size: 13px;
  color: var(--color-gray-400);
}

/* ===== 用例选择器（复用 E2E 页勾选交互形态） ===== */

.case-selector {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background-color: var(--color-gray-50);
}

.case-selector-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.select-all-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-gray-700);
  cursor: pointer;
}

.filter-select-input {
  height: 32px;
  padding: 0 8px;
  font-size: 13px;
  min-width: 160px;
}

.case-list {
  max-height: 240px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.case-list-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-secondary);
  font-size: 13px;
}

.case-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background-color: var(--background);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.case-item:hover {
  background-color: var(--color-slate-50);
}

.case-item-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.case-item-meta {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.checkbox-input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--secondary);
  flex-shrink: 0;
}

/* ===== 维度选择器 ===== */

.dimension-selector {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background-color: var(--color-gray-50);
}

.selector-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-gray-700);
}

.dimension-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px;
}

.dimension-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background-color: var(--background);
  border: 1px solid var(--border);
  cursor: pointer;
}

.dimension-item:hover {
  background-color: var(--color-slate-50);
}

.dimension-item-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== 底部操作 ===== */

.reexecute-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
</style>
