<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal report-snapshot-modal">
        <div class="modal-header">
          <h3 class="modal-title">
            <i class="fas fa-file-archive"></i> 冻结报告
            <span class="modal-subtitle">（发布时快照 · 不可变）</span>
          </h3>
          <button class="modal-close" @click="handleClose"><i class="fas fa-times"></i></button>
        </div>

        <div class="modal-scroll-container">
          <div class="modal-body">
            <!-- 总览 -->
            <div class="snapshot-section">
              <h4 class="section-title"><i class="fas fa-chart-pie"></i> 执行总览</h4>
              <div class="snapshot-summary-cards">
                <div class="summary-card">
                  <div class="summary-value">{{ snapshot.summary.totalCases ?? 0 }}</div>
                  <div class="summary-label">总用例</div>
                </div>
                <div class="summary-card success">
                  <div class="summary-value">{{ snapshot.summary.completedCases ?? 0 }}</div>
                  <div class="summary-label">完成</div>
                </div>
                <div class="summary-card danger">
                  <div class="summary-value">{{ snapshot.summary.failedCases ?? 0 }}</div>
                  <div class="summary-label">失败</div>
                </div>
                <div class="summary-card accent">
                  <div class="summary-value">{{ formatPassRate(snapshot.summary.passRate) }}</div>
                  <div class="summary-label">通过率</div>
                </div>
                <div class="summary-card">
                  <div class="summary-value">{{ formatDuration(snapshot.summary.duration) }}</div>
                  <div class="summary-label">时长</div>
                </div>
              </div>
            </div>

            <!-- 评估数据（维度分） -->
            <div class="snapshot-section">
              <h4 class="section-title"><i class="fas fa-ruler-combined"></i> 评估数据（维度分）</h4>
              <div v-if="dimensionRows.length > 0" class="dimension-table-wrap">
                <table class="snapshot-table">
                  <thead>
                    <tr><th>评估维度</th><th>得分</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, idx) in dimensionRows" :key="idx">
                      <td>{{ row.name }}</td>
                      <td class="dimension-value">{{ formatNumber(row.value) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else-if="metricDataRows.length > 0" class="metric-data-wrap">
                <table class="snapshot-table">
                  <thead>
                    <tr><th>资源</th><th>维度</th><th>得分</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, idx) in metricDataRows" :key="idx">
                      <td>{{ row.resource }}</td>
                      <td>{{ row.dimension }}</td>
                      <td class="dimension-value">{{ formatNumber(row.value) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else class="snapshot-empty">发布时该任务无维度评估数据</div>
            </div>

            <!-- 用例结果 -->
            <div class="snapshot-section">
              <h4 class="section-title"><i class="fas fa-list-check"></i> 用例执行结果
                <span class="section-count">共 {{ snapshot.cases.length }} 条</span>
              </h4>
              <input v-model="caseKeyword" class="case-search" placeholder="搜索用例名称 / 分类..." />
              <div v-if="filteredCases.length > 0" class="case-list">
                <div v-for="(c, idx) in filteredCases" :key="idx" class="case-row" :class="{ expanded: expandedCase === idx }">
                  <div class="case-row-head" @click="toggleCase(idx)">
                    <span class="case-name" :title="c.name || ''">{{ c.name || '未命名用例' }}</span>
                    <span class="case-category" v-if="c.category">{{ c.category }}</span>
                    <span class="case-metrics" v-if="hasMetrics(c)">{{ summarizeJson(c.metrics, 60) }}</span>
                    <span class="case-toggle"><i class="fas" :class="expandedCase === idx ? 'fa-chevron-up' : 'fa-chevron-down'"></i></span>
                  </div>
                  <div class="case-row-detail" v-if="expandedCase === idx">
                    <div class="case-detail-item" v-if="hasResults(c)">
                      <span class="case-detail-label">执行结果</span>
                      <pre class="case-detail-pre">{{ prettyJson(c.results) }}</pre>
                    </div>
                    <div class="case-detail-item" v-if="hasAlgorithmResults(c)">
                      <span class="case-detail-label">算法结果</span>
                      <pre class="case-detail-pre">{{ prettyJson(c.algorithmResults) }}</pre>
                    </div>
                    <div class="case-detail-item" v-if="c.logs">
                      <span class="case-detail-label">执行日志</span>
                      <pre class="case-detail-pre logs">{{ c.logs }}</pre>
                    </div>
                    <div class="case-detail-item" v-if="c.testCaseId">
                      <span class="case-detail-label">用例 ID</span>
                      <code class="case-detail-code">{{ c.testCaseId }}</code>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="snapshot-empty">无匹配用例</div>
            </div>

            <!-- 分析结论 -->
            <div class="snapshot-section" v-if="snapshot.analysis">
              <h4 class="section-title"><i class="fas fa-file-signature"></i> 分析结论</h4>
              <pre class="analysis-pre">{{ snapshot.analysis }}</pre>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleClose">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { ReportSnapshot } from '../../domain/model/publishedTask';

const props = defineProps<{ snapshot: ReportSnapshot }>();
const emit = defineEmits<{ (e: 'close'): void }>();

const caseKeyword = ref('');
const expandedCase = ref<number | null>(null);

/** 维度平均分行（dimensionValues 兜底解析） */
const dimensionRows = computed(() => {
  const values = props.snapshot.summary.dimensionValues || [];
  const rows: { name: string; value: unknown }[] = [];
  for (const item of values) {
    if (Array.isArray(item)) {
      if (item.length >= 2) rows.push({ name: String(item[0]), value: item[1] });
    } else if (item && typeof item === 'object') {
      const obj = item as Record<string, unknown>;
      const name = obj.name ?? obj.dimension ?? obj.label ?? Object.keys(obj)[0];
      const value = obj.value ?? obj.score ?? obj.average ?? Object.values(obj)[0];
      if (name != null && value != null) rows.push({ name: String(name), value });
    }
  }
  return rows;
});

/** 资源×维度分行（metricData 兜底解析） */
const metricDataRows = computed(() => {
  const data = props.snapshot.summary.metricData || {};
  const rows: { resource: string; dimension: string; value: unknown }[] = [];
  for (const [resource, dims] of Object.entries(data)) {
    if (dims && typeof dims === 'object') {
      for (const [dim, value] of Object.entries(dims as Record<string, unknown>)) {
        if (value != null && typeof value !== 'object') {
          rows.push({ resource, dimension: dim, value });
        }
      }
    }
  }
  return rows;
});

const filteredCases = computed(() => {
  const kw = caseKeyword.value.trim().toLowerCase();
  if (!kw) return props.snapshot.cases;
  return props.snapshot.cases.filter((c) => {
    const name = (c.name || '').toLowerCase();
    const category = (c.category || '').toLowerCase();
    return name.includes(kw) || category.includes(kw);
  });
});

function hasMetrics(c: { metrics?: Record<string, unknown> }): boolean {
  return !!c.metrics && Object.keys(c.metrics).length > 0;
}
function hasResults(c: { results?: unknown[] }): boolean {
  return !!c.results && c.results.length > 0;
}
function hasAlgorithmResults(c: { algorithmResults?: Record<string, unknown> }): boolean {
  return !!c.algorithmResults && Object.keys(c.algorithmResults).length > 0;
}

function summarizeJson(val: unknown, max: number): string {
  const str = JSON.stringify(val);
  return str ? (str.length > max ? `${str.slice(0, max)}...` : str) : '';
}

function prettyJson(val: unknown): string {
  try {
    return JSON.stringify(val, null, 2);
  } catch {
    return String(val);
  }
}

function formatPassRate(val: number): string {
  if (val == null) return '0%';
  if (val <= 1) return `${(val * 100).toFixed(1)}%`;
  return `${Number(val).toFixed(1)}%`;
}

function formatDuration(seconds: number): string {
  if (!seconds && seconds !== 0) return '-';
  const s = Math.round(seconds);
  if (s < 60) return `${s}秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}分${s % 60}秒`;
  const h = Math.floor(m / 60);
  return `${h}时${m % 60}分`;
}

function formatNumber(val: unknown): string {
  if (val == null) return '-';
  if (typeof val === 'number') return Number(val).toFixed(3);
  return String(val);
}

function toggleCase(idx: number) {
  expandedCase.value = expandedCase.value === idx ? null : idx;
}

function handleClose() {
  emit('close');
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 13000;
  overflow: hidden;
}

.modal {
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.report-snapshot-modal {
  width: 820px;
  max-width: 94vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #343a40;
}

.modal-title i {
  color: #ff6a00;
}

.modal-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
  margin-left: 4px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #6c757d;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
}

.modal-scroll-container {
  max-height: calc(90vh - 70px);
  overflow-y: auto;
  flex: 1;
}

.modal-body {
  padding: 20px 24px;
  background-color: #fff;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-top: 1px solid #e9ecef;
  background-color: #f8f9fa;
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-secondary {
  background-color: #f0f0f0;
  color: #333;
}

.btn-secondary:hover {
  background-color: #e0e0e0;
}

.snapshot-section {
  margin-bottom: 22px;
}

.section-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-title i {
  color: #ff6a00;
}

.section-count {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
  margin-left: 4px;
}

.snapshot-summary-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.summary-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 8px;
  text-align: center;
}

.summary-card .summary-value {
  font-size: 20px;
  font-weight: 700;
  color: #334155;
}

.summary-card.success .summary-value { color: #16a34a; }
.summary-card.danger .summary-value { color: #dc2626; }
.summary-card.accent .summary-value { color: #ff6a00; }

.summary-card .summary-label {
  margin-top: 4px;
  font-size: 12px;
  color: #94a3b8;
}

.snapshot-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.snapshot-table th,
.snapshot-table td {
  border: 1px solid #e9ecef;
  padding: 7px 10px;
  text-align: left;
}

.snapshot-table th {
  background: #f8f9fa;
  color: #495057;
  font-weight: 600;
}

.dimension-value {
  font-variant-numeric: tabular-nums;
  color: #ff6a00;
  font-weight: 600;
}

.dimension-table-wrap,
.metric-data-wrap {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid #e9ecef;
  border-radius: 6px;
}

.snapshot-empty {
  padding: 16px;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
  border-radius: 6px;
}

.case-search {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 10px;
}

.case-search:focus {
  outline: none;
  border-color: #ff6a00;
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.15);
}

.case-list {
  border: 1px solid #e9ecef;
  border-radius: 6px;
  overflow: hidden;
}

.case-row {
  border-bottom: 1px solid #eef2f7;
}

.case-row:last-child {
  border-bottom: none;
}

.case-row-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.case-row-head:hover {
  background: #f8fafc;
}

.case-row.expanded .case-row-head {
  background: #fff7ed;
}

.case-name {
  flex: 1;
  font-size: 13px;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-category {
  flex-shrink: 0;
  font-size: 11px;
  color: #ff6a00;
  background: #fff1e6;
  border-radius: 10px;
  padding: 2px 8px;
}

.case-metrics {
  flex-shrink: 0;
  max-width: 260px;
  font-size: 12px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.case-toggle {
  flex-shrink: 0;
  color: #adb5bd;
  font-size: 12px;
}

.case-row-detail {
  padding: 12px 14px;
  background: #fbfcfd;
  border-top: 1px solid #eef2f7;
}

.case-detail-item {
  margin-bottom: 10px;
}

.case-detail-item:last-child {
  margin-bottom: 0;
}

.case-detail-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 4px;
}

.case-detail-pre {
  margin: 0;
  padding: 8px 10px;
  background: #f1f5f9;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  max-height: 220px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.case-detail-pre.logs {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.case-detail-code {
  font-size: 12px;
  color: #475569;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
}

.analysis-pre {
  margin: 0;
  padding: 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: #78350f;
}
</style>
