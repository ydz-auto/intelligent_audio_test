<template>
  <div class="test-case-detail">
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>正在加载用例详情...</p>
    </div>
    
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-circle"></i>
      <p>{{ error }}</p>
      <button @click="fetchDetail" class="btn btn-primary">重试</button>
    </div>
    
    <div v-else class="detail-content">
      <div class="case-header-panel" style="margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--border-color);">
        <h4 style="margin: 0 0 12px 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-file-alt" style="color: var(--primary-color);"></i>
          {{ detail.caseName }}
        </h4>
        <div class="case-meta" style="display: flex; gap: 20px; flex-wrap: wrap;">
          <div class="meta-item" style="display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-info-circle" style="color: var(--text-secondary); font-size: 14px;"></i>
            <span style="font-size: 14px; color: var(--text-secondary);">状态: </span>
            <span :class="'status-tag ' + (detail.executionStatus || 'pending').toLowerCase()" style="font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: 500;">
              {{ 
                detail.executionStatus === 'completed' ? (
                  (detail.evaluationStatus === 'completed' || detail.evaluationStatus === 'failed') ? '已完成' : '评估中'
                ) : 
                detail.executionStatus === 'failed' ? '执行失败' : 
                detail.executionStatus === 'in_progress' ? '执行中' : '等待中'
              }}
            </span>
          </div>
          <div class="meta-item" style="display: flex; align-items: center; gap: 8px;" v-if="detail.duration">
            <i class="fas fa-clock" style="color: var(--text-secondary); font-size: 14px;"></i>
            <span style="font-size: 14px; color: var(--text-secondary);">耗时{{ (detail.duration / 1000).toFixed(2) }}s</span>
          </div>
          <div class="meta-item" style="display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-star" style="color: var(--text-secondary); font-size: 14px;"></i>
            <span style="font-size: 14px; color: var(--text-secondary);">评分: </span>
            <span :class="'status-tag ' + (detail.evaluationStatus || 'pending').toLowerCase()" style="font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: 500;">
              {{ detail.evaluationStatus === 'completed' ? '评分完成' : '待评分' }}
            </span>
          </div>
        </div>
      </div>

      <div class="results-section" style="margin-top: 24px; background-color: var(--background-primary); border-radius: var(--border-radius-lg); box-shadow: var(--shadow-sm); padding: 20px; border: 1px solid var(--border-color);">
        <h5 style="margin: 0 0 16px 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-chart-bar" style="color: var(--primary-color);"></i>
          执行结果与指标
        </h5>
        
        <div v-if="!detail.results || detail.results.length === 0" class="no-items-message" style="text-align: center; padding: 30px; color: var(--text-secondary);">
          暂无执行结果
        </div>
        
        <div v-else v-for="result in detail.results" :key="result.id" class="result-card-modern" style="margin-bottom: 20px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden;">
          <div class="result-card-header" style="background-color: var(--background-secondary); padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color);">
            <div style="font-weight: 500; font-size: 14px;">
              <i class="fas fa-mobile-alt" style="margin-right: 6px; color: var(--text-secondary);"></i>
              {{ result.deviceName || result.deviceId || '' }}
            </div>
            <div v-if="result.apiName" style="font-size: 13px; color: var(--text-secondary);">
              API{{ result.apiName }}
            </div>
          </div>
          
          <div class="result-card-body" style="padding: 16px;">
            <TestCaseReportDetail 
              :dimensions="result.dimensions"
              :audioPath="result.resultData?.audioPath"
              :asrResult="result.asrResult"
              :transResult="result.translationResult"
              :referenceAsr="result.referenceAsrText || detail.referenceAsrText"
              :referenceTrans="result.referenceTranslationText || detail.referenceTranslationText"
              :problemsAndDiagnostics="result.problemsAndDiagnostics || []"
              :algorithmResults="detail.algorithmResults || {}"
              :referenceParams="detail.referenceParams || {}"
              :algorithmType="detail.algorithmType || ''"
              :results="detail.results || []"
            />
          </div>
        </div>
      </div>

      <div class="logs-section" style="margin-top: 24px;">
        <h5 style="margin: 0 0 16px 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-terminal" style="color: var(--primary-color);"></i>
          执行日志
        </h5>
        <div class="modern-log-container" ref="logContainer" style="background-color: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 8px; font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; max-height: 400px; overflow-y: auto; line-height: 1.6; border: 1px solid #333;">
          <div v-if="!detail.logs || detail.logs.length === 0" class="no-logs" style="text-align: center; color: #666; padding: 20px;">
            暂无日志信息
          </div>
          <div v-else v-for="log in detail.logs" :key="log.id" class="log-line" :class="'log-' + (log.level || 'info').toLowerCase()" style="margin-bottom: 2px; display: flex; gap: 10px;">
            <span class="log-timestamp" style="color: #858585; white-space: nowrap;">[{{ formatTime(log.time) }}]</span>
            <span class="log-lvl" style="font-weight: bold; width: 50px; text-align: center; border-radius: 2px; font-size: 11px; height: 18px; line-height: 18px;">{{ (log.level || 'INFO').toUpperCase() }}</span>
            <span class="log-msg" style="word-break: break-all;">{{ log.content }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { tasksApi, logsApi } from '../../../utils/api'
import TestCaseReportDetail from '../TestCaseReportDetail.vue'

const props = defineProps({
  taskId: { type: [String, Number], required: true },
  caseId: { type: [String, Number], required: true }
})

const loading = ref(true)
const error = ref(null)
const detail = ref(null)
const logContainer = ref(null)

const fetchDetail = async () => {
  loading.value = true
  error.value = null
  try {
    const [detailData, resultsData] = await Promise.all([
      tasksApi.getCaseDetail(props.taskId, props.caseId),
      tasksApi.getCaseResults(props.taskId, props.caseId)
    ])
    
    detail.value = {
      caseName: detailData.case_name,
      executionStatus: detailData.execution_status,
      evaluationStatus: detailData.evaluation_status,
      duration: detailData.duration,
      referenceAsrText: detailData.reference_asr_text,
      referenceTranslationText: detailData.reference_translation_text,
      errorMessage: detailData.error_message,
      results: resultsData.results || [],
      logs: []
    }
    
    // 后端 get_case_detail 不包含日志，需要单独获取
    try {
      const logsResponse = await logsApi.getAll({
        taskId: String(props.taskId),
        test_case_id: String(props.caseId),
        page: 1,
        perPage: 200
      })
      if (logsResponse && logsResponse.items) {
        // 后端返回倒序（最新在前），翻转为正序显示
        detail.value.logs = [...logsResponse.items].reverse().map(log => ({
          id: log.id,
          time: log.timestamp ?? log.time ?? log.createdAt,
          level: log.level || 'INFO',
          content: log.content
        }))
      }
    } catch (logErr) {
      console.warn('获取用例日志失败:', logErr)
    }
    
    await nextTick()
    scrollToBottom()
  } catch (err) {
    console.error('获取用例详情失败:', err)
    error.value = err.message || '获取详情失败，请重试'
  } finally {
    loading.value = false
  }
}

const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  const ms = String(date.getMilliseconds()).padStart(3, '0')
  return `${hours}:${minutes}:${seconds}.${ms}`
}

const scrollToBottom = () => {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

onMounted(() => {
  fetchDetail()
})
</script>

<style scoped>
.test-case-detail {
  padding: 0;
  min-height: 200px;
}

.loading-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px;
  gap: 16px;
  color: var(--text-secondary);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(0, 0, 0, 0.1);
  border-left-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-tag {
  display: inline-block;
}

.status-tag.completed { background-color: var(--success-light); color: var(--success-color); }
.status-tag.failed { background-color: var(--error-light); color: var(--error-color); }
.status-tag.inProgress { background-color: var(--warning-light); color: var(--warning-color); }
.status-tag.pending { background-color: var(--secondary-light); color: var(--secondary-color); }

.score-text-5 { color: var(--success-color); }
.score-text-4 { color: #73d13d; }
.score-text-3 { color: var(--warning-color); }
.score-text-2 { color: #ff7a45; }
.score-text-1 { color: var(--error-color); }
.score-text-none { color: var(--text-disabled); }

.score-badge { display: inline-block; }
.score-badge.score-5 { background-color: var(--success-light); color: var(--success-color); }
.score-badge.score-4 { background-color: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
.score-badge.score-3 { background-color: var(--warning-light); color: var(--warning-color); }
.score-badge.score-2 { background-color: #fff2e8; color: #fa541c; border: 1px solid #ffbb96; }
.score-badge.score-1 { background-color: var(--error-light); color: var(--error-color); }
.score-badge.score-0 { background-color: var(--secondary-light); color: var(--secondary-color); }

.log-line.error .log-lvl { background-color: #f85149; color: white; }
.log-line.warn .log-lvl { background-color: #d29922; color: white; }
.log-line.info .log-lvl { background-color: #388bfd; color: white; }
.log-line.debug .log-lvl { background-color: #6e7681; color: white; }

.log-line.error .log-msg { color: #f85149; }
.log-line.warn .log-msg { color: #d29922; }

.modern-log-container::-webkit-scrollbar {
  width: 8px;
}

.modern-log-container::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.modern-log-container::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 4px;
}

.modern-log-container::-webkit-scrollbar-thumb:hover {
  background: #444;
}

.modern-audio-player::-webkit-media-controls-panel {
  background-color: var(--primary-light);
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background-color: #3b82f6;
  color: white;
}

.btn-primary:hover {
  background-color: #2563eb;
}
</style>
