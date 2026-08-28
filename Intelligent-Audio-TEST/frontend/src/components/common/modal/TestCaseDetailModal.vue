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
            <CaseIdBadge :case-id="caseId" />
          </div>
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

      <!-- 执行结果与指标 - 有任何数据时才显示 -->
      <div v-if="hasAnyResultData" class="results-section" style="margin-top: 24px; background-color: var(--background-primary); border-radius: var(--border-radius-lg); box-shadow: var(--shadow-sm); padding: 20px; border: 1px solid var(--border-color);">
        <h5 style="margin: 0 0 16px 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-chart-bar" style="color: var(--primary-color);"></i>
          执行结果与指标
        </h5>
        <TestCaseReportDetail 
          :isComparison="true"
          :devices="detail.devices"
          :comparisonData="preparedComparisonData"
          :metricConfigs="detail.metricConfigs"
          :audioList="detail.audioList"
          :referenceAsr="extractReferenceText(detail.referenceParams, 'asr_reference_text')"
          :referenceTrans="extractReferenceText(detail.referenceParams, 'translation_reference_text')"
          :algorithmResults="detail.algorithmResults"
          :referenceParams="detail.referenceParams"
          :algorithmType="detail.algorithmType"
          :results="detail.results"
          :fieldMapping="detail.fieldMapping"
          :resultAudios="detail.resultAudios"
        />
      </div>
      
      <!-- 完全没有执行数据时的提示 -->
      <div v-else-if="!detail.results || detail.results.length === 0" class="results-section" style="margin-top: 24px; background-color: var(--background-primary); border-radius: var(--border-radius-lg); box-shadow: var(--shadow-sm); padding: 20px; border: 1px solid var(--border-color);">
        <h5 style="margin: 0 0 16px 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-chart-bar" style="color: var(--primary-color);"></i>
          执行结果与指标
        </h5>
        <div class="no-items-message" style="text-align: center; padding: 30px; color: var(--text-secondary);">
          暂无执行结果
        </div>
      </div>

      <!-- 执行日志 -->
      <div class="logs-section" style="margin-top: 24px;">
        <h5 style="margin: 0 0 16px 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-terminal" style="color: var(--primary-color);"></i>
          执行日志
        </h5>
        <div class="log-toolbar">
          <button v-if="hasMoreLogs" @click="loadMoreLogs" :disabled="logLoadingMore" class="btn-load-more-logs">
            {{ logLoadingMore ? '加载中...' : '↓ 加载更多日志' }}
          </button>
          <span v-if="logTotal > 0" class="log-count">显示 {{ detail.logs.length }} / 共 {{ logTotal }} 条</span>
        </div>
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
import { ref, computed, onMounted, nextTick } from 'vue'
import { tasksApi, logsApi } from '../../../utils/api'
import TestCaseReportDetail from '../TestCaseReportDetail.vue'
import CaseIdBadge from '../CaseIdBadge.vue'

const props = defineProps({
  taskId: { type: [String, Number], required: true },
  caseId: { type: [String, Number], required: true }
})

const loading = ref(true)
const error = ref(null)
const detail = ref(null)
const logContainer = ref(null)

// 日志分页状态
const logPage = ref(1)
const logTotal = ref(0)
const logPages = ref(0)
const logLoadingMore = ref(false)
const logPerPage = 100

// 准备对比数据：按设备分组指标和文本
// 多轮场景：同一维度名会出现多次（每轮一次 + 可能的整体评估），
// 用 round_number 区分：NULL=整体评估, 0-indexed=轮次
// 指标 key 形如 "LLM语义评分" (单轮/整体) 或 "LLM语义评分@round:1" (第2轮) 或 "LLM语义评分@overall" (整体)
const preparedComparisonData = computed(() => {
  if (!detail.value?.results || !detail.value.devices?.length) return {}
  // 先判断是否多轮：任一设备有任一维度带 roundNumber（非 NULL）即视为多轮
  const isMultiRound = detail.value.results.some(r => (r.dimensions || []).some(d => (d.roundNumber ?? d.round_number) !== null && (d.roundNumber ?? d.round_number) !== undefined))
  const data = {}
  detail.value.devices.forEach(device => {
    const deviceResult = detail.value.results.find(r => (r.deviceName ?? r.device_name) === device)
    const metricsMap = {}
    if (deviceResult?.dimensions) {
      deviceResult.dimensions.forEach(d => {
        if (!d.name) return
        const rn = d.roundNumber ?? d.round_number
        let key = d.name
        if (isMultiRound) {
          if (rn === null || rn === undefined) key = `${d.name}@overall`
          else key = `${d.name}@round:${rn + 1}`
        }
        metricsMap[key] = {
          metric: d.name,
          value: d.score ?? d.value,
          round_number: rn,
          dimension_type: d.dimension_type ?? d.dimensionType ?? 'main',
          parent_dimension_id: d.parent_dimension_id ?? d.parentDimensionId ?? null,
          dimension_id: d.dimension_id ?? d.dimensionId ?? null
        }
      })
    }
    data[device] = {
      metrics: metricsMap,
      asr: { text: deviceResult?.asrResult || deviceResult?.asr_result || '-' },
      trans: { text: deviceResult?.translationResult || deviceResult?.translation_result || '-' }
    }
  })
  return data
})

// 从结构化 referenceParams 提取参考文本
const extractReferenceText = (refParams, key) => {
  if (!refParams) return ''
  const param = refParams[key]
  if (!param) return ''
  return param.text || param.value || ''
}

// 检查是否有任何结果数据可显示
const hasAnyResultData = computed(() => {
  if (!detail.value) return false
  const d = detail.value
  
  // 有设备结果
  if (d.devices && d.devices.length > 0) return true
  
  // 有音频列表（参考音频）
  if (d.audioList && d.audioList.length > 0) return true
  
  // 有结果音频
  if (d.resultAudios && typeof d.resultAudios === 'object' && Object.keys(d.resultAudios).length > 0) return true
  
  // 有指标数据
  if (d.metricConfigs && d.metricConfigs.length > 0) return true
  
  // 有 field_mapping 中的数据
  if (d.fieldMapping) {
    if ((d.fieldMapping.result || []).length > 0) return true
    if ((d.fieldMapping.reference || []).length > 0) return true
  }
  
  // 有 algorithmResults 数据
  if (Array.isArray(d.algorithmResults) && d.algorithmResults.length > 0) return true
  
  // 有 referenceParams 数据
  if (d.referenceParams && typeof d.referenceParams === 'object' && Object.keys(d.referenceParams).length > 0) return true
  
  return false
})

// 是否还有更多日志可加载
const hasMoreLogs = computed(() => {
  return detail.value?.logs && detail.value.logs.length < logTotal.value
})

const fetchDetail = async () => {
  loading.value = true
  error.value = null
  try {
    const [detailData, resultsData] = await Promise.all([
      tasksApi.getCaseDetail(props.taskId, props.caseId),
      tasksApi.getCaseResults(props.taskId, props.caseId)
    ])
    
    detail.value = {
      caseName: detailData.caseName ?? detailData.case_name,
      executionStatus: detailData.executionStatus ?? detailData.execution_status,
      evaluationStatus: detailData.evaluationStatus ?? detailData.evaluation_status,
      duration: detailData.duration,
      errorMessage: detailData.errorMessage ?? detailData.error_message,
      results: resultsData.results || [],
      // 后端返回完整的对比展示数据
      audioList: detailData.audioList ?? detailData.audio_list ?? [],
      referenceParams: detailData.referenceParams ?? detailData.reference_params ?? {},
      algorithmResults: detailData.algorithmResults ?? detailData.algorithm_results ?? [],
      algorithmType: detailData.algorithmType ?? detailData.algorithm_type ?? '',
      devices: detailData.devices ?? [],
      metricConfigs: detailData.metricConfigs ?? detailData.metric_configs ?? [],
      fieldMapping: detailData.fieldMapping ?? detailData.field_mapping ?? { result: [], reference: [] },
      resultAudios: detailData.resultAudios ?? detailData.result_audios ?? {},
      logs: []
    }
    
    // 后端 get_case_detail 不包含日志，需要单独获取
    try {
      // 先获取第1页来拿到总页数
      const firstPageResponse = await logsApi.getAll({
        taskId: String(props.taskId),
        test_case_id: String(props.caseId),
        page: 1,
        perPage: logPerPage
      })
      
      if (firstPageResponse && firstPageResponse.items) {
        const total = firstPageResponse.total || 0
        const pages = firstPageResponse.pages || 1
        logTotal.value = total
        logPages.value = pages

        const mapLog = (items) => items.map(log => ({
          id: log.id,
          time: log.timestamp ?? log.time ?? log.createdAt,
          level: log.level || 'INFO',
          content: log.content
        }))

        if (pages <= 1) {
          // 只有1页：后端返回DESC（最新在前），reverse为正序
          detail.value.logs = mapLog([...firstPageResponse.items].reverse())
          logPage.value = 1
        } else {
          // 多页：从最后一页（最旧的日志）开始加载，按时间正序显示
          const lastPageResponse = await logsApi.getAll({
            taskId: String(props.taskId),
            test_case_id: String(props.caseId),
            page: pages,
            perPage: logPerPage
          })
          if (lastPageResponse?.items) {
            detail.value.logs = mapLog([...lastPageResponse.items].reverse())
            logPage.value = pages  // 记录当前已加载到第几页
          }
        }
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
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  const ms = String(date.getMilliseconds()).padStart(3, '0')
  return `${month}-${day} ${hours}:${minutes}:${seconds}.${ms}`
}

const scrollToBottom = () => {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

// 加载更多日志（从最旧页向前翻，加载更新的日志，追加到列表后面）
const loadMoreLogs = async () => {
  if (logLoadingMore.value || !hasMoreLogs.value) return
  logLoadingMore.value = true
  // 从最后一页向前翻（page - 1 = 更新的日志）
  const prevPage = logPage.value - 1
  if (prevPage < 1) return

  try {
    const response = await logsApi.getAll({
      taskId: String(props.taskId),
      test_case_id: String(props.caseId),
      page: prevPage,
      perPage: logPerPage
    })
    if (response?.items) {
      // 后端返回DESC，reverse为正序后追加到列表末尾（更新的日志在后面）
      const newerLogs = [...response.items].reverse().map(log => ({
        id: log.id,
        time: log.timestamp ?? log.time ?? log.createdAt,
        level: log.level || 'INFO',
        content: log.content
      }))
      detail.value.logs = [...detail.value.logs, ...newerLogs]
      logPage.value = prevPage
    }
    // 新日志追加在后面，滚动到底部
    await nextTick()
    scrollToBottom()
  } catch (err) {
    console.warn('加载更多日志失败:', err)
  } finally {
    logLoadingMore.value = false
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

.log-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 4px 0;
}

.btn-load-more-logs {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--background-secondary);
  color: var(--primary-color);
  font-size: 12px;
  cursor: pointer;
}

.btn-load-more-logs:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.log-count {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
