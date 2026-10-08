<template>
  <div class="badge-filter" :class="{ 'badge-filter--compact': compact }">
    <span v-if="title" class="badge-filter__title">
      <i v-if="icon" :class="icon"></i>
      {{ title }}
    </span>
    <div class="badge-filter__badges">
      <button
        v-if="showAll"
        type="button"
        class="badge-filter__badge"
        :class="{ 'badge-filter__badge--active': isAll }"
        @click="select(ALL_VALUE)"
      >
        {{ allLabel }}
      </button>
      <button
        v-for="opt in visibleOptions"
        :key="String(opt.value)"
        type="button"
        class="badge-filter__badge"
        :class="{ 'badge-filter__badge--active': modelValue === opt.value }"
        @click="select(opt.value)"
      >
        {{ opt.label }}
      </button>
      <button
        v-if="showToggle"
        type="button"
        class="badge-filter__badge badge-filter__toggle"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起' : `更多 (${hiddenCount})` }}
        <i class="fas" :class="expanded ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
      </button>
      <span v-if="effectiveOptions.length === 0" class="badge-filter__empty">暂无可选项</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

export interface BadgeFilterOption {
  value: string | number;
  label: string;
}

const props = withDefaults(defineProps<{
  /** 选项列表（{value,label}[]） */
  options?: BadgeFilterOption[];
  /** 当前选中值（'all' 或具体值） */
  modelValue?: string | number;
  /** 筛选区标题 */
  title?: string;
  /** 标题图标（FontAwesome class） */
  icon?: string;
  /** 是否展示「全部」徽章 */
  showAll?: boolean;
  /** 「全部」徽章文案 */
  allLabel?: string;
  /** 再次点击已选项是否取消（回到全部）；showAll=false 时无效 */
  deselectable?: boolean;
  /** 紧凑模式 */
  compact?: boolean;
  /** 选项过多时折叠：默认只展示 collapsedCount 个 + 「更多」切换 */
  collapsible?: boolean;
  /** 折叠态展示的选项数量 */
  collapsedCount?: number;
}>(), {
  options: () => [],
  modelValue: 'all',
  title: '',
  icon: '',
  showAll: true,
  allLabel: '全部',
  deselectable: true,
  compact: false,
  collapsible: false,
  collapsedCount: 8,
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void;
}>();

const ALL_VALUE = 'all';

/** 剔除选项中的 'all' 占位项（由「全部」徽章承担），避免重复 */
const effectiveOptions = computed<BadgeFilterOption[]>(() =>
  (props.options || []).filter(opt => opt.value !== ALL_VALUE && opt.value !== '')
);

const isAll = computed(() => !props.modelValue || props.modelValue === ALL_VALUE);

// ===== 折叠/展开（选项超过 collapsedCount 时收起多余的，点「更多」展开）=====
const expanded = ref(false);

const showToggle = computed(() =>
  props.collapsible && effectiveOptions.value.length > props.collapsedCount
);

const hiddenCount = computed(() =>
  Math.max(0, effectiveOptions.value.length - props.collapsedCount)
);

const visibleOptions = computed<BadgeFilterOption[]>(() => {
  if (!showToggle.value || expanded.value) return effectiveOptions.value;
  return effectiveOptions.value.slice(0, props.collapsedCount);
});

// 当前选中项被折叠隐藏时自动展开（含收起时仍选中隐藏项的场景），避免「看不见的已选筛选」
watch(
  [expanded, () => props.modelValue],
  ([isExpanded, value]) => {
    if (isExpanded || value === ALL_VALUE) return;
    if (!visibleOptions.value.some(opt => opt.value === value)) {
      expanded.value = true;
    }
  },
  { immediate: true }
);

function select(value: string | number) {
  if (value === ALL_VALUE) {
    emit('update:modelValue', ALL_VALUE);
    return;
  }
  // 单选可取消：再次点击已选项回到「全部」
  if (props.deselectable && props.showAll && props.modelValue === value) {
    emit('update:modelValue', ALL_VALUE);
    return;
  }
  emit('update:modelValue', value);
}
</script>

<style scoped>
/* 徽章样式使用 !important：项目全局 button:not(.btn-icon-only):not(.svg-btn-only):not(.icon-btn-only)
   选择器特异性更高（0,3,1 > 0,2,0），会覆盖 scoped 样式导致边框/背景丢失 */
.badge-filter {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  max-width: 100%;
}

.badge-filter__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #64748b);
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-filter__title i {
  color: var(--primary-color, #ff6a00);
  font-size: 12px;
}

.badge-filter__badges {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.badge-filter__badge {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 6px !important;
  padding: 5px 14px !important;
  border: 1px solid #d0d5dd !important;
  border-radius: 999px !important;
  background: #f8fafc !important;
  color: #475569 !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  line-height: 1.4 !important;
  min-height: 28px !important;
  min-width: 0 !important;
  flex-shrink: 0 !important;
  cursor: pointer !important;
  transition: all 0.2s ease !important;
  white-space: nowrap !important;
  user-select: none !important;
  transform: none !important;
  overflow: visible !important;
}

.badge-filter__badge:hover {
  border-color: var(--primary-color, #ff6a00) !important;
  color: var(--primary-color, #ff6a00) !important;
  background: #fff7ed !important;
}

.badge-filter__badge--active {
  border-color: var(--primary-color, #ff6a00) !important;
  background: var(--primary-color, #ff6a00) !important;
  color: #fff !important;
  box-shadow: 0 2px 6px rgba(255, 106, 0, 0.25) !important;
}

.badge-filter__empty {
  font-size: 13px;
  color: var(--text-light, #94a3b8);
}

.badge-filter__toggle {
  border-style: dashed !important;
  color: var(--text-secondary, #64748b) !important;
}

.badge-filter__toggle i {
  font-size: 10px;
  margin-left: 2px;
}

.badge-filter--compact .badge-filter__title {
  font-size: 12px;
}

.badge-filter--compact .badge-filter__badge {
  padding: 3px 10px !important;
  font-size: 12px !important;
  min-height: 24px !important;
}
</style>
