<template>
  <div class="task-detail-page">
    <TaskDetailModal :task-id="taskId" />
  </div>
</template>

<script setup lang="ts">
// INT-208：日常任务详情路由页——复用既有任务详情弹窗组件（overlay 由弹窗容器提供，
// 页面语境下直接渲染同一内容），供已发布任务执行成功后跳转新任务详情。
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import TaskDetailModal from '../../components/common/modal/TaskDetailModal.vue';

const route = useRoute();

const taskId = computed(() => String(route.params.id ?? ''));
</script>

<style scoped>
.task-detail-page {
  padding: 16px 24px;
}
</style>
