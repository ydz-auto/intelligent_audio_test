<template>
  <div class="dashboard-page">
    <!-- 页面标题 + Actions -->
    <section class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-th-large"></i>
          工作台
        </h2>
        <p class="page-description">任务、资产与设备状态一览</p>
      </div>
      <div class="header-right">
        <button
          v-if="can('home:refresh')"
          type="button"
          class="btn btn-secondary"
          :disabled="refreshing"
          @click="handleRefresh"
        >
          <i class="fas" :class="refreshing ? 'fa-spinner fa-spin' : 'fa-sync-alt'"></i>
          {{ refreshing ? '刷新中…' : '刷新统计' }}
        </button>
        <router-link v-if="can('task:read')" class="btn btn-primary" to="/tasks">
          <i class="fas fa-chart-line"></i> 查看任务
        </router-link>
      </div>
    </section>

    <div class="dashboard-body">
      <!-- ① 算法卡片网格 -->
      <AlgorithmCardGrid />

      <!-- ② 开始使用引导卡 -->
      <SetupGuide :details="details" />

      <!-- ③ 平台概览卡 -->
      <PlatformSummary
        :details="details"
        :summary="summary"
        :task-stats="taskDomainStats"
        :queue-count="queueCount"
        :queue-head-name="queueHeadName"
      />

      <!-- ④ 双面板行 -->
      <div class="panels-row">
        <RecentTasksPanel :tasks="recentTasks" :loading="loadingSummary" />
        <TopGroupsPanel :groups="topGroups" :loading="loadingSummary" />
      </div>

      <!-- ⑤ 任务统计图表区 -->
      <TaskCharts v-if="can('task:read')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useNotification } from '../../composables/modal/useNotification'
import { useDashboardPermission } from '../../composables/dashboard/useDashboardPermission'
import { useDashboardStats } from '../../composables/dashboard/useDashboardStats'
import { useTaskDomainStats } from '../../composables/dashboard/useTaskDomainStats'
import { useQueueSummary } from '../../composables/dashboard/useQueueSummary'
import AlgorithmCardGrid from './sections/AlgorithmCardGrid.vue'
import SetupGuide from './sections/SetupGuide.vue'
import PlatformSummary from './sections/PlatformSummary.vue'
import RecentTasksPanel from './sections/RecentTasksPanel.vue'
import TopGroupsPanel from './sections/TopGroupsPanel.vue'
import TaskCharts from './sections/TaskCharts.vue'

const notification = useNotification()
const { can } = useDashboardPermission()

// 解构为顶层 ref：模板自动解包（stats.details 式嵌套访问不做模板解包）
const { details, summary, loadingSummary, loadAll, refreshStats } = useDashboardStats()
const { stats: taskDomainStats, load: loadTaskStats } = useTaskDomainStats()
const { count: queueCount, headName: queueHeadName, load: loadQueue } = useQueueSummary()

const refreshing = ref(false)

const recentTasks = computed(() => summary.value?.recentTasks ?? [])
const topGroups = computed(() => summary.value?.topGroups ?? [])

async function handleRefresh() {
  refreshing.value = true
  try {
    const result = await refreshStats()
    // 刷新统计联动图表区与排队条
    await Promise.allSettled([loadTaskStats(), loadQueue()])
    if (result.ok) {
      notification.success('统计已刷新')
    } else {
      notification.error(result.message || '刷新统计失败')
    }
  } finally {
    refreshing.value = false
  }
}

onMounted(async () => {
  await Promise.allSettled([loadAll(), loadTaskStats(), loadQueue()])
})
</script>

<style src="./Dashboard.css"></style>
