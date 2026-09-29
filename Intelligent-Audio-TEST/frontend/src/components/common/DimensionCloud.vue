<script setup lang="ts">
import { computed } from 'vue'

/** 维度云分组：主维度 + 其子维度；main 为 null 表示父维度不在候选集（孤儿子维度） */
export interface DimensionCloudGroup {
  main: any | null
  children: any[]
  /** 孤儿子维度时展示的父维度名 */
  orphanParentName?: string
}

const props = withDefaults(defineProps<{
  /** 分组后的维度云数据 */
  groups: DimensionCloudGroup[]
  /** 已选维度 id 列表（用于高亮） */
  selectedIds?: (string | number)[]
  /** 空态文案 */
  emptyText?: string
  /** 主题变体：round=单轮评估维度(debug 蓝) / overall=整体评估维度(info 绿) */
  variant?: 'round' | 'overall'
}>(), {
  selectedIds: () => [],
  emptyText: '暂无可用的评价维度',
  variant: 'round'
})

const emit = defineEmits<{
  (e: 'toggle', dim: any): void
}>()

const selectedIdSet = computed(() => new Set(props.selectedIds.map(String)))
const isSelected = (dim: any) => selectedIdSet.value.has(String(dim.id))
</script>

<template>
  <div class="dimension-cloud-container" :class="`variant-${variant}`">
    <!-- 主维度 + 紧随其子维度，成组展示 -->
    <div v-for="(group, gi) in groups" :key="gi" class="dimension-group">
      <template v-if="group.main">
        <div
          class="dimension-tag dimension-tag-main"
          :class="{ selected: isSelected(group.main) }"
          @click.stop.prevent="emit('toggle', group.main)"
        >
          {{ group.main.name }}
          <span class="dim-badge dim-badge-main">主</span>
          <span v-if="group.children.length > 0" class="dim-group-count">{{ group.children.length }}</span>
        </div>
        <div v-if="group.children.length > 0" class="dimension-sub-list">
          <div
            v-for="dim in group.children"
            :key="dim.id"
            class="dimension-tag dimension-tag-sub"
            :class="{ selected: isSelected(dim) }"
            @click.stop.prevent="emit('toggle', dim)"
          >
            <span class="tree-branch">└</span>{{ dim.name }}
            <span class="dim-badge dim-badge-sub">子</span>
          </div>
        </div>
      </template>
      <!-- 孤儿子维度：父维度不在当前候选集，附带父维度名提示 -->
      <template v-else>
        <div
          v-for="dim in group.children"
          :key="dim.id"
          class="dimension-tag dimension-tag-sub"
          :class="{ selected: isSelected(dim) }"
          @click.stop.prevent="emit('toggle', dim)"
        >
          <span class="tree-branch">└</span>{{ dim.name }}
          <span class="dim-badge dim-badge-sub">子</span>
          <span v-if="group.orphanParentName" class="parent-name-hint">（{{ group.orphanParentName }}）</span>
        </div>
      </template>
    </div>
    <p v-if="groups.length === 0" class="empty-hint">{{ emptyText }}</p>
  </div>
</template>

<style scoped>
/* 维度标签云 */
.dimension-cloud-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 16px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  max-height: 220px;
  overflow-y: auto;
  align-content: flex-start;
}

/* 主维度 + 子维度分组 */
.dimension-group {
  display: contents;
}

.dimension-sub-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding-left: 26px;
  width: 100%;
  margin-bottom: 4px;
}

/* 主题变体：round=单轮评估维度(debug 蓝) / overall=整体评估维度(info 绿)，仅作用于徽章，容器保持中性灰 */
/* --dim-text 为描边态文字色：主色小字对比度不足，统一加深一档 */
.dimension-cloud-container.variant-round {
  --dim-accent: #1890ff;
  --dim-accent-bg: #e6f7ff;
  --dim-accent-border: #91caff;
  --dim-accent-hover: #40a9ff;
  --dim-text: #096dd9;
}
.dimension-cloud-container.variant-overall {
  --dim-accent: #52c41a;
  --dim-accent-bg: #f6ffed;
  --dim-accent-border: #b7eb8f;
  --dim-accent-hover: #73d13d;
  --dim-text: #389e0d;
}

/* 维度标签云：未选中=描边式（透明底+主题色细边+实色字）；选中=填充主题色+白字+黑阴影 */
.dimension-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background-color: transparent;
  color: var(--dim-text);
  border: 1px solid var(--dim-accent-border);
  border-radius: 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s ease;
  user-select: none;
  white-space: nowrap;
}

.dimension-tag:hover {
  background-color: var(--dim-accent-bg);
  transform: translateY(-1px);
}

.dimension-tag.selected {
  background-color: var(--dim-accent);
  color: #fff;
  border-color: var(--dim-accent);
  font-weight: 600;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.dimension-tag.selected:hover {
  background-color: var(--dim-accent-hover);
  border-color: var(--dim-accent-hover);
}

/* 选中（填充态）内部徽标反色：白底深主题色字保证可读 */
.dimension-tag.selected .dim-badge-main,
.dimension-tag.selected .dim-badge-sub {
  background-color: #fff;
  color: var(--dim-text);
  border: none;
}

.dimension-tag.selected .dim-group-count {
  background-color: #fff;
  color: var(--dim-text);
  border: none;
}

.dimension-tag.selected .tree-branch,
.dimension-tag.selected .parent-name-hint {
  color: rgba(255, 255, 255, 0.8);
}

/* 主维度标签：加粗区分层级 */
.dimension-tag-main {
  font-weight: 600;
}

.dimension-tag-main.selected {
  font-weight: 700;
}

/* 子维度标签：与主维度同主题，层级靠主/子徽标区分 */
.dimension-tag-sub {
  font-weight: 500;
}

/* 主/子徽标 */
.dim-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  flex-shrink: 0;
}

.dim-badge-main {
  background-color: var(--dim-accent);
  color: #fff;
  border: none;
}

.dim-badge-sub {
  background-color: #fff;
  color: var(--dim-text);
  border: 1px solid var(--dim-accent-border);
}

/* 主维度组内子维度数量角标 */
.dim-group-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background-color: #fff;
  color: var(--dim-text);
  border: 1px solid var(--dim-accent-border);
  font-size: 11px;
  font-weight: 600;
}

/* 树形分支符号 */
.tree-branch {
  color: #9e9e9e;
  font-size: 14px;
  font-family: monospace;
  flex-shrink: 0;
}

/* 孤儿子维度父名提示 */
.parent-name-hint {
  font-size: 12px;
  color: #9e9e9e;
  font-weight: normal;
}

.empty-hint {
  margin: 8px 0;
  color: #999;
  font-size: 13px;
}
</style>
