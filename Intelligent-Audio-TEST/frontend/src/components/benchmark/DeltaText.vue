<template>
  <span
    class="delta-text"
    :class="textClass"
    :title="tooltip"
  >
    <template v-if="display">
      {{ display }}
      <span v-if="arrow" class="delta-arrow" aria-hidden="true">{{ arrow }}</span>
    </template>
    <template v-else>—</template>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BenchmarkRankingRow } from '../../domain/model/benchmark'
import { BenchmarkSource, BenchmarkDirection } from '../../domain/enums'

const props = defineProps<{
  /** 榜单行（DeltaText 只消费 delta_external / score100 / direction / source / unit） */
  row: BenchmarkRankingRow
}>()

/**
 * 基线差文案（对位 INT-359 §5.4 DeltaText）：
 * - 实测轨双轨并存时显示「基线差 ±{|delta|}{unit}」，正负色随指标 direction 语义翻转
 * - 否则显示 score100（有值：「{score100} 分」，空值「—」）
 * - 基线差 0 或空 → 中性「—」
 */
const display = computed<string>(() => {
  const { source, deltaExternal, score100, unit } = props.row
  if (source === BenchmarkSource.PLATFORM_TEST && deltaExternal !== null && deltaExternal !== undefined) {
    if (deltaExternal === 0) return ''
    return `基线差 ±${Math.abs(deltaExternal).toFixed(2)}${unit || ''}`
  }
  if (score100 !== null && score100 !== undefined) {
    return `${score100} 分`
  }
  return ''
})

/** 方向感知的正负箭头：涨=↑、跌=↓（语义随指标 direction 翻转） */
const arrow = computed<'↑' | '↓' | ''>(() => {
  const { source, deltaExternal, direction } = props.row
  if (source !== BenchmarkSource.PLATFORM_TEST || deltaExternal === null || deltaExternal === undefined || deltaExternal === 0) {
    return ''
  }
  if (direction === BenchmarkDirection.HIGHER_IS_BETTER) {
    return deltaExternal > 0 ? '↑' : '↓'
  }
  // lower_is_better：低于基线（delta<0）= 更优
  return deltaExternal < 0 ? '↓' : '↑'
})

const textClass = computed<Record<string, boolean>>(() => {
  const { source, deltaExternal, direction } = props.row
  if (source !== BenchmarkSource.PLATFORM_TEST || deltaExternal === null || deltaExternal === undefined || deltaExternal === 0) {
    return { 'delta-better': false, 'delta-worse': false }
  }
  const isBetter = direction === BenchmarkDirection.HIGHER_IS_BETTER
    ? deltaExternal > 0
    : deltaExternal < 0
  return { 'delta-better': isBetter, 'delta-worse': !isBetter }
})

/** 基线差 tooltip：高/低于外部基线 + 更优/更差（语义随指标 direction 翻转，对位审计修复） */
const tooltip = computed<string>(() => {
  const { source, deltaExternal, direction } = props.row
  if (source !== BenchmarkSource.PLATFORM_TEST || deltaExternal === null || deltaExternal === undefined || deltaExternal === 0) {
    return ''
  }
  const isHigher = deltaExternal > 0
  const isBetter = direction === BenchmarkDirection.HIGHER_IS_BETTER ? isHigher : !isHigher
  return `${isHigher ? '高于' : '低于'}外部基线（${isBetter ? '更优' : '更差'}）`
})
</script>

<style scoped>
.delta-text {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.delta-arrow {
  margin-left: 1px;
}
.delta-better {
  color: var(--success);
}
.delta-worse {
  color: var(--destructive);
}
</style>
