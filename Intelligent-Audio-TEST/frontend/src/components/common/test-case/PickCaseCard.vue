<template>
  <TestCaseCard
    :test-case="caseItem"
    :is-selected="state === 'checked'"
    :show-checkbox="false"
    :name-clickable="onNameClick"
    hide-meta
    @name-click="handleNameClick"
  >
    <template #leading>
      <label class="pcc-check" @click.stop>
        <input
          type="checkbox"
          class="pcc-checkbox"
          :checked="state === 'checked'"
          :indeterminate="state === 'indeterminate'"
          :aria-label="`选择 ${name}`"
          @change="handleToggle"
        />
      </label>
    </template>
    <template #badgeLeading>
      <span class="pcc-count"><span class="pcc-count-label">{{ count }} 条</span></span>
      <slot name="badgeLeading" />
    </template>
    <template #actions>
      <div class="pcc-actions">
        <slot name="actions" />
        <button
          type="button"
          class="pcc-toggle"
          :class="{ 'pcc-toggle--open': open }"
          :aria-label="open ? '收起' : '展开'"
          :aria-expanded="open"
          @click.stop="() => emit('toggle-open')"
        >
          <i class="fas" :class="open ? 'fa-chevron-down' : 'fa-chevron-right'"></i>
        </button>
      </div>
    </template>
    <template #expandedContent>
      <div v-if="open" class="pcc-children">
        <slot />
      </div>
    </template>
  </TestCaseCard>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'
import "../../../assets/styles/components/test-case-card.css"

/**
 * 挑选/购物车 compact 用例卡（18_挑选合并交互重设计.md §3.8.3/§3.8.4，INT-1103）。
 * CaseCard compact 变体：复用 TestCaseCard 字段口径（名称 / CaseIdBadge / 算法徽章 / 计数 Badge），
 * hideMeta + 精简操作区（展开三角）+ 前导三态勾选；用例视图用例节点与购物车用例节点共用。
 */
import TestCaseCard from './TestCaseCard.vue';
import type { NodeCheckState } from '../../task/pick/pickTree';

const props = defineProps<{
  /** 用例名（已降级友好文案「用例不可用 {前 8 位}…」） */
  name: string;
  /** case_id（CaseIdBadge 点击复制） */
  caseId?: string | number;
  /** 算法类型（算法徽章） */
  algorithmType?: string | null;
  /** 计数 Badge「{n} 条」 */
  count: number;
  /** 勾选态（R3 三态） */
  state: NodeCheckState;
  /** 名称可点击（用例详情弹窗等） */
  onNameClick?: boolean;
  open: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggle', select: boolean): void;
  (e: 'toggle-open'): void;
  (e: 'name-click', caseId: string | number | undefined): void;
}>();

/** 勾选切换（R6 用例级 / 购物车批量移除选择；change 目标 checked 即新选中态） */
const handleToggle = (e: Event) => {
  const checked = (e.target as HTMLInputElement).checked;
  emit('toggle', checked);
};

/** 名称可点击：仅 onNameClick 时上抛（如任务域开用例详情弹窗） */
const handleNameClick = () => {
  if (props.onNameClick) emit('name-click', props.caseId);
};

/** 喂给 TestCaseCard 的字段子集（compact 口径：无描述/时长/轮次数据） */
const caseItem = {
  id: props.caseId ?? props.name,
  name: props.name,
  tags: [] as string[],
  algorithmType: props.algorithmType ?? null,
  totalDuration: null,
  description: '',
};
</script>

<style scoped>
.pcc-check {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  margin-top: 2px;
  cursor: pointer;
}
.pcc-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--primary);
}
.pcc-count {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
}
.pcc-count-label {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--color-slate-100);
  color: var(--color-slate-600);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono, monospace);
}
.pcc-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.pcc-toggle {
  border: none;
  background: none;
  color: var(--color-slate-400);
  cursor: pointer;
  font-size: 12px;
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  transition: transform 0.15s ease;
}
.pcc-toggle:hover {
  background: var(--color-slate-100);
  color: var(--foreground);
}
.pcc-toggle--open {
  transform: rotate(0deg);
}
.pcc-children {
  border-top: 1px solid var(--border);
  padding: 8px 12px;
}
</style>
