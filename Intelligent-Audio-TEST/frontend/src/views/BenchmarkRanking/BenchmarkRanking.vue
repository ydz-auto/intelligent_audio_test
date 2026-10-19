<template>
  <div class="benchmark-ranking-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-chart-simple"></i>
          排行榜
        </h2>
        <p class="page-description">多个厂商模型/APP/API 在同一标准化环境、同一测试集与指标下同时实测，按指标与场景生成名次，横向看清业界水平。</p>
      </div>
    </div>

    <BenchmarkRankingHero :active-category="store.category" @select="handleCategorySelect" />

    <!-- INT-745：页内算法卡片网格（每算法一张大卡；不渲染右上角全局切换器；按算法过滤待后端立项） -->
    <AlgorithmCardGrid />

    <BenchmarkRankingFilters
      :suite="store.suite"
      :metric-code="store.metricCode"
      :source="store.source"
      :subject-name="store.subjectName"
      :suite-options="store.suiteOptions"
      :metric-options="store.metricOptions"
      :has-active-filters="store.hasActiveFilters"
      :has-compute-permission="canCompute"
      :computing="store.computing"
      @update:suite="handleSuiteChange"
      @update:metric-code="handleMetricChange"
      @update:source="handleSourceChange"
      @update:subject-name="handleSubjectNameChange"
      @subject-search="handleSubjectSearch"
      @reset="handleReset"
      @compute="handleCompute"
    />

    <!-- 加载态：骨架屏 -->
    <div v-if="store.loading && !store.rows.length" class="loading-state" aria-label="排行加载中">
      <div class="skeleton skeleton-hero"></div>
      <div class="skeleton skeleton-filters"></div>
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
    </div>

    <!-- 错误态 -->
    <div v-else-if="store.error && !store.rows.length" class="error-state">
      <h4 class="error-title">排行加载失败</h4>
      <p class="error-desc">{{ store.error }}</p>
      <button type="button" class="btn btn-retry" @click="store.load">
        <i class="fas fa-rotate-right"></i> 重试
      </button>
    </div>

    <!-- 空态 -->
    <div v-else-if="!store.loading && !store.rows.length" class="empty-state">
      <i class="fas fa-trophy empty-icon" aria-hidden="true"></i>
      <h4 class="empty-title">暂无排行数据</h4>
      <p class="empty-desc">
        尚未计算排行，或当前筛选条件下没有数据。
        <template v-if="!canCompute">请联系管理员计算排行。</template>
      </p>
      <button
        v-if="canCompute"
        type="button"
        class="btn btn-compute"
        @click="handleCompute"
      >
        <i class="fas fa-calculator"></i> 立即计算
      </button>
    </div>

    <!-- 数据态：指标组卡 ×N -->
    <div v-else class="group-list">
      <MetricGroupCard
        v-for="group in store.groups"
        :key="`${group.category}-${group.metricCode}-${group.scenarioKey}`"
        :group="group"
        :highlighted-subject="store.subjectName || undefined"
        :show-report="canViewReport"
        @select-subject="handleSelectSubject"
      />
      <p class="algorithm-note">榜单全量展示，按算法过滤待后端立项。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/progress.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBenchmarkStore } from '../../store/benchmarkStore'
import { useAuthStore } from '../../store/authStore'
import { useNotification } from '../../composables/modal/useNotification'
import { BenchmarkCategoryTabLabels, BenchmarkSource, type BenchmarkCategoryType, type BenchmarkSourceType } from '../../domain/enums'
import BenchmarkRankingHero from '../../components/benchmark/BenchmarkRankingHero.vue'
import BenchmarkRankingFilters from '../../components/benchmark/BenchmarkRankingFilters.vue'
import MetricGroupCard from '../../components/benchmark/MetricGroupCard.vue'
import AlgorithmCardGrid from './AlgorithmCardGrid.vue'

const store = useBenchmarkStore()
const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const notification = useNotification()

/** 权限判定（INT-429 seed_rbac 实测码名）；computed 包装使权限刷新后联动 */
const canCompute = computed(() => authStore.hasPermission('benchmark:ranking:compute'))
const canViewReport = computed(() => authStore.hasPermission('report:read'))

/** 类别页签合法值（含全部） */
const CATEGORY_VALUES: ReadonlyArray<'' | BenchmarkCategoryType> = [
  '',
  ...Object.keys(BenchmarkCategoryTabLabels).filter((k) => k !== '') as BenchmarkCategoryType[],
]

function normalizeCategory(value: unknown): '' | BenchmarkCategoryType {
  return CATEGORY_VALUES.includes(value as '' | BenchmarkCategoryType) ? (value as '' | BenchmarkCategoryType) : ''
}

/** 来源筛选合法值（接口仅接受 platform_test / external_import） */
const SOURCE_VALUES: ReadonlyArray<'' | BenchmarkSourceType> = ['', BenchmarkSource.PLATFORM_TEST, BenchmarkSource.EXTERNAL_IMPORT]

function normalizeSource(value: unknown): '' | BenchmarkSourceType {
  return SOURCE_VALUES.includes(value as '' | BenchmarkSourceType) ? (value as '' | BenchmarkSourceType) : ''
}

/** 从 URL query 初始化筛选（刷新/分享可还原） */
function applyQueryToFilters() {
  const q = route.query
  store.category = normalizeCategory(q.category)
  store.suite = typeof q.suite === 'string' ? q.suite : ''
  store.metricCode = typeof q.metricCode === 'string' ? q.metricCode : ''
  store.source = normalizeSource(q.source)
  store.subjectName = typeof q.subjectName === 'string' ? q.subjectName : ''
}

/** 筛选变化 → URL query 合并写入（照 newAPI navigate({search: prev => ({...prev})}) 模式） */
function syncQuery() {
  router.replace({
    query: {
      ...(store.category ? { category: store.category } : {}),
      ...(store.suite ? { suite: store.suite } : {}),
      ...(store.metricCode ? { metricCode: store.metricCode } : {}),
      ...(store.source ? { source: store.source } : {}),
      ...(store.subjectName ? { subjectName: store.subjectName } : {}),
    },
  })
}

// ===== 筛选联动 =====

function handleCategorySelect(category: '' | BenchmarkCategoryType) {
  store.category = category
  syncQuery()
  store.load()
}

function handleSuiteChange(value: string) {
  store.suite = value
  syncQuery()
  store.load()
}

function handleMetricChange(value: string) {
  store.metricCode = value
  syncQuery()
  store.load()
}

function handleSourceChange(value: string) {
  store.source = value as '' | BenchmarkSourceType
  syncQuery()
  store.load()
}

function handleSubjectNameChange(value: string) {
  // 输入即更新内存态；URL 写入与重取交给防抖后的 subjectSearch（避免每键触发路由变化/侧栏折叠）
  store.subjectName = value
}

function handleSubjectSearch(_value: string) {
  syncQuery()
  store.load()
}

function handleSelectSubject(subject: string) {
  store.subjectName = subject
  syncQuery()
  store.load()
}

function handleReset() {
  store.resetFilters()
  syncQuery()
  store.load()
}

function handleCompute() {
  store.computeRanking().then((result) => {
    if (result.ok) {
      notification.success(result.message)
      store.load()
    } else {
      notification.error(result.message)
      notification.info('上一次排行结果仍可查看')
    }
  })
}

onMounted(() => {
  applyQueryToFilters()
  store.loadMappings()
  store.load()
})
</script>

<style scoped>
.benchmark-ranking-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-header .header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.page-description {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
}
.loading-state {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.skeleton {
  border-radius: var(--radius-lg);
  background: var(--muted);
  animation: pulse 1.5s ease-in-out infinite;
}
.skeleton-hero {
  height: 96px;
}
.skeleton-filters {
  height: 48px;
}
.skeleton-card {
  height: 320px;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 24px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  text-align: center;
  background: var(--card);
}
.error-title,
.empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}
.error-desc,
.empty-desc {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
  max-width: 28rem;
}
.empty-icon {
  font-size: 32px;
  color: var(--warning);
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
}
.btn-retry {
  background: transparent;
  border-color: var(--border);
  color: var(--foreground);
}
.btn-retry:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.btn-compute {
  background: var(--primary);
  color: var(--primary-foreground);
}
.group-list {
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.algorithm-note {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
  text-align: right;
}
</style>
