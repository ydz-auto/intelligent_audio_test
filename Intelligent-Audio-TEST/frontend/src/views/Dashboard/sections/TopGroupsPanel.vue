<template>
  <section class="dashboard-card dashboard-panel">
    <div class="dashboard-panel__head">
      <span class="panel-icon panel-icon--chart2"><i class="fas fa-folder-open"></i></span>
      <div class="panel-head-text">
        <span class="panel-title">用例分组排行</span>
        <span class="panel-desc">按用例数量排序的前 5 个分组</span>
      </div>
    </div>

    <div class="panel-list" :class="{ 'is-loading': loading }">
      <template v-if="loading">
        <div v-for="i in 5" :key="i" class="panel-row panel-row--skeleton">
          <span class="skeleton-line"></span>
        </div>
      </template>
      <template v-else-if="groups.length > 0">
        <div
          v-for="(group, idx) in groups"
          :key="group.id"
          class="group-row"
          :class="{ 'is-link': can('testcase:read') }"
          @click="goGroup(group)"
        >
          <span class="group-rank">{{ idx + 1 }}</span>
          <span class="group-main">
            <span class="group-name">{{ group.name }}</span>
            <span class="group-count">{{ group.caseCount }} 条</span>
            <span class="group-progress">
              <span class="group-progress-fill" :style="{ width: progressWidth(group) }"></span>
            </span>
          </span>
        </div>
      </template>
      <div v-else class="panel-empty">
        <span class="empty-icon"><i class="fas fa-inbox"></i></span>
        <span class="empty-title">暂无用例分组</span>
        <span class="empty-desc">在用例管理中创建分组后，这里会显示排行</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/progress.css'

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDashboardPermission } from '../../../composables/dashboard/useDashboardPermission'
import type { TopGroupSummary } from '../../../domain/model/stats'

const props = defineProps<{
  groups: TopGroupSummary[]
  loading: boolean
}>()

const router = useRouter()
const { can } = useDashboardPermission()

const maxCount = computed(() => Math.max(...props.groups.map(g => g.caseCount), 1))

function progressWidth(group: TopGroupSummary) {
  return `${Math.max(4, Math.round((group.caseCount / maxCount.value) * 100))}%`
}

function goGroup(group: TopGroupSummary) {
  if (can('testcase:read')) {
    router.push({ path: '/TestCaseManager', query: { group: String(group.id) } })
  }
}
</script>
