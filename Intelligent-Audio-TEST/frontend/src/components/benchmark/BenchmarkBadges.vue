<template>
  <span class="benchmark-badges">
    <span class="badge badge-neutral">{{ subjectTypeLabel }}</span>
    <span v-if="deviceTypeLabel" class="badge badge-neutral badge-device">{{ deviceTypeLabel }}</span>
    <span v-if="versionLabel" class="badge badge-neutral badge-version">{{ versionLabel }}</span>
    <span
      class="badge"
      :class="isPlatformTest ? 'badge-info' : 'badge-secondary'"
    >{{ sourceLabel }}</span>
  </span>
</template>

<script setup lang="ts">
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'

import { computed } from 'vue'
import type { BenchmarkRankingRow } from '../../domain/model/benchmark'
import {
  BenchmarkSource,
  BenchmarkSourceLabels,
  BenchmarkSubjectTypeLabels,
  BenchmarkDeviceTypeLabels,
  type BenchmarkSubjectTypeType,
} from '../../domain/enums'

const props = defineProps<{ row: BenchmarkRankingRow }>()

const isPlatformTest = computed(() => props.row.source === BenchmarkSource.PLATFORM_TEST)

const sourceLabel = computed(() =>
  BenchmarkSourceLabels[props.row.source] || props.row.source)

const subjectTypeLabel = computed(() =>
  BenchmarkSubjectTypeLabels[props.row.subjectType as BenchmarkSubjectTypeType] || props.row.subjectType)

const deviceTypeLabel = computed(() => {
  const t = props.row.deviceType
  return t ? (BenchmarkDeviceTypeLabels[t] || t) : ''
})

const versionLabel = computed(() =>
  isPlatformTest.value && props.row.publishedTaskVersion != null
    ? `v${props.row.publishedTaskVersion}`
    : '')
</script>

<style scoped>
.benchmark-badges {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: var(--radius-tag);
  font-size: 11px;
  line-height: 1.6;
}
.badge-neutral {
  background: var(--gray-light);
  color: var(--muted-foreground);
}
.badge-device {
  font-style: italic;
}
.badge-version {
  font-family: var(--font-family-mono, monospace);
}
.badge-info {
  background: var(--info);
  color: var(--info-foreground);
}
.badge-secondary {
  background: var(--secondary);
  color: var(--secondary-foreground);
}
</style>
