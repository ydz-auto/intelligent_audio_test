<template>
  <div class="report-context-selector" ref="rootRef">
    <!-- 触发钮（当前上下文名 + 类型 Badge + 箭头；§3.5 报告上下文选择器） -->
    <button
      type="button"
      class="rcs-trigger"
      :class="{ 'rcs-trigger--active': open }"
      @click="toggleOpen"
    >
      <i class="fas fa-file-chart-column rcs-trigger-icon"></i>
      <span v-if="currentLabel" class="rcs-trigger-label">{{ currentLabel }}</span>
      <span v-else class="rcs-trigger-label rcs-trigger-label--placeholder">{{ INPUT_COPY.selectContext }}</span>
      <span v-if="currentBadge" class="rcs-trigger-badge">{{ currentBadge }}</span>
      <i class="fas fa-chevron-up rcs-trigger-chevron" :class="{ 'rcs-trigger-chevron--down': !open }"></i>
    </button>

    <!-- 双列面板（左类型 / 右搜索列表；自下而上弹出） -->
    <div v-if="open" class="rcs-dropdown" ref="dropdownRef">
      <div class="rcs-columns">
        <!-- 左列：上下文类型 -->
        <div class="rcs-types">
          <div class="rcs-column-header">类型</div>
          <div class="rcs-type-list">
            <button
              v-for="type in visibleTypes"
              :key="type.key"
              type="button"
              class="rcs-type-item"
              :class="{ 'rcs-type-item--active': type.key === selectedType }"
              @click="selectedType = type.key"
            >
              {{ type.label }}
            </button>
          </div>
        </div>

        <!-- 右列：搜索 + 报告/任务列表 -->
        <div class="rcs-options">
          <div class="rcs-search">
            <i class="fas fa-magnifying-glass rcs-search-icon"></i>
            <input
              v-model="keyword"
              type="text"
              class="rcs-search-input"
              :placeholder="INPUT_COPY.selectContext"
            />
          </div>
          <div class="rcs-option-list">
            <button
              v-for="opt in filteredOptions"
              :key="opt.id"
              type="button"
              class="rcs-option-item"
              :class="{ 'rcs-option-item--active': opt.id === selectedId }"
              @click="selectOption(opt)"
            >
              <i v-if="opt.id === selectedId" class="fas fa-check rcs-option-check"></i>
              <span class="rcs-option-label">{{ opt.label }}</span>
              <span class="rcs-option-badge">{{ opt.badge }}</span>
            </button>
            <div v-if="!filteredOptions.length" class="rcs-option-empty">{{ INPUT_COPY.noMatch }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { ChatConfig, ReportContextOption, ReportContextType } from '@/domain/model/aiChat'
import { INPUT_COPY, REPORT_CONTEXT_TYPE_BADGES } from '@/domain/constants/aiChat'
import { reportsApi } from '@/infrastructure/api/reportsApi'
import { tasksApi } from '@/infrastructure/api/tasksApi'

const props = defineProps<{
  config: ChatConfig
}>()

const emit = defineEmits<{
  (e: 'select-context', id: string, label: string, type: ReportContextType): void
}>()

/** 上下文类型左列（§3.5：测试报告/对比报告/二次对比/任务；任务组 task:read 权限过滤在权限派生层） */
const CONTEXT_TYPES: Array<{ key: ReportContextType; label: string }> = [
  { key: 'task', label: INPUT_COPY.testReport },
  { key: 'comparison', label: INPUT_COPY.comparisonReport },
  { key: 'secondary_comparison', label: INPUT_COPY.secondaryComparison },
  { key: 'task_context', label: INPUT_COPY.task },
]

const open = ref(false)
const keyword = ref('')
const selectedType = ref<ReportContextType | ''>('task')
const selectedId = ref<string | null>(null)
const options = ref<ReportContextOption[]>([])
const dropdownRef = ref<HTMLElement | null>(null)
const rootRef = ref<HTMLElement | null>(null)

const currentLabel = computed(() => props.config.reportContextLabel ?? '')
const currentBadge = computed(
  () => (props.config.reportContextType ? REPORT_CONTEXT_TYPE_BADGES[props.config.reportContextType] : '')
)

const visibleTypes = computed(() => CONTEXT_TYPES)
const filteredOptions = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return options.value.filter(
    (opt) =>
      (selectedType.value === '' || opt.type === selectedType.value) &&
      (!kw || opt.label.toLowerCase().includes(kw))
  )
})

/**
 * 数据交互（§3.5）：GET /reports（report:read）+ GET /tasks（task:read）联查。
 * 待后端立项（INT-598 方案A：组件树先落、Demo 态整块不渲染）——挂载点由
 * REPORT_CONTEXT_ENABLED 开关控制，开启前不发起请求。
 */
async function loadOptions(): Promise<void> {
  try {
    const [reportPage, taskPage] = await Promise.all([
      reportsApi.getAll({ page: 1, perPage: 100 }),
      tasksApi.getAll({ page: 1, perPage: 100 }),
    ])
    const reportOptions: ReportContextOption[] = (reportPage.items ?? [])
      .filter(
        (r) => r.type === 'task' || r.type === 'comparison' || r.type === 'secondary_comparison'
      )
      .map((r) => ({
        id: String(r.id),
        label: r.name || `报告 #${r.id}`,
        type: r.type as ReportContextType,
        badge: REPORT_CONTEXT_TYPE_BADGES[r.type as ReportContextType] ?? INPUT_COPY.testReport,
      }))
    const taskOptions: ReportContextOption[] = (taskPage.items ?? []).map((t) => ({
      id: `task-${t.id}`,
      label: t.name || `任务 #${t.id}`,
      type: 'task_context' as ReportContextType,
      badge: INPUT_COPY.task,
    }))
    options.value = [...reportOptions, ...taskOptions]
  } catch {
    // 列表加载失败：空态（不杜撰数据）
    options.value = []
  }
}

function toggleOpen(): void {
  open.value = !open.value
  if (open.value && options.value.length === 0) void loadOptions()
}

function selectOption(opt: ReportContextOption): void {
  selectedId.value = opt.id
  emit('select-context', opt.id, opt.label, opt.type)
  open.value = false
}

/** 点击组件根以外才关闭（触发钮/面板内点击不误关——标准 popover 语义） */
function handleDocumentClick(event: MouseEvent): void {
  const root = rootRef.value
  if (!root) return
  if (!root.contains(event.target as Node)) {
    open.value = false
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') open.value = false
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener('click', handleDocumentClick)
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('click', handleDocumentClick)
    document.removeEventListener('keydown', handleKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.report-context-selector {
  position: relative;
}

.rcs-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 15rem;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--foreground);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.rcs-trigger:hover,
.rcs-trigger--active {
  border-color: var(--primary);
}

.rcs-trigger-icon {
  color: var(--muted-foreground);
  font-size: 13px;
}

.rcs-trigger-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rcs-trigger-label--placeholder {
  color: var(--muted-foreground);
}

.rcs-trigger-badge {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted-foreground);
  background: var(--muted);
  border-radius: var(--radius-full);
  padding: 1px 6px;
}

.rcs-trigger-chevron {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted-foreground);
  opacity: 0.6;
}

.rcs-trigger-chevron--down {
  transform: rotate(180deg);
}

/* ===== 双列面板 ===== */
.rcs-dropdown {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  z-index: 120;
  width: 30rem;
  max-width: calc(100vw - 40px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--popover);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.rcs-columns {
  display: grid;
  grid-template-columns: 9.5rem minmax(0, 1fr);
  max-height: 28rem;
}

.rcs-types,
.rcs-options {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.rcs-types {
  border-right: 1px solid var(--border);
}

.rcs-column-header {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted-foreground);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.rcs-type-list,
.rcs-option-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.rcs-type-item {
  display: block;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  font: inherit;
  font-size: 12px;
  color: var(--foreground);
  cursor: pointer;
  text-align: left;
}

.rcs-type-item:hover {
  background: var(--muted);
}

.rcs-type-item--active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  box-shadow: inset 2px 0 0 var(--primary);
}

.rcs-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.rcs-search-icon {
  color: var(--muted-foreground);
  font-size: 12px;
}

.rcs-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 12px;
  color: var(--foreground);
  outline: none;
}

.rcs-option-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  font: inherit;
  font-size: 12px;
  color: var(--foreground);
  cursor: pointer;
  text-align: left;
}

.rcs-option-item:hover {
  background: var(--muted);
}

.rcs-option-item--active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  box-shadow: inset 2px 0 0 var(--primary);
}

.rcs-option-check {
  color: var(--primary);
  font-size: 12px;
}

.rcs-option-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rcs-option-badge {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted-foreground);
  background: var(--muted);
  border-radius: var(--radius-full);
  padding: 1px 6px;
}

.rcs-option-empty {
  padding: 16px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--muted-foreground);
}
</style>
