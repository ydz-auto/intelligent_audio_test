<template>
  <span class="case-review-badge" title="该用例存在人工复核结果" @click.stop="openDetail">
    <i class="fas fa-clipboard-check"></i>
    <span>人工复核</span>
    <span class="badge-count" v-if="count > 0">{{ count }}</span>
  </span>

  <!-- 复核明细弹窗 -->
  <teleport to="body">
    <div class="review-detail-overlay" v-if="showDetail" @click.self="closeDetail">
      <div class="review-detail-dialog" @click.stop>
        <div class="review-detail-header">
          <h3 class="review-detail-title">复核明细 — {{ caseName }}</h3>
          <button class="review-detail-close" @click="closeDetail" title="关闭">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="review-detail-body">
          <div v-if="!items.length" class="review-detail-empty">
            暂无复核记录
          </div>
          <div v-else class="review-detail-list">
            <div v-for="(item, idx) in items" :key="idx" class="review-detail-item">
              <div class="review-item-head">
                <span class="review-item-time">{{ formatTime(item.createdAt) }}</span>
                <span class="review-item-field">{{ fieldLabel(item.fieldName) }}</span>
              </div>
              <div class="review-item-change">
                <span class="change-old">{{ item.oldValue ?? '—' }}</span>
                <span class="change-arrow"><i class="fas fa-arrow-right"></i></span>
                <span class="change-new">{{ item.newValue }}</span>
              </div>
              <div class="review-item-comment" v-if="item.comment">{{ item.comment }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
/**
 * 用例卡片「人工复核」Badge（§4.1 卡片标记）+ 卡片内复核明细弹窗（§4.1 明细）。
 *
 * 数据：来源任务复核历史按 test_case_id 聚合（reviewApi.getReviewHistory，真实）。
 */
import { ref } from 'vue'
import type { ReviewHistoryItemDomain } from '@/domain/model/review'

const props = defineProps<{
  caseName: string
  count: number
  items: ReviewHistoryItemDomain[]
}>()

const showDetail = ref(false)

function openDetail() {
  showDetail.value = true
}
function closeDetail() {
  showDetail.value = false
}

const fieldLabel = (field?: string) => {
  if (field === 'execution_status') return '执行状态'
  if (field === 'evaluation_status') return '评估状态'
  return field ?? ''
}

const formatTime = (ts?: string | null) => {
  if (!ts) return '—'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
</script>

<style scoped>
.case-review-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 500;
  color: var(--primary);
  background: var(--accent);
  border: 1px solid color-mix(in srgb, var(--primary) 25%, transparent);
  cursor: pointer;
  transition: background 0.2s ease;
}
.case-review-badge:hover {
  background: color-mix(in srgb, var(--primary) 18%, transparent);
}
.badge-count {
  font-size: 11px;
  color: var(--muted-foreground);
}
.review-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--foreground) 40%, transparent);
}
.review-detail-dialog {
  width: 480px;
  max-width: calc(100vw - 32px);
  background: var(--background);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
  max-height: 80vh;
}
.review-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}
.review-detail-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--foreground);
}
.review-detail-close {
  background: transparent;
  border: none;
  color: var(--muted-foreground);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.review-detail-close:hover {
  color: var(--foreground);
}
.review-detail-body {
  padding: 12px 18px;
  overflow-y: auto;
}
.review-detail-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--muted-foreground);
  font-size: 13px;
}
.review-detail-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.review-detail-item {
  background: var(--muted);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.review-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}
.review-item-time {
  color: var(--muted-foreground);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}
.review-item-field {
  color: var(--foreground);
  font-weight: 500;
}
.review-item-change {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.change-old {
  color: var(--muted-foreground);
  text-decoration: line-through;
}
.change-arrow {
  color: var(--destructive);
  font-size: 11px;
}
.change-new {
  color: var(--foreground);
  font-weight: 600;
}
.review-item-comment {
  font-size: 12px;
  color: var(--muted-foreground);
  word-break: break-word;
}
</style>
