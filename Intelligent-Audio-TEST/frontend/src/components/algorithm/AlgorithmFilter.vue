<template>
  <div class="algorithm-filter" :class="{ 'algorithm-filter--compact': compact }">
    <span v-if="title" class="algorithm-filter__title">
      <i class="fas fa-microchip"></i>
      {{ title }}
    </span>
    <div class="algorithm-filter__badges">
      <button
        v-if="showAll"
        type="button"
        class="algorithm-filter__badge"
        :class="{ 'algorithm-filter__badge--active': isAll }"
        @click="select('all')"
      >
        全部
      </button>
      <button
        v-for="opt in effectiveOptions"
        :key="opt.value"
        type="button"
        class="algorithm-filter__badge"
        :class="{ 'algorithm-filter__badge--active': modelValue === opt.value }"
        @click="select(opt.value)"
      >
        {{ opt.label }}
      </button>
      <span v-if="effectiveOptions.length === 0" class="algorithm-filter__empty">暂无算法配置</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useAlgorithmLabels } from '../../composables/useAlgorithmLabels';

export interface AlgorithmFilterOption {
  value: string;
  label: string;
}

const props = withDefaults(defineProps<{
  /** 算法选项（{value,label}[]）；不传时自动从 useAlgorithmLabels 全局加载 */
  options?: AlgorithmFilterOption[];
  /** 当前选中值（'all' 或算法 value） */
  modelValue?: string;
  /** 筛选区标题 */
  title?: string;
  /** 是否展示「全部」徽章 */
  showAll?: boolean;
  /** 紧凑模式（标题内联） */
  compact?: boolean;
}>(), {
  options: undefined,
  modelValue: 'all',
  title: '算法筛选',
  showAll: true,
  compact: false,
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

const { algorithmOptions: globalOptions, loadAlgorithms } = useAlgorithmLabels();

onMounted(() => {
  // 预加载全局算法选项（模块级缓存，多个页面共用一次请求）
  loadAlgorithms();
});

/** 最终选项：优先外部传入；剔除 'all' 占位项（由「全部」徽章承担），避免重复 */
const effectiveOptions = computed<AlgorithmFilterOption[]>(() => {
  const source = props.options && props.options.length > 0 ? props.options : globalOptions.value;
  return (source || []).filter(opt => opt.value && opt.value !== 'all');
});

const isAll = computed(() => !props.modelValue || props.modelValue === 'all');

function select(value: string) {
  if (value === 'all') {
    emit('update:modelValue', 'all');
    return;
  }
  // 单选：再次点击已选中的算法视为取消（回到全部）
  emit('update:modelValue', props.modelValue === value ? 'all' : value);
}
</script>

<style scoped>
.algorithm-filter {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  width: 100%;
}

.algorithm-filter__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #64748b);
  white-space: nowrap;
  flex-shrink: 0;
}

.algorithm-filter__title i {
  color: var(--primary-color, #ff6a00);
  font-size: 12px;
}

.algorithm-filter__badges {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 徽章样式使用 !important：项目全局 button:not(.btn-icon-only):not(.svg-btn-only):not(.icon-btn-only)
   选择器特异性更高（0,3,1 > 0,2,0），会覆盖 scoped 样式导致边框/背景丢失 */
.algorithm-filter__badge {
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
}

.algorithm-filter__badge:hover {
  border-color: var(--primary-color, #ff6a00) !important;
  color: var(--primary-color, #ff6a00) !important;
  background: #fff7ed !important;
}

.algorithm-filter__badge--active {
  border-color: var(--primary-color, #ff6a00) !important;
  background: var(--primary-color, #ff6a00) !important;
  color: #fff !important;
  box-shadow: 0 2px 6px rgba(255, 106, 0, 0.25) !important;
}

.algorithm-filter__empty {
  font-size: 13px;
  color: var(--text-light, #94a3b8);
}

.algorithm-filter--compact .algorithm-filter__title {
  font-size: 12px;
}

.algorithm-filter--compact .algorithm-filter__badge {
  padding: 3px 10px !important;
  font-size: 12px !important;
  min-height: 24px !important;
  border-radius: 999px !important;
}
</style>
