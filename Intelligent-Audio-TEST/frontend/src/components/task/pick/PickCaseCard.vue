<template>
  <TestCaseCard
    :test-case="caseItem"
    :is-selected="state === 'checked'"
    :indeterminate="state === 'indeterminate'"
    :show-checkbox="true"
    :show-config="false"
    :compact="true"
    :count="count"
    :show-expand="true"
    :open="open"
    :actions="actions ?? []"
    @toggle-selection="onToggleCard"
    @toggle-open="$emit('toggle-open')"
    @action="$emit('action', $event)"
  >
    <template #expandedContent>
      <!-- 子树点击不冒泡到用例卡根（卡片根 @click=R6 用例级勾选；叶行/分支行各自勾选，
           否则点叶行会同时触发用例级切换，INT-1110 实测） -->
      <div @click.stop>
        <slot />
      </div>
    </template>
  </TestCaseCard>
</template>

<script setup lang="ts">
/**
 * PickCaseCard —— 挑选/购物车 compact 用例卡（18_挑选合并交互重设计.md §3.8.3/§4.2，INT-1047/INT-1110）。
 * 复用本线全站统一用例卡 TestCaseCard（INT-1103 交付）compact 变体：
 * 「名称 + CaseIdBadge + 算法徽章 + 计数 Badge」最小呈现（§3.6 裁定②注记）；
 * 勾选走 R6 用例级三态（选中集为唯一真相，状态由父级传入）；
 * actions 透传 TestCaseCard 图标钮（购物车「移除该组」等，§4.3 移除矩阵）。
 */
import { computed } from 'vue';
import TestCaseCard from '../../common/test-case/TestCaseCard.vue';
import type { NodeCheckState } from './pickTree';

const props = defineProps<{
  /** 用例名（已降级友好文案「用例不可用 {前 8 位}…」） */
  name: string;
  /** case_id（CaseIdBadge 点击复制） */
  caseId?: string | number | null;
  /** 算法类型（算法徽章） */
  algorithmType?: string | null;
  /** 计数 Badge「{n} 条」 */
  count: number;
  /** 勾选态（R3 三态，由父级派生） */
  state: NodeCheckState;
  open: boolean;
  /** 透传 TestCaseCard 图标钮（购物车「移除该组」等） */
  actions?: Array<{ id: string; title?: string; icon?: string; iconClass?: string; disabled?: boolean }>;
}>();

const emit = defineEmits<{
  (e: 'toggle', select: boolean): void;
  (e: 'toggle-open'): void;
  (e: 'action', payload: { action: { id: string }; testCase: unknown }): void;
}>();

/** 统一用例卡入参：候选行无 tags/type/时长等字段（§11-7 待补）→ 仅名称 + 算法徽章最小呈现 */
const caseItem = computed(() => ({
  id: props.caseId ?? props.name,
  name: props.name,
  type: [],
  algorithmType: props.algorithmType ?? null,
  description: '',
}));

/** 卡片/复选框点击 → R6 用例级切换（三态：非全选 → 全选；全选 → 取消） */
function onToggleCard() {
  emit('toggle', props.state !== 'checked');
}
</script>
