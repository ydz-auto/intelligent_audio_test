<template>
  <Teleport to="body">
    <div v-if="visible" class="rhd2-overlay" @click.self="emit('close')">
      <div class="rhd2-drawer" @click.stop>
        <!-- 头部 -->
        <div class="rhd2-header">
          <h3 class="rhd2-title">
            <i class="fas fa-clock-rotate-left"></i> 复核历史 — {{ title || `任务 ${taskId}` }}
          </h3>
          <span v-if="loaded" class="rhd2-count">共 {{ totalCount }} 条</span>
          <button class="rhd2-close" @click="emit('close')" title="关闭">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <!-- 两个 Tab：人工复核 / AI 复核（19 规范 §4.3） -->
        <div class="rhd2-tabs">
          <button
            type="button"
            class="rhd2-tab"
            :class="{ active: tab === 'manual' }"
            @click="switchTab('manual')"
          >
            <i class="fas fa-clipboard-check"></i> 人工复核
          </button>
          <button
            type="button"
            class="rhd2-tab"
            :class="{ active: tab === 'ai' }"
            @click="switchTab('ai')"
          >
            <i class="fas fa-sparkles"></i> AI 复核
          </button>
        </div>

        <!-- 列表区 -->
        <div class="rhd2-body">
          <!-- 人工复核 Tab -->
          <template v-if="tab === 'manual'">
            <div v-if="manualLoading" class="rhd2-empty">
              <i class="fas fa-spinner fa-spin"></i>
              <p>正在加载复核历史…</p>
            </div>
            <div v-else-if="manualError" class="rhd2-empty rhd2-error">
              <p><i class="fas fa-circle-exclamation"></i> 复核历史加载失败</p>
              <button class="rhd2-retry" @click="loadManual">
                <i class="fas fa-rotate"></i> 重试
              </button>
            </div>
            <div v-else-if="manualItems.length === 0" class="rhd2-empty">
              <i class="fas fa-inbox"></i>
              <p>暂无复核记录</p>
            </div>
            <ul v-else class="rhd2-list">
              <li v-for="(item, idx) in manualItems" :key="idx" class="rhd2-item">
                <div class="rhd2-row">
                  <span class="rhd2-time">{{ formatTime(item.createdAt) }}</span>
                  <span class="rhd2-operator">
                    操作人 {{ item.createdByUserId != null ? `用户 #${item.createdByUserId}` : '—' }}
                  </span>
                  <span v-if="!props.caseId" class="rhd2-case" :title="caseLabel(item)">
                    {{ caseLabel(item) }}
                  </span>
                  <span class="rhd2-field">{{ fieldLabel(item.fieldName) }}</span>
                </div>
                <div class="rhd2-row rhd2-row--values">
                  <span class="rhd2-change">
                    <span>{{ statusLabel(item.fieldName, item.oldValue) ?? '—' }}</span>
                    <span class="rhd2-arrow"> → </span>
                    <span>{{ statusLabel(item.fieldName, item.newValue) ?? '—' }}</span>
                  </span>
                  <span v-if="item.comment" class="rhd2-comment" :title="item.comment">
                    {{ item.comment }}
                  </span>
                </div>
              </li>
            </ul>
          </template>

          <!-- AI 复核 Tab -->
          <template v-else>
            <div v-if="aiLoading" class="rhd2-empty">
              <i class="fas fa-spinner fa-spin"></i>
              <p>正在加载 AI 复核记录…</p>
            </div>
            <div v-else-if="aiError" class="rhd2-empty rhd2-error">
              <p><i class="fas fa-circle-exclamation"></i> AI 复核记录加载失败</p>
              <button class="rhd2-retry" @click="loadAi">
                <i class="fas fa-rotate"></i> 重试
              </button>
            </div>
            <div v-else-if="aiItems.length === 0" class="rhd2-empty">
              <i class="fas fa-sparkles"></i>
              <p>暂无 AI 复核记录</p>
            </div>
            <ul v-else class="rhd2-list">
              <li v-for="rec in aiItems" :key="rec.id" class="rhd2-item">
                <div class="rhd2-row">
                  <span class="rhd2-ai-status" :class="`rhd2-ai-status--${String(rec.status ?? 'unknown')}`">
                    <i class="fas fa-sparkles"></i>
                    {{ aiReviewStatusLabel(rec.status) }}
                  </span>
                  <span v-if="rec.status === 'completed' && rec.verdict" class="rhd2-ai-verdict">
                    {{ aiReviewVerdictLabel(rec.verdict) }}
                  </span>
                  <span v-if="rec.status === 'completed'" class="rhd2-ai-confidence">
                    置信度 {{ Math.round((rec.confidence?.value ?? 0) * 100) }}%（{{ rec.confidence?.label ?? '—' }}）
                  </span>
                  <span v-if="rec.adopted" class="rhd2-ai-adopted">
                    <i class="fas fa-check-circle"></i> 已采纳
                  </span>
                  <span v-else-if="rec.rejected" class="rhd2-ai-rejected">
                    <i class="fas fa-circle-xmark"></i> 已驳回
                  </span>
                </div>
                <div class="rhd2-row rhd2-row--meta">
                  <span class="rhd2-time">{{ formatTime(rec.createdAt) }}</span>
                  <span v-if="!props.caseId" class="rhd2-case" :title="rec.testCaseId ?? ''">{{ rec.testCaseId ?? '' }}</span>
                </div>
                <p v-if="rec.reasoning" class="rhd2-comment rhd2-comment--block" :title="rec.reasoning">
                  {{ rec.reasoning }}
                </p>
              </li>
            </ul>
          </template>
        </div>

        <!-- 底部 -->
        <div class="rhd2-footer">
          <button class="rhd2-close-btn" @click="emit('close')">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'

import { ref, watch, computed } from 'vue'
import { reviewApi } from '@/infrastructure/api/reviewApi'
import { aiReviewStatusLabel, aiReviewVerdictLabel } from '@/domain/model/review'
import type { ReviewHistoryItemDomain, AiReviewRecord } from '@/domain/model/review'

/**
 * 报告侧复核历史抽屉（19 规范 §4.3：人工复核 / AI 复核 两 Tab）。
 * 人工 Tab：GET /tasks/results/{task_id}/review-history（多次复核追加不覆盖）。
 * AI Tab：GET /tasks/results/{task_id}/ai-review-history（INT-800 真实端点，INT-1070 接线）。
 * 用例卡片入口按 caseId 过滤；记录状态（pending/running/completed/failed 及未知值）容错渲染。
 */
const props = defineProps<{
  visible: boolean
  taskId: string | number
  /** 用例级入口按 caseId 过滤；缺省任务级全量 */
  caseId?: string
  /** 标题用例名（用例卡片入口「复核历史 — {用例名}」；缺省任务名） */
  title?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const tab = ref<'manual' | 'ai'>('manual')

const manualLoading = ref(false)
const manualError = ref(false)
const manualHistory = ref<ReviewHistoryItemDomain[]>([])

const aiLoading = ref(false)
const aiError = ref(false)
const aiHistory = ref<AiReviewRecord[]>([])

const loaded = ref(false)

/** 后端按时间正序返回 → 展示侧倒序（最新在前）；按 caseId 过滤 */
const manualItems = computed(() =>
  manualHistory.value
    .filter((item) => !props.caseId || item.testCaseId === props.caseId)
    .slice()
    .reverse(),
)

const aiItems = computed(() =>
  aiHistory.value
    .filter((rec) => !props.caseId || (rec.testCaseId ?? '') === props.caseId)
    .slice()
    .reverse(),
)

const totalCount = computed(() => manualItems.value.length + aiItems.value.length)

async function loadManual() {
  manualLoading.value = true
  manualError.value = false
  try {
    manualHistory.value = await reviewApi.getReviewHistory(props.taskId)
  } catch (err) {
    console.error('加载复核历史失败:', err)
    manualError.value = true
  } finally {
    manualLoading.value = false
  }
}

async function loadAi() {
  aiLoading.value = true
  aiError.value = false
  try {
    aiHistory.value = await reviewApi.getAiReviewHistory(props.taskId)
  } catch (err) {
    console.error('加载 AI 复核记录失败:', err)
    aiError.value = true
  } finally {
    aiLoading.value = false
  }
}

function switchTab(next: 'manual' | 'ai') {
  tab.value = next
}

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    tab.value = 'manual'
    loaded.value = false
    Promise.all([loadManual(), loadAi()]).finally(() => {
      loaded.value = true
    })
  },
  { immediate: true },
)

function fieldLabel(field?: string | null): string {
  if (field === 'execution_status') return '执行状态'
  if (field === 'evaluation_status') return '评估状态'
  return field ?? ''
}

function statusLabel(field?: string | null, value?: string | null): string | null {
  if (value == null) return null
  if (field === 'execution_status') {
    const map: Record<string, string> = {
      completed: '已完成',
      failed: '执行失败',
      stopped: '已停止',
      skipped: '已跳过',
      pending: '待执行',
      queued: '排队中',
      running: '执行中',
    }
    return map[value] ?? value
  }
  if (field === 'evaluation_status') {
    const map: Record<string, string> = {
      completed: '已完成',
      failed: '评估失败',
      pending: '待评估',
      running: '评估中',
      calculating: '计算中',
      stopped: '已停止',
    }
    return map[value] ?? value
  }
  return value
}

function caseLabel(item: ReviewHistoryItemDomain): string {
  return item.testCaseId ?? ''
}

function formatTime(ts?: string | null): string {
  if (!ts) return '—'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
</script>

<style scoped>
.rhd2-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: color-mix(in srgb, var(--foreground) 30%, transparent);
}
.rhd2-drawer {
  position: absolute;
  top: 0;
  right: 0;
  height: 100%;
  width: min(500px, 94vw);
  background: var(--background);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
}
.rhd2-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.rhd2-title {
  margin: 0;
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.rhd2-title i {
  color: var(--primary);
}
.rhd2-count {
  font-size: 12px;
  color: var(--muted-foreground);
}
.rhd2-close {
  border: none;
  background: none;
  color: var(--muted-foreground);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.rhd2-close:hover {
  color: var(--foreground);
}
.rhd2-tabs {
  display: flex;
  gap: 4px;
  padding: 10px 20px 0;
  border-bottom: 1px solid var(--border);
}
.rhd2-tab {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted-foreground);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.rhd2-tab i {
  color: var(--muted-foreground);
}
.rhd2-tab.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}
.rhd2-tab.active i {
  color: var(--primary);
}
.rhd2-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.rhd2-empty {
  padding: 40px 16px;
  text-align: center;
  color: var(--muted-foreground);
  font-size: 13px;
}
.rhd2-empty i {
  font-size: 32px;
  color: var(--color-slate-300);
  margin-bottom: 8px;
  display: block;
}
.rhd2-empty p {
  margin: 4px 0;
}
.rhd2-error {
  color: var(--destructive);
}
.rhd2-retry {
  margin-top: 8px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--background);
  font-size: 12px;
  cursor: pointer;
}
.rhd2-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rhd2-item {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--muted) 20%, transparent);
}
.rhd2-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.rhd2-row--values {
  margin-top: 4px;
}
.rhd2-row--meta {
  margin-top: 4px;
}
.rhd2-time {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--muted-foreground);
}
.rhd2-operator {
  color: var(--muted-foreground);
}
.rhd2-case {
  padding: 0 6px;
  border-radius: var(--radius-tag);
  background: var(--color-slate-100);
  color: var(--foreground);
  font-size: 11px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rhd2-field {
  padding: 0 6px;
  border-radius: var(--radius-tag);
  background: var(--color-slate-200);
  color: var(--foreground);
  font-size: 11px;
}
.rhd2-change {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  color: var(--foreground);
}
.rhd2-arrow {
  color: var(--destructive);
}
.rhd2-comment {
  color: var(--muted-foreground);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rhd2-comment--block {
  margin-top: 4px;
  max-width: none;
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.rhd2-ai-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
}
.rhd2-ai-status i {
  font-size: 10px;
}
.rhd2-ai-status--completed {
  background: color-mix(in srgb, var(--success) 15%, transparent);
  color: var(--success-dark, var(--success));
}
.rhd2-ai-status--running,
.rhd2-ai-status--pending {
  background: color-mix(in srgb, var(--warning) 15%, transparent);
  color: var(--warning-dark, var(--foreground));
}
.rhd2-ai-status--failed {
  background: color-mix(in srgb, var(--destructive) 12%, transparent);
  color: var(--destructive);
}
.rhd2-ai-status--canceled {
  background: var(--muted);
  color: var(--muted-foreground);
}
.rhd2-ai-verdict {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  font-size: 11px;
  color: var(--foreground);
}
.rhd2-ai-confidence {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--muted-foreground);
}
.rhd2-ai-adopted {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--success-dark, var(--success));
}
.rhd2-ai-rejected {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--destructive);
}
.rhd2-footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}
.rhd2-close-btn {
  padding: 6px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--background);
  color: var(--foreground);
  font-size: 13px;
  cursor: pointer;
}
.rhd2-close-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}
</style>
