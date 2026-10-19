<template>
  <section class="dashboard-card algorithm-grid-card">
    <!-- 区头 -->
    <div class="dashboard-card__head">
      <div class="card-head-text">
        <span class="card-eyebrow">算法切换</span>
        <p class="card-sub">点击卡片切换全局算法：任务、用例、设备、报告、日志列表将按所选算法过滤</p>
      </div>
    </div>

    <!-- 无 algorithm:read 只读降级条（网格不渲染） -->
    <div v-if="!canManage" class="algorithm-readonly-bar">
      <span class="readonly-label">当前算法</span>
      <span class="readonly-value">{{ readonlyLabel }}</span>
    </div>

    <!-- 加载骨架 -->
    <div v-else-if="loading && definitions.length === 0" class="algorithm-grid">
      <div v-for="i in 4" :key="i" class="algorithm-card algorithm-card--skeleton">
        <span class="skeleton-icon"></span>
        <span class="skeleton-title"></span>
        <span class="skeleton-desc"></span>
      </div>
    </div>

    <!-- 网格 -->
    <div v-else class="algorithm-grid">
      <div
        role="button"
        tabindex="0"
        class="algorithm-card"
        :class="{ 'is-selected': selectedType === null }"
        @click="handleSelect(null)"
        @keydown.enter="handleSelect(null)"
      >
        <span class="algorithm-icon">
          <i class="fas fa-layer-group"></i>
        </span>
        <span class="algorithm-name">全部算法</span>
        <span class="algorithm-desc">不按算法筛选，展示全部算法数据。</span>
        <span v-if="selectedType === null" class="algorithm-current-badge">
          <i class="fas fa-check"></i> 当前
        </span>
      </div>

      <div
        v-for="algo in definitions"
        :key="algo.type"
        role="button"
        tabindex="0"
        class="algorithm-card"
        :class="{
          'is-selected': selectedType === algo.type,
          'is-offline': algo.status !== 'online',
        }"
        :aria-disabled="algo.status !== 'online'"
        @click="algo.status === 'online' && handleSelect(algo.type)"
        @keydown.enter="algo.status === 'online' && handleSelect(algo.type)"
      >
        <span class="algorithm-icon">
          <i :class="algo.icon || 'fa-microchip'"></i>
        </span>
        <span class="algorithm-name">{{ algo.name || algo.type }}</span>
        <span class="algorithm-badges">
          <span v-if="algo.groupName" class="badge badge-outline">{{ algo.groupName }}</span>
          <span class="badge" :class="algo.status === 'online' ? 'badge-online' : 'badge-offline'">
            {{ algo.status === 'online' ? '在线' : '离线' }}
          </span>
        </span>
        <span v-if="paramSummary(algo)" class="algorithm-params">{{ paramSummary(algo) }}</span>
        <span class="algorithm-desc">{{ algo.description }}</span>
        <span v-if="selectedType === algo.type" class="algorithm-current-badge">
          <i class="fas fa-check"></i> 当前
        </span>
      </div>
    </div>

    <!-- 加载失败降级 -->
    <div v-if="error && canManage" class="algorithm-error">
      <span class="algorithm-error-value">--</span>
      <span class="algorithm-error-text">{{ error }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useNotification } from '../../../composables/modal/useNotification'
import { useDashboardPermission } from '../../../composables/dashboard/useDashboardPermission'
import { useAlgorithmCards, getAlgorithmParamSummary } from '../../../composables/dashboard/useAlgorithmCards'
import { useGlobalAlgorithmStore } from '../../../store/globalAlgorithmStore'

const { can } = useDashboardPermission()
const notification = useNotification()
const store = useGlobalAlgorithmStore()
const { definitions, loading, error, errorDetail, selectedType, select, load } = useAlgorithmCards()

/** INT-899（INT-858 N1）：加载失败降级——固定文案渲染进卡片网格，原始 RPC 详情仅进 Toast */
watch(error, (val) => {
  if (val) notification.error(val, errorDetail.value)
})

/** algorithm:read 持有者可管理（网格可点）；device_admin/guest 只读降级条；AUTH_MODE=off 全放行 */
const canManage = computed(() => can('algorithm:read'))

const readonlyLabel = computed(() => {
  const t = store.algorithmType
  if (!t) return '全部算法'
  const algo = definitions.value.find(a => a.type === t)
  return algo?.name ?? t
})

function paramSummary(algo: any) {
  return getAlgorithmParamSummary(algo)
}

async function handleSelect(type: string | null) {
  select(type)
  if (type === null) {
    notification.success('已恢复全部算法')
  } else {
    const algo = definitions.value.find(a => a.type === type)
    notification.success(`已切换全局算法为 ${algo?.name ?? type}`)
  }
}

onMounted(() => {
  if (canManage.value) load()
})
</script>
