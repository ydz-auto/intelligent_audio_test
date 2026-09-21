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
}>(), {
  selectedIds: () => [],
  emptyText: '暂无可用的评价维度'
})

const emit = defineEmits<{
  (e: 'toggle', dim: any): void
}>()

const selectedIdSet = computed(() => new Set(props.selectedIds.map(String)))
const isSelected = (dim: any) => selectedIdSet.value.has(String(dim.id))
</script>

<template>
  <div class="dimension-cloud-container">
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

.dimension-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background-color: var(--background-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 20px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  user-select: none;
  white-space: nowrap;
}

.dimension-tag:hover {
  background-color: var(--primary-light);
  color: var(--primary-color);
  border-color: var(--primary-color);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.dimension-tag.selected {
  background-color: #ffe9d4;
  color: #e85d04;
  border-color: var(--primary-color);
  font-weight: 600;
}

.dimension-tag.selected:hover {
  background-color: #ffe2c6;
  color: #e85d04;
  border-color: var(--primary-color);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

/* 主维度标签 */
.dimension-tag-main {
  background-color: var(--primary-light);
  color: var(--primary-color);
  border-color: rgba(255, 106, 0, 0.35);
  font-weight: 600;
}

.dimension-tag-main:hover {
  background-color: #ffe9d4;
  border-color: var(--primary-color);
}

.dimension-tag-main.selected {
  background-color: #ffe9d4;
  color: #e85d04;
  border-color: var(--primary-color);
  font-weight: 700;
}

.dimension-tag-main.selected:hover {
  background-color: #ffe2c6;
  border-color: var(--primary-color);
  transform: translateY(-1px);
}

/* 子维度标签 */
.dimension-tag-sub {
  background-color: var(--background-secondary);
  color: var(--text-primary);
  border-color: var(--border-color);
}

.dimension-tag-sub.selected {
  background-color: #fff3e3;
  color: #e85d04;
  border-color: var(--primary-color);
}

.dimension-tag-sub.selected:hover {
  background-color: #ffe9d4;
  border-color: var(--primary-color);
  transform: translateY(-1px);
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
  background-color: var(--primary-color);
  color: #fff;
  border: none;
}

.dim-badge-sub {
  background-color: var(--primary-light);
  color: var(--primary-color);
  border: 1px solid rgba(255, 106, 0, 0.35);
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
  background: var(--primary-light);
  color: var(--primary-color);
  border: 1px solid rgba(255, 106, 0, 0.35);
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
