<template>
  <Teleport to="body">
    <div class="rhd-overlay" @click.self="emit('close')">
      <div class="rhd-drawer">
        <!-- 头部 -->
        <div class="rhd-header">
          <h3><i class="fas fa-clock-rotate-left"></i> 复核历史 — {{ taskName || `任务 ${taskId}` }}</h3>
          <span v-if="!loading && !error && items.length" class="rhd-count">共 {{ items.length }} 条</span>
          <button class="rhd-close" @click="emit('close')"><i class="fas fa-times"></i></button>
        </div>

        <!-- 列表 -->
        <div class="rhd-body">
          <div v-if="loading" class="rhd-empty"><i class="fas fa-spinner fa-spin"></i> 正在加载复核历史…</div>
          <div v-else-if="error" class="rhd-empty rhd-error">
            <p><i class="fas fa-circle-exclamation"></i> 复核历史加载失败</p>
            <button class="rhd-retry" @click="loadHistory"><i class="fas fa-rotate"></i> 重试</button>
          </div>
          <div v-else-if="items.length === 0" class="rhd-empty">
            <i class="fas fa-inbox"></i>
            <p>暂无复核记录</p>
          </div>
          <ul v-else class="rhd-list">
            <li v-for="item in items" :key="item.id" class="rhd-item">
              <div class="rhd-row">
                <span class="rhd-time">{{ formatDateTime(item.createdAt) }}</span>
                <span class="rhd-operator">操作人 {{ item.createdByUserId != null ? `用户 #${item.createdByUserId}` : '—' }}</span>
                <span class="rhd-case" :title="caseLabel(item)">
                  {{ caseLabel(item) }}
                </span>
              </div>
              <div class="rhd-row rhd-row--values">
                <span class="rhd-field">{{ fieldLabel(item.fieldName) }}</span>
                <span class="rhd-change">
                  <span>{{ item.oldValue ?? '—' }}</span>
                  <span class="rhd-arrow"> → </span>
                  <span>{{ item.newValue ?? '—' }}</span>
                </span>
                <span v-if="item.comment" class="rhd-comment" :title="item.comment">{{ item.comment }}</span>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

/**
 * 任务复核历史抽屉（19 规范 §3.4，右侧 Sheet 形态）。
 * 数据源 GET /tasks/results/{task_id}/review-history（task:read；多次复核追加不覆盖）。
 * 行 = 时间（mono）+ 操作人（用户 #id，AUTH_MODE=off 显「—」）+ 用例名 + 字段徽章
 *   + 改判 {原值} → {新值}（mono，destructive 箭头）+ 备注（截断 Tooltip）。
 * 空态「暂无复核记录」；加载中提示；单条复核弹窗「查看复核历史」link 复用（按 resultId 过滤）。
 */
import { ref, onMounted, computed } from 'vue'
import { tasksApi } from '../../../infrastructure/api'
import type { ReviewHistoryItem } from '../../../infrastructure/api/tasksApi'

const props = defineProps<{
  taskId: string | number
  taskName?: string
  /** 用例名映射（testCaseId → 名称；缺省显示 testCaseId） */
  caseNameMap?: Record<string, string>
  /** 按结果过滤（单条复核弹窗「查看复核历史」link 入口） */
  resultId?: number
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(true)
const error = ref(false)
const history = ref<ReviewHistoryItem[]>([])

/** 后端按时间正序返回 → 展示侧倒序（最新在前，§3.4「服务端按时间倒序」口径） */
const items = computed(() =>
  history.value
    .filter((item) => (props.resultId ? item.resultId === props.resultId : true))
    .slice()
    .reverse(),
)

async function loadHistory() {
  loading.value = true
  error.value = false
  try {
    history.value = await tasksApi.getReviewHistory(props.taskId)
  } catch (err) {
    console.error('加载复核历史失败:', err)
    error.value = true
  } finally {
    loading.value = false
  }
}

function fieldLabel(field?: string | null): string {
  return field === 'evaluation_status' ? '评估状态' : '执行状态'
}

/** 用例名（缺省显示 testCaseId；null 容错为空串） */
function caseLabel(item: ReviewHistoryItem): string {
  const id = item.testCaseId ?? ''
  return props.caseNameMap?.[id] ?? id ?? ''
}

function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  // 2026-10-09T20:21:28 → 2026-10-09 20:21:28（mono 展示口径）
  return value.replace('T', ' ').slice(0, 19)
}

onMounted(loadHistory)
</script>

<style scoped>
.rhd-overlay {
  position: fixed;
  inset: 0;
  z-index: 1050;
  background: color-mix(in srgb, var(--color-black) 30%, transparent);
}
.rhd-drawer {
  position: absolute;
  top: 0;
  right: 0;
  height: 100%;
  width: min(480px, 92vw);
  background: var(--background, #fff);
  box-shadow: var(--shadow-lg, 0 8px 24px rgb(0 0 0 / 0.12));
  display: flex;
  flex-direction: column;
}
.rhd-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, var(--color-slate-200));
}
.rhd-header h3 {
  margin: 0;
  flex: 1;
  font-size: 16px;
  font-weight: var(--font-weight-semibold, 600);
  color: var(--foreground, var(--foreground));
  display: flex;
  align-items: center;
  gap: 8px;
}
.rhd-header h3 i {
  color: var(--primary, var(--primary));
}
.rhd-count {
  font-size: 12px;
  color: var(--muted-foreground, var(--color-slate-500));
}
.rhd-close {
  border: none;
  background: none;
  color: var(--muted-foreground, var(--color-slate-500));
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.rhd-close:hover {
  color: var(--primary, var(--primary));
}
.rhd-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.rhd-empty {
  padding: 40px 16px;
  text-align: center;
  color: var(--muted-foreground, var(--color-slate-400));
  font-size: 13px;
}
.rhd-empty i {
  font-size: 32px;
  color: var(--color-slate-300, #cbd5e1);
  margin-bottom: 8px;
  display: block;
}
.rhd-empty p {
  margin: 4px 0;
}
.rhd-error {
  color: var(--destructive, #dc2626);
}
.rhd-retry {
  margin-top: 8px;
  padding: 4px 12px;
  border: 1px solid var(--border, var(--color-slate-200));
  border-radius: var(--radius-control);
  background: var(--background, #fff);
  font-size: 12px;
  cursor: pointer;
}
.rhd-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rhd-item {
  padding: 10px 12px;
  border: 1px solid var(--border, var(--color-slate-200));
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--muted) 20%, transparent);
}
.rhd-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.rhd-row--values {
  margin-top: 4px;
}
.rhd-time {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--muted-foreground, var(--color-slate-500));
}
.rhd-operator {
  color: var(--muted-foreground, var(--color-slate-500));
}
.rhd-case {
  padding: 0 6px;
  border-radius: var(--radius-tag);
  background: var(--color-slate-100);
  color: var(--foreground, var(--color-slate-700));
  font-size: 11px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rhd-field {
  padding: 0 6px;
  border-radius: var(--radius-tag);
  background: var(--color-slate-200);
  color: var(--foreground, var(--color-slate-700));
  font-size: 11px;
}
.rhd-change {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}
.rhd-arrow {
  color: var(--destructive, #dc2626);
}
.rhd-comment {
  color: var(--muted-foreground, var(--color-slate-500));
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
