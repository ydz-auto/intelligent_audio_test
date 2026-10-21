<template>
  <div class="pts">
    <h3 class="pts-title">挑选 · 阶段 1：选择任务</h3>

    <!-- 搜索 + 已选计数 -->
    <div class="pts-toolbar">
      <div class="pts-search">
        <i class="fas fa-search pts-search-icon"></i>
        <input
          v-model="search"
          class="pts-input"
          placeholder="搜索任务名称"
          aria-label="搜索任务名称"
        />
      </div>
      <span class="pts-info">
        已选 <b>{{ selectedTaskIds.size }}</b> 个任务
      </span>
      <span class="pts-hint">仅已完成、执行失败、已停止的终态任务可挑选</span>
    </div>

    <!-- 任务列表 -->
    <div class="pts-list">
      <div v-if="loading" class="pts-empty">
        <i class="fas fa-spinner fa-spin"></i>
        <p>正在加载可挑选任务…</p>
      </div>
      <div v-else-if="isError" class="pts-empty pts-error">
        <i class="fas fa-exclamation-triangle"></i>
        <p>可挑选任务加载失败，请重试</p>
        <button class="pts-btn" @click="onRetry"><i class="fas fa-redo"></i> 重试</button>
      </div>
      <div v-else-if="filtered.length === 0" class="pts-empty">
        <i class="fas fa-inbox"></i>
        <p>{{ kw ? '没有符合搜索条件的任务' : '暂无可挑选的终态任务' }}</p>
        <p class="pts-empty-hint">仅已完成、执行失败、已停止的终态任务可挑选</p>
      </div>
      <div v-else class="pts-rows">
        <div
          v-for="task in filtered"
          :key="task.taskId"
          class="pts-row"
          :class="{ 'pts-row--selected': selectedTaskIds.has(task.taskId) }"
        >
          <label class="pts-check" @click.stop>
            <input
              type="checkbox"
              class="pts-checkbox"
              :checked="selectedTaskIds.has(task.taskId)"
              :aria-label="`选择任务 ${task.taskName}`"
              @change="onToggle(task.taskId)"
            />
          </label>
          <span class="pts-name" :title="task.taskName">{{ task.taskName }}</span>
          <span class="pts-status" :class="statusClass(task.executionStatus)">
            {{ statusLabel(task.executionStatus) }}
          </span>
          <span class="pts-count">{{ task.count }} 条</span>
          <span class="pts-time">{{ formatTime(task.createdAt) }}</span>
        </div>
      </div>
    </div>

    <!-- 底部：全选当前筛选 / 清空 / 下一步 -->
    <div class="pts-footer">
      <div class="pts-footer-left">
        <button class="pts-btn" :disabled="filtered.length === 0" @click="onSelectAll(filtered.map((t) => t.taskId))">
          <i class="fas fa-check-double"></i> 全选当前筛选
        </button>
        <button class="pts-btn" :disabled="selectedTaskIds.size === 0" @click="onClear">
          <i class="fas fa-eraser"></i> 清空
        </button>
      </div>
      <button
        class="pts-btn pts-btn-primary"
        :disabled="selectedTaskIds.size === 0"
        @click="onNext"
      >
        下一步：选择结果（{{ selectedTaskIds.size }}） <i class="fas fa-arrow-right"></i>
      </button>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * 挑选阶段 1 · 选择任务（18_挑选合并交互重设计.md §3.8.2，INT-1047/INT-1110）。
 * 搜索（任务名）+ 多选 + 全选当前筛选 + 清空 + 下一步：选择结果。
 * 任务行 = Checkbox + 任务名 + 执行状态徽章 + 结果计数「{n} 条」+ 创建时间（mono）。
 * 数据源 = 候选行聚合的可挑选终态任务集合（按状态/名称排序）。
 */

/** 阶段 1 任务行（候选行按 taskId 聚合） */
export interface PickTaskRow {
  taskId: number;
  taskName: string;
  executionStatus: string;
  createdAt: string | null;
  count: number;
}

/** 终态排序权重（§3.8.2 按状态/名称排序：已完成 → 执行失败 → 已停止） */
export function getTaskStatusOrder(status: string): number {
  switch (status) {
    case 'completed': return 0;
    case 'failed': return 1;
    case 'stopped': return 2;
    default: return 3;
  }
}
</script>

<script setup lang="ts">
import { ref, computed } from 'vue';

const props = defineProps<{
  tasks: PickTaskRow[];
  selectedTaskIds: ReadonlySet<number>;
  loading: boolean;
  isError: boolean;
  onRetry: () => void;
  onToggle: (taskId: number) => void;
  /** 全选当前筛选（传入搜索命中集） */
  onSelectAll: (taskIds: number[]) => void;
  onClear: () => void;
  onNext: () => void;
}>();

const search = ref('');
const kw = computed(() => search.value.trim().toLowerCase());

const filtered = computed(() => {
  if (!kw.value) return props.tasks;
  return props.tasks.filter((t) => t.taskName.toLowerCase().includes(kw.value));
});

function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成';
    case 'failed': return '执行失败';
    case 'stopped': return '已停止';
    default: return status || '-';
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'completed': return 'pts-status--completed';
    case 'failed': return 'pts-status--failed';
    case 'stopped': return 'pts-status--stopped';
    default: return '';
  }
}

/** 创建时间（mono 口径，YYYY-MM-DD HH:mm） */
function formatTime(iso?: string | null): string {
  if (!iso) return '';
  const t = iso.replace('T', ' ').slice(0, 16);
  return t;
}
</script>

<style scoped>
.pts {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 320px;
}
.pts-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground, #1e293b);
}
.pts-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.pts-search {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.pts-search-icon {
  position: absolute;
  left: 10px;
  color: var(--color-slate-400, #94a3b8);
  font-size: 12px;
}
.pts-input {
  height: 34px;
  padding: 0 10px 0 30px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-md);
  font-size: 13px;
  background: #fff;
  color: var(--foreground, #1e293b);
  width: 220px;
}
.pts-input:focus {
  outline: none;
  border-color: var(--primary, #ff6a00);
}
.pts-info {
  font-size: 13px;
  color: var(--color-slate-500, #64748b);
}
.pts-info b {
  color: var(--primary, #ff6a00);
  font-size: 14px;
}
.pts-hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-slate-400, #94a3b8);
}
.pts-list {
  flex: 1;
  min-height: 200px;
  max-height: 380px;
  overflow-y: auto;
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
  padding: 4px 0;
}
.pts-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--color-slate-400, #94a3b8);
}
.pts-empty i {
  font-size: 36px;
  color: var(--color-slate-300, #cbd5e1);
  margin-bottom: 8px;
}
.pts-empty p {
  margin: 4px 0;
  font-size: 13px;
}
.pts-empty-hint {
  font-size: 12px !important;
  color: var(--color-slate-400, #94a3b8);
}
.pts-rows {
  display: flex;
  flex-direction: column;
  padding: 4px;
}
.pts-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  font-size: 13px;
  transition: background 0.15s ease;
}
.pts-row:hover {
  background: var(--color-slate-50, #f8fafc);
}
.pts-row--selected {
  background: var(--accent, #fff7ed);
}
.pts-check {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}
.pts-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary, #ff6a00);
}
.pts-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: var(--foreground, #1e293b);
}
.pts-status {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
}
.pts-status--completed { background: var(--color-emerald-100); color: var(--color-emerald-600); }
.pts-status--failed { background: var(--color-red-100); color: var(--color-red-600); }
.pts-status--stopped { background: var(--color-gray-100); color: var(--color-gray-500); }
.pts-count {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-500, #64748b);
  font-size: 11px;
  font-weight: 500;
}
.pts-time {
  flex-shrink: 0;
  color: var(--color-slate-400, #94a3b8);
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  white-space: nowrap;
}
.pts-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.pts-footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pts-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-md);
  background: #fff;
  color: var(--foreground, #1e293b);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.pts-btn:hover {
  border-color: var(--primary, #ff6a00);
  color: var(--primary, #ff6a00);
}
.pts-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.pts-btn-primary {
  background: var(--primary, #ff6a00);
  border-color: var(--primary, #ff6a00);
  color: #fff;
}
.pts-btn-primary:hover {
  background: var(--primary-hover, #e55d00);
  color: #fff;
}
</style>
