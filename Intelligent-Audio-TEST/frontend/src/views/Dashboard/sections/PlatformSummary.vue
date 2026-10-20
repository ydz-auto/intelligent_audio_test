<template>
  <section class="dashboard-card platform-summary">
    <div class="platform-summary__grid">
      <!-- 左区：标题 + 三 StatCard -->
      <div class="platform-summary__left">
        <div class="dashboard-card__head">
          <div class="card-head-text">
            <span class="card-title">平台概览</span>
            <p class="card-sub">监控任务、资产与设备状态</p>
          </div>
        </div>
        <div class="stat-cards-row">
          <!-- 任务总数 -->
          <div
            role="button"
            tabindex="0"
            class="stat-tile"
            :class="{ 'is-link': can('task:read') }"
            @click="goTasks"
            @keydown.enter="goTasks"
          >
            <span class="stat-tile-icon stat-tile-icon--accent1"><i class="fas fa-clipboard-list"></i></span>
            <span class="stat-tile-value">{{ details?.tasks?.total ?? '--' }}</span>
            <span class="stat-tile-label">任务总数</span>
            <span class="stat-tile-sub">{{ details?.tasks?.completed ?? 0 }} 个已完成</span>
            <span v-if="taskTrendSpark" class="stat-sparkline">
              <svg :viewBox="`0 0 ${sparkW} ${sparkH}`" preserveAspectRatio="none" class="sparkline-svg">
                <polyline :points="taskTrendSpark" fill="none" stroke="var(--chart-1)" stroke-width="2" />
              </svg>
            </span>
          </div>

          <!-- 完成率 -->
          <div
            role="button"
            tabindex="0"
            class="stat-tile"
            :class="{ 'is-link': can('task:read') && latestTaskId }"
            @click="goLatestTask"
            @keydown.enter="goLatestTask"
          >
            <span class="stat-tile-icon stat-tile-icon--accent2"><i class="fas fa-chart-line"></i></span>
            <span class="stat-tile-value">{{ completionRate }}</span>
            <span class="stat-tile-label">完成率</span>
            <span class="stat-tile-sub">{{ details?.tasks?.completed ?? 0 }}/{{ details?.tasks?.total ?? 0 }} 执行完成</span>
          </div>

          <!-- 最近任务 -->
          <div
            role="button"
            tabindex="0"
            class="stat-tile"
            :class="{ 'is-link': can('task:read') && latestTaskId }"
            @click="goLatestTask"
            @keydown.enter="goLatestTask"
          >
            <span class="stat-tile-icon stat-tile-icon--accent3"><i class="fas fa-clock"></i></span>
            <span class="stat-tile-value stat-tile-value--sm">{{ latestTaskStatusText }}</span>
            <span class="stat-tile-label">最近任务</span>
            <span class="stat-tile-sub stat-tile-sub--truncate">{{ latestTaskName }}</span>
            <span class="stat-tile-details" v-if="latestTask">
              用例 {{ latestTask.completedCases }}/{{ latestTask.totalCases }} · {{ latestTaskCompletedText }}
            </span>
          </div>
        </div>
      </div>

      <!-- 右区：设备状态面板 -->
      <div class="platform-summary__right">
        <div class="device-status-head">
          <span class="device-status-label">设备状态</span>
          <span class="device-status-dot" :class="deviceStatusTone"></span>
          <span class="device-status-text">{{ deviceStatusText }}</span>
        </div>
        <div class="device-status-number">
          <span class="device-status-value">{{ details?.devices?.online ?? 0 }}</span>
          <span class="device-status-unit">台在线</span>
        </div>
        <div class="device-mini-cards">
          <div
            role="button"
            tabindex="0"
            class="mini-card"
            @click="goAudio"
            @keydown.enter="goAudio"
          >
            <span class="mini-card-icon"><i class="fas fa-music"></i></span>
            <span class="mini-card-label">音频文件</span>
            <span class="mini-card-value">{{ details?.audioFiles?.total ?? 0 }}</span>
            <span class="mini-card-sub">干音 {{ details?.audioFiles?.dry ?? 0 }} 个</span>
          </div>
          <div class="mini-card">
            <span class="mini-card-icon"><i class="fas fa-server"></i></span>
            <span class="mini-card-label">API 服务</span>
            <span class="mini-card-value">{{ details?.apis?.total ?? 0 }}</span>
            <span class="mini-card-sub">在线 {{ details?.apis?.online ?? 0 }} 个</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 排队状态条 -->
    <div v-if="can('task:read')" class="queue-bar">
      <span class="queue-bar-icon"><i class="fas fa-clock"></i></span>
      <span class="queue-bar-label">排队中</span>
      <span class="queue-bar-count">{{ queueCount }} 个任务</span>
      <span v-if="queueCount > 0" class="queue-bar-head">队首「{{ queueHeadName }}」</span>
      <span v-else class="queue-bar-head queue-bar-head--empty">当前无排队任务</span>
      <router-link class="queue-bar-link" to="/tasks">查看队列</router-link>
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/log.css'

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDashboardPermission } from '../../../composables/dashboard/useDashboardPermission'
import { getTaskStatusLabel } from '../../../domain/constants/reportLabels'
import type { HomeStatsDetails, HomeStatsSummary } from '../../../domain/model/stats'
import type { TaskDomainStats } from '../../../domain/model/task'

const props = defineProps<{
  details: HomeStatsDetails | null
  summary: HomeStatsSummary | null
  taskStats: TaskDomainStats | null
  queueCount: number
  queueHeadName: string
}>()

const router = useRouter()
const { can } = useDashboardPermission()

// ===== 三 StatCard =====

/** 完成率（completed/total 百分比，一位小数） */
const completionRate = computed(() => {
  const { total = 0, completed = 0 } = props.details?.tasks ?? {}
  if (!total) return '--'
  return `${((completed / total) * 100).toFixed(1)}%`
})

/** 最近任务（recent_tasks[0]） */
const latestTask = computed(() => props.summary?.recentTasks?.[0] ?? null)
const latestTaskId = computed(() => latestTask.value?.id ?? null)
const latestTaskName = computed(() => latestTask.value?.name ?? '暂无任务')
const latestTaskStatusText = computed(() =>
  latestTask.value ? getTaskStatusLabel(latestTask.value.status) : '--'
)
const latestTaskCompletedText = computed(() => {
  const t = latestTask.value
  if (!t) return '--'
  if (t.completedCases === t.totalCases && t.totalCases > 0) return '已完成'
  return '进行中'
})

/** 任务总数 sparkline：/tasks/stats trend 均分 12 桶 */
const sparkW = 160
const sparkH = 36
const taskTrendSpark = computed(() => {
  const trend = props.taskStats?.trend ?? []
  if (trend.length === 0) return ''
  const buckets = 12
  const counts: number[] = []
  for (let i = 0; i < buckets; i++) {
    const start = Math.floor((i / buckets) * trend.length)
    const end = Math.floor(((i + 1) / buckets) * trend.length)
    const slice = trend.slice(start, end)
    counts.push(slice.reduce((s, b) => s + b.count, 0))
  }
  const max = Math.max(...counts, 1)
  const points = counts.map((c, i) => {
    const x = (i / (buckets - 1)) * sparkW
    const y = sparkH - (c / max) * (sparkH - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return points
})

// ===== 设备状态 =====

const deviceStatusTone = computed(() => {
  const { total = 0, online = 0, offline = 0 } = props.details?.devices ?? {}
  if (total === 0) return 'dot-muted'
  if (offline === 0) return 'dot-success'
  if (online === 0) return 'dot-destructive'
  return 'dot-warning'
})

const deviceStatusText = computed(() => {
  const { total = 0, online = 0, offline = 0 } = props.details?.devices ?? {}
  if (total === 0) return '暂无设备'
  if (offline === 0) return '正常'
  if (online === 0) return '全部离线'
  return `${offline} 台离线`
})

// ===== 跳转 =====

function goTasks() {
  if (can('task:read')) router.push('/tasks')
}
function goLatestTask() {
  if (can('task:read') && latestTaskId.value) router.push(`/tasks/${latestTaskId.value}`)
}
function goAudio() {
  if (can('audio:read')) router.push('/AudioImport')
}
</script>
