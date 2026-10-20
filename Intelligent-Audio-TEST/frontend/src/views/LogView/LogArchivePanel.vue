<!--
  purpose: LogView 日志归档管理面板（INT-548）。
  MVC role: View（Presentation）。
  状态/动作收敛在 logArchive.ts composable（Application），本组件只做展示与事件触发。
  操作类按钮按 log:manage 权限门控（与既有 C2 口径一致，admin 可全操作）。
-->
<template>
  <div class="log-archive-panel">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">
          <i class="fas fa-archive"></i>
          日志归档管理
        </h3>
      </div>
      <div class="card-body log-archive-body">
        <!-- 归档状态（GET /logs/archive/status） -->
        <section class="archive-section archive-status-section" data-testid="archive-status">
          <h4 class="archive-section-title">归档状态</h4>
          <div class="archive-status-grid">
            <div class="archive-stat">
              <span class="archive-stat-label">总日志</span>
              <span class="archive-stat-value">{{ status.totalLogs }}</span>
            </div>
            <div class="archive-stat">
              <span class="archive-stat-label">热日志</span>
              <span class="archive-stat-value">{{ status.hotLogs }}</span>
            </div>
            <div class="archive-stat">
              <span class="archive-stat-label">冷日志</span>
              <span class="archive-stat-value">{{ status.coldLogs }}</span>
            </div>
            <div class="archive-stat">
              <span class="archive-stat-label">任务归档文件</span>
              <span class="archive-stat-value">{{ status.taskArchives }}</span>
            </div>
            <div class="archive-stat">
              <span class="archive-stat-label">用例归档文件</span>
              <span class="archive-stat-value">{{ status.caseArchives }}</span>
            </div>
            <div class="archive-stat">
              <span class="archive-stat-label">其他归档文件</span>
              <span class="archive-stat-value">{{ status.otherArchives }}</span>
            </div>
            <div class="archive-stat archive-stat--wide">
              <span class="archive-stat-label">归档目录</span>
              <span class="archive-stat-value archive-dir">{{ status.archiveDir || '-' }}</span>
            </div>
          </div>
          <p v-if="statusLoading" class="archive-empty-hint">归档状态加载中...</p>
          <p v-if="statusError" class="archive-result-message archive-error">{{ statusError }}</p>
        </section>

        <!-- 触发归档（POST /logs/archive） -->
        <section class="archive-section archive-trigger-section" data-testid="archive-trigger">
          <h4 class="archive-section-title">触发归档</h4>
          <div class="archive-action-row">
            <label class="archive-field">
              <span class="archive-field-label">保留最近天数</span>
              <input
                class="form-input-sm archive-days-input"
                type="number"
                min="1"
                v-model.number="archiveDays"
                :disabled="!canManage"
              />
            </label>
            <label class="archive-checkbox">
              <input type="checkbox" v-model="archiveDryRun" :disabled="!canManage" />
              <span>仅预览（dry_run）</span>
            </label>
            <button
              class="btn btn-primary"
              data-testid="archive-trigger-btn"
              :disabled="!canManage || resultLoading"
              @click="triggerArchive"
            >
              <i class="fas fa-archive btn-icon"></i>
              <span>{{ resultLoading ? '归档中...' : (archiveDryRun ? '预览归档' : '触发归档') }}</span>
            </button>
          </div>
          <p v-if="result?.message" class="archive-result-message">{{ result.message }}</p>
        </section>

        <!-- 已归档日志列表（GET /logs/archive/logs） -->
        <section class="archive-section archived-logs-section" data-testid="archived-logs">
          <h4 class="archive-section-title">已归档日志</h4>
          <div class="archive-action-row">
            <label class="archive-field">
              <span class="archive-field-label">任务ID</span>
              <input
                class="form-input-sm"
                type="number"
                placeholder="留空则按用例ID"
                v-model.number="archivedQuery.taskId"
              />
            </label>
            <label class="archive-field">
              <span class="archive-field-label">用例ID</span>
              <input
                class="form-input-sm"
                type="text"
                placeholder="留空则按任务ID"
                v-model="archivedQuery.testCaseId"
              />
            </label>
            <button
              class="btn btn-secondary"
              data-testid="archived-query-btn"
              :disabled="archivedLoading"
              @click="queryArchivedLogs"
            >
              <i class="fas fa-search btn-icon"></i>
              <span>{{ archivedLoading ? '查询中...' : '查询已归档日志' }}</span>
            </button>
            <button class="btn btn-text" @click="clearArchivedQuery">清空</button>
          </div>
          <p v-if="archivedError" class="archive-result-message archive-error">{{ archivedError }}</p>
          <p v-if="archivedLogs.length" class="archived-count-hint">共 {{ archivedTotal }} 条已归档日志</p>
          <div class="archived-logs-table" v-if="archivedLogs.length">
            <table class="data-table archive-log-table">
              <thead>
                <tr>
                  <th style="width: 160px;">时间</th>
                  <th style="width: 90px;">级别</th>
                  <th style="width: 110px;">模块</th>
                  <th style="width: 90px;">任务ID</th>
                  <th style="width: 130px;">用例ID</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="log in archivedLogs" :key="log.id">
                  <td>{{ formatLogTime(log.time !== undefined && log.time !== null ? String(log.time) : '', 'datetime') }}</td>
                  <td><span class="log-level" :class="log.level">{{ (log.level || 'info').toUpperCase() }}</span></td>
                  <td>{{ log.module || '-' }}</td>
                  <td>{{ log.taskId ?? '-' }}</td>
                  <td>{{ log.testCaseId ?? '-' }}</td>
                  <td class="archived-log-content" :title="log.content">{{ log.content }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="archive-empty-hint">暂无已归档日志，请按任务ID/用例ID查询。</p>
        </section>

        <!-- 归档文件下载/删除（GET/DELETE /logs/archive/{filename}） -->
        <section class="archive-section archive-file-section" data-testid="archive-file-ops">
          <h4 class="archive-section-title">归档文件操作</h4>
          <div class="archive-action-row">
            <label class="archive-field archive-filename-field">
              <span class="archive-field-label">归档文件</span>
              <input
                class="form-input"
                type="text"
                placeholder="如 2026-10-15.json（归档文件名末段）"
                v-model="archiveFilename"
              />
            </label>
            <button
              class="btn btn-secondary"
              data-testid="archive-download-btn"
              :disabled="!archiveFilename || fileBusy"
              @click="downloadArchive(archiveFilename)"
            >
              <i class="fas fa-download btn-icon"></i>
              <span>下载</span>
            </button>
            <button
              class="btn btn-danger"
              data-testid="archive-delete-btn"
              :disabled="!canManage || !archiveFilename || fileBusy"
              @click="deleteArchive(archiveFilename)"
            >
              <i class="fas fa-trash-alt btn-icon"></i>
              <span>删除</span>
            </button>
          </div>
          <p class="archive-file-hint">下载需 <code>log:read</code>，删除需 <code>log:manage</code>；输入归档文件名（逻辑 key 末段，如 2026-10-15.json），带斜杠的整串 key 会取末段。</p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { onMounted } from 'vue';
import { formatLogTime } from '../../utils/timeFormat';
import { useLogArchive } from './logArchive';

const {
  status,
  statusLoading,
  statusError,
  archiveDays,
  archiveDryRun,
  result,
  resultLoading,
  archivedQuery,
  archivedLogs,
  archivedTotal,
  archivedLoading,
  archivedError,
  archiveFilename,
  fileBusy,
  canManage,
  loadStatus,
  triggerArchive,
  queryArchivedLogs,
  clearArchivedQuery,
  downloadArchive,
  deleteArchive,
} = useLogArchive();

onMounted(() => {
  loadStatus();
});
</script>

<style scoped>
.log-archive-panel {
  margin-bottom: var(--spacing-xl);
  width: 100%;
  box-sizing: border-box;
}

.log-archive-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.archive-section {
  padding: var(--spacing-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background-color: var(--background);
}

.archive-section-title {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--foreground);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.archive-status-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
}

.archive-stat {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: var(--muted);
  border-radius: var(--radius-md);
}

.archive-stat--wide {
  grid-column: span 4;
}

.archive-stat-label {
  font-size: var(--font-size-xs);
  color: var(--muted-foreground);
}

.archive-stat-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--foreground);
}

.archive-stat-value.archive-dir {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-normal); /* 原 --font-weight-regular 未定义→继承 400；对齐 400 = normal */
  word-break: break-all;
}

.archive-action-row {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.archive-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.archive-field-label {
  font-size: var(--font-size-xs);
  color: var(--muted-foreground);
}

.archive-days-input {
  width: 120px;
}

.archive-filename-field {
  flex: 1;
  min-width: 260px;
}

.archive-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding-bottom: 8px;
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
  cursor: pointer;
}

.archive-result-message {
  margin: var(--spacing-md) 0 0 0;
  font-size: var(--font-size-sm);
  color: var(--success);
  word-break: break-all;
}

.archive-result-message.archive-error {
  color: var(--destructive);
}

.archive-empty-hint {
  margin: var(--spacing-md) 0 0 0;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.archived-count-hint {
  margin: var(--spacing-md) 0 0 0;
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
}

.archive-file-hint {
  margin: var(--spacing-sm) 0 0 0;
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.archived-logs-table {
  margin-top: var(--spacing-md);
  overflow-x: auto;
}

.archive-log-table th {
  white-space: nowrap;
}

.archived-log-content {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
