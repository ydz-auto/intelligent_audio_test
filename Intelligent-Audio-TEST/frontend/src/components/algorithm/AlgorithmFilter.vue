<template>
  <BadgeFilter
    :options="effectiveOptions"
    :model-value="modelValue"
    :title="title"
    icon="fas fa-microchip"
    :show-all="showAll"
    all-label="全部"
    :compact="compact"
    @update:model-value="value => emit('update:modelValue', String(value))"
  />
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import BadgeFilter from '../common/BadgeFilter.vue';
import { useAlgorithmLabels } from '../../composables/algorithm/useAlgorithmLabels';

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
  // 始终预加载全局算法选项（作为兜底，接口为空/失败时展示标准算法清单）
  loadAlgorithms();
});

/** 最终选项：优先外部传入；剔除 'all' 占位项（由「全部」徽章承担），避免重复。
 *  若页面未配置选项或接口为空，兜底使用全局算法清单（含内置默认算法） */
const effectiveOptions = computed<AlgorithmFilterOption[]>(() => {
  const source = props.options && props.options.length > 0 ? props.options : globalOptions.value;
  const real = (source || []).filter(opt => opt.value && opt.value !== 'all');
  if (real.length > 0) return real;
  return (globalOptions.value || []).filter(opt => opt.value && opt.value !== 'all');
});
</script>
