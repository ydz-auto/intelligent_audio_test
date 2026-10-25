<template>
  <template v-if="counts">
    <span v-if="counts.failed > 0" class="branch-count-failed">· 失败 {{ counts.failed }}</span>
    <span v-if="counts.missing > 0" class="branch-count-missing"> · 失效 {{ counts.missing }}</span>
  </template>
</template>

<script setup lang="ts">
/**
 * 分支节点计数后缀（规范 18 §5 / INT-1836）：失败 f / 失效 k。
 *
 * 依据 = 该节点下**过滤后**的叶（`filterCompositionTree` 已把节点 itemIds 重算成命中集），
 * 随筛选实时重算；全部成功时不渲染任何后缀（调用方保留「{n} 条」）。
 * 失败部分用 `--destructive` 文本色，失效部分弱化为 `--muted-foreground`（§5）。
 */
import type { CompositionBranchCounts } from './compositionTree';

defineProps<{
  /** 分支计数；null = 非组成区（不渲染） */
  counts: CompositionBranchCounts | null;
}>();

defineOptions({ name: 'BranchCountSuffix' });
</script>

<style scoped>
.branch-count-failed {
  color: var(--destructive);
}

.branch-count-missing {
  color: var(--muted-foreground);
}
</style>
