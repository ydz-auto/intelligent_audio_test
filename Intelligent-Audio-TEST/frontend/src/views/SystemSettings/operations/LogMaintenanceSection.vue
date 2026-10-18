<template>
  <div class="settings-form-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-wrench"></i>
          日志维护
        </h2>
        <p class="page-description">配置日志保留策略并管理归档（与「日志查看」页联动）</p>
      </div>
    </div>

    <p v-if="kvError" class="error-msg">{{ kvError }}</p>
    <p v-if="kvNotice" class="success-msg">{{ kvNotice }}</p>

    <!-- 保留天数（KV：operations.log_retention_days） -->
    <div class="card settings-card">
      <div class="card-body">
        <div class="retention-row">
          <div class="retention-field">
            <label class="field-label">日志保留天数</label>
            <div class="retention-input">
              <input
                type="number"
                class="form-input"
                min="1"
                v-model.number="values['operations.log_retention_days']"
                :disabled="!canManage"
              />
              <span class="unit">天</span>
            </div>
            <p class="field-hint">超过保留期的系统日志自动清理（读权限可见，写权限可改）</p>
          </div>
          <div class="retention-actions">
            <button class="btn btn-primary" :disabled="saving" @click="save">
              <i class="fas fa-save btn-icon"></i>{{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 归档管理（INT-548 归档端点，原 /logs 归档面板迁移至此，/logs 页改为「查看归档」链接） -->
    <div class="card settings-card">
      <div class="card-header">
        <h3 class="card-title">
          <i class="fas fa-archive"></i>
          归档管理
        </h3>
        <p class="card-description">管理日志归档状态、归档文件与归档操作</p>
      </div>
      <div class="card-body">
        <div class="archive-section">
          <div class="section-label">归档状态</div>
          <div class="status-grid">
            <div class="status-item">
              <span class="status-label">总日志</span>
              <span class="status-value">{{ archiveStatus.totalLogs }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">热日志</span>
              <span class="status-value">{{ archiveStatus.hotLogs }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">冷日志</span>
              <span class="status-value">{{ archiveStatus.coldLogs }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">任务归档</span>
              <span class="status-value">{{ archiveStatus.taskArchives }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">用例归档</span>
              <span class="status-value">{{ archiveStatus.caseArchives }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">其他归档</span>
              <span class="status-value">{{ archiveStatus.otherArchives }}</span>
            </div>
            <div class="status-item wide">
              <span class="status-label">归档目录</span>
              <span class="status-value mono">{{ archiveStatus.archiveDir || '-' }}</span>
            </div>
          </div>
          <div class="archive-actions">
            <button class="btn btn-primary" :disabled="!canManage || resultLoading" @click="doTriggerArchive">
              <i class="fas fa-box-archive btn-icon"></i>
              {{ resultLoading ? '归档中...' : '立即归档' }}
            </button>
            <p v-if="result?.message" class="result-msg">{{ result.message }}</p>
          </div>
        </div>

        <!-- 已归档日志查询 -->
        <div class="archive-section">
          <div class="section-label">已归档日志</div>
          <div class="query-row">
            <input
              type="number"
              class="form-input"
              v-model.number="archivedQuery.taskId"
              placeholder="任务ID"
            />
            <input
              type="text"
              class="form-input"
              v-model="archivedQuery.testCaseId"
              placeholder="用例ID"
            />
            <button class="btn btn-secondary" @click="queryArchivedLogs()">
              <i class="fas fa-search btn-icon"></i>查询
            </button>
            <button class="btn btn-text" @click="clearArchivedQuery()">清空</button>
          </div>
          <p v-if="archivedError" class="error-msg">{{ archivedError }}</p>
          <div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>级别</th>
                  <th>模块</th>
                  <th>任务ID</th>
                  <th>用例ID</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!archivedLogs.length">
                  <td colspan="6" class="empty-row">
                    {{ archivedLoading ? '加载中...' : '暂无已归档日志' }}
                  </td>
                </tr>
                <tr v-else v-for="log in archivedLogs" :key="log.id">
                  <td class="mono">{{ log.time || '-' }}</td>
                  <td><span class="log-level" :class="log.level">{{ log.level?.toUpperCase() }}</span></td>
                  <td>{{ log.module || '-' }}</td>
                  <td class="mono">{{ log.taskId ?? '-' }}</td>
                  <td class="mono">{{ log.testCaseId ?? '-' }}</td>
                  <td class="content-cell">{{ log.content }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="archivedTotal > 0" class="count-hint">共 {{ archivedTotal }} 条</p>
        </div>

        <!-- 归档文件操作 -->
        <div class="archive-section">
          <div class="section-label">归档文件</div>
          <div class="query-row">
            <input
              type="text"
              class="form-input"
              v-model="archiveFilename"
              placeholder="归档文件名（如 2026-10-15.json）"
            />
            <button class="btn btn-secondary" @click="downloadArchive(archiveFilename)">
              <i class="fas fa-download btn-icon"></i>下载
            </button>
            <button
              v-if="canManage"
              class="btn btn-secondary btn-danger"
              @click="deleteArchive(archiveFilename)"
            >
              <i class="fas fa-trash btn-icon"></i>删除
            </button>
          </div>
          <p class="field-hint">下载需 log:read，删除需 log:manage；带斜杠的逻辑 key 自动取末段文件名</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAuthStore } from '@/store/authStore'
import { useOptionForm } from '../useSettingsForm'
import type { SystemOptions } from '@/domain'
import { useLogArchive } from '@/views/LogView/logArchive'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('log:manage'))

const kv = useOptionForm([
  {
    key: 'operations.log_retention_days',
    type: 'number',
    toValue: (o: SystemOptions) => {
      const v = o['operations.log_retention_days']
      if (typeof v === 'number') return v
      const n = Number(v)
      return Number.isFinite(n) ? n : 30
    },
  },
])
const { values, saving, error: kvError, notice: kvNotice, save } = kv

const archive = useLogArchive()
const {
  status: archiveStatus,
  resultLoading,
  result,
  archivedQuery,
  archivedLogs,
  archivedLoading,
  archivedError,
  archivedTotal,
  archiveFilename,
  loadStatus,
  triggerArchive: doTriggerArchive,
  queryArchivedLogs,
  clearArchivedQuery,
  downloadArchive,
  deleteArchive,
} = archive

onMounted(() => {
  loadStatus().catch(() => undefined)
})
</script>

<style scoped>
.settings-card {
  max-width: 820px;
  margin-bottom: var(--spacing-lg);
}

.retention-row {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-lg);
}

.retention-input {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: var(--spacing-xs);
}

.retention-input .form-input {
  width: 160px;
}

.unit {
  color: var(--text-secondary);
  font-size: 14px;
}

.field-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.field-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin: var(--spacing-xs) 0 0;
}

.archive-section {
  padding: var(--spacing-md) 0;
  border-bottom: 1px solid var(--gray-light-color);
}

.archive-section:last-child {
  border-bottom: none;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: var(--spacing-sm);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: var(--spacing-sm);
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.status-item.wide {
  grid-column: 1 / -1;
}

.status-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.status-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.mono {
  font-family: var(--font-mono, monospace);
}

.archive-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
}

.result-msg {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.query-row {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.query-row .form-input {
  width: 160px;
}

.count-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin: var(--spacing-xs) 0 0;
}

.error-msg {
  color: var(--destructive);
  font-size: 13px;
  margin: var(--spacing-xs) 0;
}

.content-cell {
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
