<template>
  <section class="dashboard-card dashboard-panel">
    <div class="dashboard-panel__head">
      <span class="panel-icon panel-icon--info"><i class="fas fa-clipboard-list"></i></span>
      <div class="panel-head-text">
        <span class="panel-title">最近任务</span>
        <span class="panel-desc">最新创建的 5 个任务</span>
      </div>
      <router-link class="panel-link" to="/tasks">查看全部</router-link>
    </div>

    <div class="panel-list" :class="{ 'is-loading': loading }">
      <template v-if="loading">
        <div v-for="i in 5" :key="i" class="panel-row panel-row--skeleton">
          <span class="skeleton-line"></span>
        </div>
      </template>
      <template v-else-if="tasks.length > 0">
        <div
          v-for="task in tasks"
          :key="task.id"
          role="button"
          tabindex="0"
          class="panel-row"
          @click="goDetail(task)"
          @keydown.enter="goDetail(task)"
        >
          <span class="panel-row-main">
            <span class="panel-row-title">{{ task.name }}</span>
            <span class="panel-row-meta">
              用例 {{ task.completedCases }}/{{ task.totalCases }} · {{ formatTime(task.createdAt) }}
            </span>
          </span>
          <span class="panel-row-side">
            <span class="status-badge" :class="statusType(task.status)">{{ statusText(task.status) }}</span>
            <span v-if="task.algorithmType" class="algorithm-chip">{{ algorithmLabel(task.algorithmType) }}</span>
          </span>
        </div>
      </template>
      <div v-else class="panel-empty">
        <span class="empty-icon"><i class="fas fa-inbox"></i></span>
        <span class="empty-title">暂无任务</span>
        <span class="empty-desc">发起第一次测试后，最近任务会显示在这里</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getTaskStatusLabel } from '../../../domain/constants/reportLabels'
import { getStatusType } from '../../../utils/statusUtils'
import { useAlgorithmLabels } from '../../../composables/algorithm/useAlgorithmLabels'
import type { RecentTaskSummary } from '../../../domain/model/stats'

const props = defineProps<{
  tasks: RecentTaskSummary[]
  loading: boolean
}>()

const router = useRouter()
const { getAlgorithmLabel, loadAlgorithms } = useAlgorithmLabels()

// 预加载算法选项（/algorithm/options），保证算法徽章中文名就绪
onMounted(() => {
  loadAlgorithms()
})

function goDetail(task: RecentTaskSummary) {
  router.push(`/tasks/${task.id}`)
}

function statusText(status: string) {
  return getTaskStatusLabel(status)
}

function statusType(status: string) {
  return `badge-${getStatusType(status)}`
}

function algorithmLabel(type?: string) {
  return type ? getAlgorithmLabel(type) : ''
}

function formatTime(iso?: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>
