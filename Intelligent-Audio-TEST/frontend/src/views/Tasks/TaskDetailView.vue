<template>
  <div class="task-detail-page">
    <TaskDetailModal :task-id="taskId" :focus-section="focusSection" />
  </div>
</template>

<script setup lang="ts">
// INT-208：日常任务详情路由页——复用既有任务详情弹窗组件（overlay 由弹窗容器提供，
// 页面语境下直接渲染同一内容），供已发布任务执行成功后跳转新任务详情。
// INT-1835 规范 18 §3.1：下单成功落点 `?focus=composition` 在此解析为 prop，
// 详情壳（TaskDetailModal）只在容器判定成立时滚动定位 + 高亮；非容器静默忽略。
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import TaskDetailModal from '../../components/common/modal/TaskDetailModal.vue';
import { isCompositionFocusRequested } from '../../utils/compositionFocus';

const route = useRoute();

const taskId = computed(() => String(route.params.id ?? ''));
/** hash 路由：`#/tasks/{id}?focus=composition`（query 而非 `#composition`，G6） */
const focusSection = computed<'composition' | null>(() =>
  isCompositionFocusRequested(route.query.focus as string | (string | null)[] | null | undefined)
    ? 'composition'
    : null);
</script>

<style scoped>
.task-detail-page {
  padding: 16px 24px;
}
</style>
