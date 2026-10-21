<template>
  <!-- 标注代码下拉（INT-1106 对齐 React INT-1030：标注代码不再以原始代码文本输入）。
       语义：标注代码=算法类型代码——选「默认同算法类型」（空值，后端用当前算法类型），
       选其它算法类型表示复用该算法的标注（互用标注，算法 A 想要 B 的标注就选 B）。
       选项 = 算法列表 → 「算法名称（类型代码）」，人可读、不再让人填看不懂的代码。 -->
  <select
    class="form-input form-input-sm annotation-code-select"
    :aria-label="ariaLabel"
    :value="modelValue"
    @change="onChange"
  >
    <option value="">默认同算法类型</option>
    <option v-for="option in options" :key="option.type" :value="option.type">
      {{ option.name }}（{{ option.type }}）
    </option>
    <!-- 存量值不在算法列表（如算法已删除）回退显示原值，数据保全（照 React annotation-code-select 回退口径） -->
    <option v-if="fallbackValue" :value="fallbackValue">{{ fallbackValue }}</option>
  </select>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** 标注代码选项（算法类型 → 名称映射；类型代码即标注代码） */
export interface AlgorithmOption {
  type: string
  name: string
}

const props = withDefaults(defineProps<{
  /** 当前标注代码（算法类型代码；空串 = 默认同算法类型） */
  modelValue?: string
  /** 算法列表（选项=算法类型/标注代码 的映射） */
  options?: AlgorithmOption[]
  ariaLabel?: string
}>(), {
  modelValue: '',
  options: () => [],
  ariaLabel: '标注代码'
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

/** 存量值不在选项列表时回退显示原值（仅当非空且未匹配） */
const fallbackValue = computed(() =>
  props.modelValue !== '' && !props.options.some(o => o.type === props.modelValue)
    ? props.modelValue
    : ''
)

function onChange(e: Event) {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
}
</script>

<style scoped>
.annotation-code-select {
  width: 100%;
  min-width: 100px;
  cursor: pointer;
}
</style>
