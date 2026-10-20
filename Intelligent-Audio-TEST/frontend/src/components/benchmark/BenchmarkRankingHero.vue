<template>
  <div class="rankings-hero">
    <h1 class="hero-title">排行榜</h1>
    <p class="hero-subtitle">多个厂商模型/APP/API 在同一标准化环境、同一测试集与指标下同时实测，按指标与场景生成名次，横向看清业界水平。</p>

    <!-- 类别维度下划线页签（对位 INT-359 §4.2 RankingsHero） -->
    <div class="category-tabs" role="tablist" aria-label="指标类别">
      <button
        v-for="(label, value) in tabLabels"
        :key="value"
        type="button"
        class="category-tab"
        :class="{ active: activeCategory === value }"
        role="tab"
        :aria-selected="activeCategory === value"
        :aria-label="`${label}，${activeCategory === value ? '当前已选中' : ''}`"
        @click="$emit('select', value as '' | BenchmarkCategoryType)"
      >
        {{ label }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed } from 'vue'
import {
  BenchmarkCategoryTabLabels,
  type BenchmarkCategoryType,
} from '../../domain/enums'

defineProps<{
  activeCategory: '' | BenchmarkCategoryType
}>()

defineEmits<{ (e: 'select', category: '' | BenchmarkCategoryType): void }>()

/** 页签选项（全部 + 四类别，INT-359 文案：全部/语音识别/语音对话/语音合成/翻译） */
const tabLabels = computed(() => BenchmarkCategoryTabLabels)
</script>

<style scoped>
.rankings-hero {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hero-title {
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.025em;
  color: var(--foreground);
  margin: 0;
}
.hero-subtitle {
  max-width: 42rem;
  font-size: 14px;
  color: var(--muted-foreground);
  margin: 0;
}
.category-tabs {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  margin-top: 4px;
}
.category-tab {
  position: relative;
  flex-shrink: 0;
  margin-bottom: -1px;
  padding: 8px 12px;
  font-size: 14px;
  font-weight: 500;
  background: none;
  border: none;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  color: var(--muted-foreground);
  cursor: pointer;
  white-space: nowrap;
}
.category-tab:hover {
  color: var(--foreground);
}
.category-tab.active {
  color: var(--foreground);
}
.category-tab.active::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 0;
  height: 2px;
  background: var(--foreground);
  border-radius: var(--radius-1);
}
</style>
