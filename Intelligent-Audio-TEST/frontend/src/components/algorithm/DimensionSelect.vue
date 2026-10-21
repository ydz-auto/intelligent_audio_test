<template>
  <!-- 评估维度分组单选下拉（INT-1106 对齐 React INT-1030：维度选择按 分组→主维度→子维度 展示）。
       复用 dimension-picker / EvaluationDimensionTable 的主/子分组云口径：主维度「主」徽章 + 子维度数
       角标、子维度「子」徽章 + 树形分支符 └、孤儿子维度带父名提示；分类分组组头 = 分类名 + 可见维度数。
       适配算法配置参数表行级单选项（关联维度、评估映射 target）、用例筛选 facet（clearLabel/triggerLabel）。 -->
  <span ref="rootRef" class="dimension-select">
    <button
      type="button"
      class="dimension-select-trigger form-input-sm"
      :aria-label="ariaLabel"
      :aria-expanded="open"
      @click.stop="toggle"
    >
      <span v-if="triggerLabel" class="ds-trigger-label">{{ triggerLabel }}</span>
      <span class="ds-trigger-value" :class="{ 'is-placeholder': !selected }">{{ triggerText }}</span>
      <i class="fas fa-chevron-down ds-chevron" :class="{ 'is-open': open }"></i>
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="panelRef"
        class="ds-panel"
        :style="{ top: panelStyle.top, left: panelStyle.left, minWidth: panelStyle.minWidth }"
        role="listbox"
        :aria-label="ariaLabel"
      >
        <button
          v-if="clearLabel"
          type="button"
          class="ds-option ds-option-clear"
          :class="{ 'is-selected': modelValue === '' }"
          @click="select('')"
        >
          <span class="ds-option-label">{{ clearLabel }}</span>
        </button>

        <p v-if="sections.length === 0" class="ds-empty">暂无可用维度</p>

        <template v-else>
          <div v-for="section in sections" :key="section.key" class="ds-section">
            <div class="ds-section-header">
              <i class="fas fa-folder ds-section-icon"></i>
              <span class="ds-section-name">{{ section.category?.name || '未分类' }}</span>
              <span class="ds-section-count">{{ sectionCount(section) }}</span>
            </div>

            <template v-for="(group, groupIndex) in section.groups" :key="groupIndex">
              <template v-if="group.main">
                <button
                  type="button"
                  class="ds-option ds-option-main"
                  :class="{ 'is-selected': getValueFn(group.main) === modelValue }"
                  @click="select(getValueFn(group.main))"
                >
                  <span class="ds-option-label">{{ group.main.name }}</span>
                  <span class="ds-badge ds-badge-main">主</span>
                  <span v-if="group.children.length > 0" class="ds-count-badge">{{ group.children.length }}</span>
                </button>
                <button
                  v-for="child in group.children"
                  :key="`${getValueFn(child)}-${child.id}`"
                  type="button"
                  class="ds-option ds-option-sub"
                  :class="{ 'is-selected': getValueFn(child) === modelValue }"
                  @click="select(getValueFn(child))"
                >
                  <span class="ds-option-branch">└</span>
                  <span class="ds-option-label">{{ child.name }}</span>
                  <span class="ds-badge ds-badge-sub">子</span>
                </button>
              </template>
              <template v-else>
                <button
                  v-for="child in group.children"
                  :key="`${getValueFn(child)}-${child.id}`"
                  type="button"
                  class="ds-option ds-option-sub"
                  :class="{ 'is-selected': getValueFn(child) === modelValue }"
                  @click="select(getValueFn(child))"
                >
                  <span class="ds-option-branch">└</span>
                  <span class="ds-option-label">{{ child.name }}</span>
                  <span class="ds-badge ds-badge-sub">子</span>
                  <span v-if="group.orphanParentName" class="ds-orphan-hint">（{{ group.orphanParentName }}）</span>
                </button>
              </template>
            </template>
          </div>
        </template>
      </div>
    </Teleport>
  </span>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch, onBeforeUnmount } from 'vue'
import type { Dimension, EvaluationCategory } from '@/domain'

/** 维度云分组：主维度 + 其子维度；main 为 null 表示父维度不在候选集（孤儿子维度） */
interface CloudGroup {
  main: Dimension | null
  children: Dimension[]
  /** 孤儿子维度时展示的父维度名 */
  orphanParentName: string
}

/** 分类分组节：分类（未知/未分类为 null）+ 该分类下的主/子分组云 */
interface CategorySection {
  key: string
  category: EvaluationCategory | null
  groups: CloudGroup[]
}

const props = defineProps<{
  /** 评估维度全量（含子维度；分组/主维度/子维度 展示） */
  dimensions?: Dimension[]
  /** 评估维度分类（分类分组组头；不传=单节整片主/子分组云） */
  categories?: EvaluationCategory[]
  /** 当前选中值（由 getValueFn 提取） */
  modelValue?: string
  /** 维度 → 选项值的提取器（关联维度/筛选用 id，评估映射 target 用 name） */
  getValue?: (dimension: Dimension) => string
  /** 空值占位；值为空且未选中时显示。未匹配选项的存量值回退显示原值（数据保全） */
  placeholder?: string
  /** 可清除的单选（筛选场景）：下拉顶部「全部」项，选中即清空（value=''） */
  clearLabel?: string
  /** 触发器前缀标签（筛选 chip 形态：如「评估维度」+ 当前值） */
  triggerLabel?: string
  ariaLabel?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

/** 维度 → 选项值提取器（未传入时按 id） */
const getValueFn = computed<(dimension: Dimension) => string>(
  () => props.getValue || ((d: Dimension) => String(d.id))
)

/** 构建主/子分组的维度云（父维度不在候选集的子维度作「孤儿子维度」兜底） */
function buildCloudGroups(dims: Dimension[]): CloudGroup[] {
  const byId = new Map<string, Dimension>(dims.map(d => [String(d.id), d]))
  const mainDims = dims.filter(d => !d.parentDimensionId)
  const childrenMap = new Map<string, Dimension[]>()
  dims.forEach(d => {
    if (!d.parentDimensionId) return
    const key = String(d.parentDimensionId)
    childrenMap.set(key, [...(childrenMap.get(key) ?? []), d])
  })

  const groups: CloudGroup[] = []
  const groupedChildIds = new Set<string>()
  mainDims.forEach(main => {
    const children = childrenMap.get(String(main.id)) ?? []
    groups.push({ main, children, orphanParentName: '' })
    children.forEach(c => groupedChildIds.add(String(c.id)))
  })
  dims.forEach(d => {
    const pid = d.parentDimensionId
    if (pid && !groupedChildIds.has(String(d.id))) {
      groups.push({
        main: null,
        children: [d],
        orphanParentName: byId.get(String(pid))?.name ?? '',
      })
    }
  })
  return groups
}

/** 按分类聚合主/子分组云（分类顺序照 categories 数组；categoryId 为空/未知 → 未分类） */
function groupByCategory(groups: CloudGroup[], categories: EvaluationCategory[]): CategorySection[] {
  if (categories.length === 0) return [{ key: 'all', category: null, groups }]
  const byCat = new Map<string, CloudGroup[]>()
  const uncategorized: CloudGroup[] = []
  for (const group of groups) {
    const catId = group.main ? group.main.categoryId : (group.children[0]?.categoryId ?? null)
    if (catId == null) uncategorized.push(group)
    else {
      const key = String(catId)
      if (!byCat.has(key)) byCat.set(key, [])
      byCat.get(key)!.push(group)
    }
  }
  const result: CategorySection[] = []
  for (const cat of categories) {
    const items = byCat.get(String(cat.id))
    if (items && items.length > 0) result.push({ key: String(cat.id), category: cat, groups: items })
  }
  for (const [key, items] of byCat.entries()) {
    if (!result.some(r => r.key === key)) result.push({ key, category: null, groups: items })
  }
  if (uncategorized.length > 0) result.push({ key: 'uncategorized', category: null, groups: uncategorized })
  return result
}

const sections = computed<CategorySection[]>(() =>
  groupByCategory(buildCloudGroups(props.dimensions ?? []), props.categories ?? [])
)

/** 分类节可见维度数（主维度 + 子维度） */
function sectionCount(section: CategorySection): number {
  return section.groups.reduce((sum, g) => sum + g.children.length + (g.main ? 1 : 0), 0)
}

const selected = computed<Dimension | undefined>(() =>
  (props.dimensions ?? []).find(d => getValueFn.value(d) === props.modelValue)
)

const triggerText = computed(() => {
  const s = selected.value
  if (s) return s.parentDimensionId ? `└ ${s.name}` : s.name
  return props.modelValue !== '' && props.modelValue !== undefined
    ? props.modelValue
    : (props.placeholder ?? '选择评估维度')
})

/* ===== 下拉面板（teleport fixed 定位，照 ColumnFilter popover 口径） ===== */
const open = ref(false)
const rootRef = ref<HTMLElement>()
const panelRef = ref<HTMLElement>()
const panelStyle = reactive({ top: '0px', left: '0px', minWidth: '260px' })

function toggle() {
  if (open.value) {
    open.value = false
    return
  }
  const r = rootRef.value?.getBoundingClientRect()
  if (r) {
    const w = 260
    // 底部越界时向上展开（估算面板高 320px）
    let top = r.bottom + 4
    if (top + 320 > window.innerHeight) top = Math.max(4, r.top - 320 - 4)
    panelStyle.top = `${Math.round(top)}px`
    panelStyle.left = `${Math.max(8, Math.min(Math.round(r.left), window.innerWidth - w - 8))}px`
    panelStyle.minWidth = `${Math.max(Math.round(r.width), w)}px`
  }
  open.value = true
}

function select(value: string) {
  emit('update:modelValue', value)
  open.value = false
}

// 点击面板/触发器外部关闭（mousedown 不受模态窗 click.stop 影响）
function onDocMousedown(e: MouseEvent) {
  const target = e.target as Node
  if (panelRef.value?.contains(target) || rootRef.value?.contains(target)) return
  open.value = false
}

function onScrollOrResize() {
  open.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}

watch(open, (v) => {
  if (v) {
    document.addEventListener('mousedown', onDocMousedown)
    document.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
    document.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('mousedown', onDocMousedown)
    document.removeEventListener('scroll', onScrollOrResize, true)
    window.removeEventListener('resize', onScrollOrResize)
    document.removeEventListener('keydown', onKeydown)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMousedown)
  document.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.dimension-select {
  display: inline-flex;
  vertical-align: middle;
  width: 100%;
}

.dimension-select-trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  width: 100%;
  text-align: left;
  font-family: inherit;
  background: var(--background);
  cursor: pointer;
}

.ds-trigger-label {
  color: var(--muted-foreground);
  flex-shrink: 0;
}

.ds-trigger-value {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ds-trigger-value.is-placeholder {
  color: var(--muted-foreground);
}

.ds-chevron {
  font-size: 11px;
  color: var(--muted-foreground);
  flex-shrink: 0;
  transition: transform var(--transition-fast);
}

.ds-chevron.is-open {
  transform: rotate(180deg);
}

.ds-panel {
  position: fixed;
  z-index: var(--z-index-popover);
  box-sizing: border-box;
  max-height: 320px;
  overflow-y: auto;
  padding: var(--spacing-xs);
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  box-shadow: var(--shadow-md);
}

.ds-section + .ds-section {
  border-top: 1px solid var(--border);
  margin-top: var(--spacing-xs);
  padding-top: var(--spacing-xs);
}

.ds-section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--muted-foreground);
}

.ds-section-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.ds-section-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ds-section-count {
  margin-left: auto;
  flex-shrink: 0;
  padding: 0 var(--spacing-xs);
  border-radius: var(--radius-pill);
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 10px;
  line-height: 18px;
  font-variant-numeric: tabular-nums;
}

.ds-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  width: 100%;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: none;
  border-radius: var(--radius-tag);
  background: transparent;
  color: var(--foreground);
  font-size: var(--font-size-sm);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.ds-option:hover {
  background: var(--accent);
}

.ds-option.is-selected {
  background: var(--accent);
}

.ds-option-main .ds-option-label {
  font-weight: var(--font-weight-medium);
}

.ds-option-sub .ds-option-label {
  color: var(--foreground);
}

.ds-option-branch {
  color: var(--muted-foreground);
  font-family: monospace;
  font-size: 10px;
  flex-shrink: 0;
}

.ds-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: var(--font-weight-semibold);
  flex-shrink: 0;
}

.ds-badge-main {
  background: color-mix(in srgb, var(--primary) 20%, transparent);
  color: var(--primary);
}

.ds-badge-sub {
  background: var(--muted);
  color: var(--muted-foreground);
  border: 1px solid var(--border);
}

.ds-count-badge {
  margin-left: auto;
  padding: 0 var(--spacing-xs);
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--primary) 15%, transparent);
  color: var(--primary);
  font-size: 10px;
  line-height: 16px;
  font-weight: var(--font-weight-semibold);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.ds-orphan-hint {
  color: var(--muted-foreground);
  font-size: var(--font-size-xs);
}

.ds-empty {
  margin: 0;
  padding: var(--spacing-md);
  text-align: center;
  color: var(--muted-foreground);
  font-size: var(--font-size-sm);
}
</style>
