<template>
  <div class="test-case-report-detail">
    <div v-if="hasMetrics" class="detail-section">
      <h4 class="section-title"><i class="fas fa-chart-bar"></i> 评分指标</h4>
      <div class="metrics-table-wrapper">
        <DataTable
          v-if="isComparison"
          :columns="comparisonTableColumns"
          :data="comparisonTableData"
          :resizable="true"
          :min-column-width="60"
          :default-column-width="{ first: 200, others: 150 }"
          table-class="report-data-table"
          row-key="metricName"
        >
          <template #cell-metricName="{ row, value }">
            <span class="dim-name">{{ row.metricName }}</span>
          </template>
          <template #empty>
            <div style="padding: 20px; text-align: center; color: #94a3b8;">
              暂无指标数据
            </div>
          </template>
        </DataTable>
        <DataTable
          v-else
          :columns="singleTableColumns"
          :data="singleTableData"
          :resizable="true"
          :min-column-width="60"
          :default-column-width="{ first: 200, others: 150 }"
          table-class="report-data-table"
          row-key="metric"
        >
          <template #cell-metric="{ row, value }">
            <span class="dim-name">{{ row.metric }}</span>
          </template>
          <template #cell-value="{ row, value }">
            <span class="dim-value">{{ formatValue(row.rawValue) }}</span>
          </template>
          <template #cell-score="{ row, value }">
            <span :class="'score-badge score-' + (row.rawScore || '0')">
              {{ row.rawScore || '-' }}分
            </span>
          </template>
          <template #cell-errorMessage="{ row, value }">
            <div class="collapsible-text" :class="{ expanded: expandedTexts[`${row.metric}_dim`] }">
              <div class="text-content">{{ row.rawErrorMessage || '-' }}</div>
              <div v-if="(row.rawErrorMessage || '').length > 50" class="expand-toggle" @click="toggleText(`${row.metric}_dim`)">
                {{ expandedTexts[`${row.metric}_dim`] ? '收起' : '展开' }}
              </div>
            </div>
          </template>
          <template #empty>
            <div style="padding: 20px; text-align: center; color: #94a3b8;">
              暂无指标数据
            </div>
          </template>
        </DataTable>
      </div>
    </div>

    <AudioPlayerModal
      v-if="showAudioModal && currentPlayingAudio"
      :visible="showAudioModal"
      :audioId="currentPlayingAudio.id"
      :audioTitle="currentPlayingAudio.label || '音频播放'"
      :audioType="currentPlayingAudio.type || 'api'"
      :spl="currentPlayingAudio.spl"
      :offset="currentPlayingAudio.offset"
      @close="closeAudioModal"
    />

    <!-- 统一执行结果卡片 -->
    <div v-if="hasExecutionResults" class="detail-section">
      <h4 class="section-title"><i class="fas fa-play-circle"></i> 执行结果</h4>

      <div class="execution-results-container">
        <!-- 参考文本字段 -->
        <div v-if="referenceTextFields.length > 0" class="result-subsection">
          <div class="subsection-label">参考数据</div>
          <div class="text-comparison-grid reference-row">
            <div class="text-group" v-for="field in referenceTextFields" :key="'ref_' + field.param_code">
              <div class="text-item">
                <div class="result-label">{{ field.label || field.param_code }}</div>
                <div class="text-card reference">
                  <div class="collapsible-text" :class="{ expanded: expandedTexts['ref_' + field.param_code] }">
                    <div class="text-content">{{ field.text }}</div>
                    <div v-if="(field.text || '').length > 100" class="expand-toggle" @click="toggleText('ref_' + field.param_code)">
                      {{ expandedTexts['ref_' + field.param_code] ? '收起' : '展开' }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 结果文本字段 -->
        <div v-if="resultTextFields.length > 0" class="result-subsection">
          <div v-if="referenceTextFields.length > 0" class="subsection-label">结果数据</div>
          <div v-if="!isComparison" class="device-result-row">
            <div class="text-comparison-grid">
              <div class="text-item" v-for="field in resultTextFields" :key="'res_' + field.param_code">
                <div class="result-label">{{ field.label || field.param_code }}</div>
                <div class="text-card">
                  <div class="collapsible-text" :class="{ expanded: expandedTexts['default_' + field.param_code] }">
                    <div class="text-content">{{ field.getValue('default') }}</div>
                    <div v-if="(field.getValue('default')).length > 100" class="expand-toggle" @click="toggleText('default_' + field.param_code)">
                      {{ expandedTexts['default_' + field.param_code] ? '收起' : '展开' }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else v-for="device in devices" :key="device" class="device-result-row">
            <div class="device-row-title">{{ getDeviceName(device) }}</div>
            <div class="text-comparison-grid">
              <div class="text-item" v-for="field in resultTextFields" :key="device + '_' + field.param_code">
                <div class="result-label">{{ field.label || field.param_code }}</div>
                <div class="text-card">
                  <div class="collapsible-text" :class="{ expanded: expandedTexts[device + '_' + field.param_code] }">
                    <div class="text-content">{{ field.getValue(device) }}</div>
                    <div v-if="(field.getValue(device)).length > 100" class="expand-toggle" @click="toggleText(device + '_' + field.param_code)">
                      {{ expandedTexts[device + '_' + field.param_code] ? '收起' : '展开' }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 时间轴对比 -->
        <div v-if="hasTimelineData" class="result-subsection">
          <div class="subsection-label">时间轴对比</div>
          <TimelineComparison
            :algorithmResults="algorithmResults"
            :referenceParams="referenceParams"
            :algorithmType="algorithmType"
            :results="results"
            :fieldMapping="fieldMapping"
          />
        </div>

        <!-- 音频时间轴 -->
        <div v-if="hasAudio" class="result-subsection">
          <div class="subsection-label">音频时间轴</div>
          <AudioTimelineVisualization
            :audioList="audioListWithTimeline"
          />
        </div>

        <!-- 结果音频 -->
        <div v-if="hasResultAudioData" class="result-subsection">
          <div class="subsection-label">结果音频</div>
          <div class="result-audio-container">
            <div v-for="(audios, device) in resultAudios" :key="device" class="result-audio-group">
              <div class="result-audio-title">{{ getDeviceName(device) }}</div>
              <div class="result-audio-list">
                <div v-for="(audio, idx) in audios" :key="idx" class="result-audio-item">
                  <span class="result-audio-label">{{ audio.filename || audio.param_code || '音频' + (idx + 1) }}</span>
                  <a v-if="audio.url" :href="audio.url" target="_blank" class="result-audio-link">
                    <i class="fas fa-external-link-alt"></i> 播放
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { API_CONFIG } from '../../utils/config';
import DataTable from './DataTable.vue';
import TimelineComparison from '../report/TimelineComparison.vue';
import AudioPlayerModal from './AudioPlayerModal.vue';
import AudioTimelineVisualization from './AudioTimelineVisualization.vue';

const apiBaseUrl = API_CONFIG.baseUrl;

const props = defineProps({
  dimensions: { type: Array, default: () => [] },
  metrics: { type: Array, default: () => [] },
  audioPath: String,
  asrResult: String,
  transResult: String,

  isComparison: { type: Boolean, default: false },
  devices: { type: Array, default: () => [] },
  comparisonData: { type: Object, default: () => ({}) },
  metricConfigs: { type: Array, default: () => [] },
  audioList: { type: Array, default: () => [] },
  referenceAsr: String,
  referenceTrans: String,
  resourceHeaders: { type: Array, default: () => [] },
  algorithmResults: { type: Array, default: () => [] },
  referenceParams: { type: Object, default: () => ({}) },
  algorithmType: { type: String, default: '' },
  results: { type: Array, default: () => [] },
  fieldMapping: { type: Object, default: () => ({ result: [], reference: [] }) },
  resultAudios: { type: Object, default: () => ({}) },
});

const displayMetrics = computed(() => {
  if (props.dimensions && props.dimensions.length > 0) {
    return props.dimensions.map(dim => ({
      id: dim.id,
      metric: dim.name,
      value: dim.value,
      score: dim.score,
      errorMessage: dim.errorMessage
    }));
  }
  if (props.metrics && props.metrics.length > 0) {
    return props.metrics.map(m => ({
      id: m.id,
      metric: m.metric,
      value: m.value,
      score: calculateScore(m.value),
      errorMessage: null
    }));
  }
  return [];
});

const calculateScore = (value) => {
  if (value === null || value === undefined || value === '-') return 0;
  const num = Number(value);
  if (isNaN(num)) return 0;
  if (num <= 5) return 5;
  if (num <= 10) return 4;
  if (num <= 20) return 3;
  if (num <= 30) return 2;
  return 1;
};

const formatValue = (value) => {
  if (value === null || value === undefined || value === '-') return '-';
  const num = Number(value);
  if (isNaN(num)) return String(value);
  return num.toFixed(2);
};

const getAudioUrl = (audio) => {
  if (!audio) return '';
  
  // 如果直接传入的是路径字符串（兼容旧用法）
  if (typeof audio === 'string') {
    return `${apiBaseUrl.replace('/v1', '')}/audio/stream-by-path?path=${encodeURIComponent(audio)}`;
  }
  
  // 如果有完整URL（后端直接返回的），直接返回
  if (audio.url && audio.url.startsWith('http')) {
    return audio.url;
  }
  if (audio.url && audio.url.startsWith('/')) {
    // 处理后端返回的 /api/audios/play/{id} 格式
    if (audio.url.includes('/audios/play/')) {
      return audio.url;
    }
    // 处理其他 /api 开头的路径
    return `${apiBaseUrl.replace('/v1', '')}${audio.url}`;
  }
  
  // 优先使用 ID 获取音频
  if (audio.id) {
    const taskType = audio.type || 'api';
    return `${apiBaseUrl}/audios/${audio.id}/stream?task_type=${taskType}`;
  }
  
  // 如果没有 ID，回退到使用路径
  if (audio.path) {
    return `${apiBaseUrl.replace('/v1', '')}/audio/stream-by-path?path=${encodeURIComponent(audio.path)}`;
  }
  
  return '';
};

const hasAudio = computed(() => props.audioPath || props.audioList.length > 0);

// 是否有评分指标数据
const hasMetrics = computed(() => {
  if (props.isComparison) {
    return allMetricNames.value.length > 0;
  }
  return (props.dimensions && props.dimensions.length > 0) || 
         (props.metrics && props.metrics.length > 0);
});

// 是否有任何执行结果数据（文本、时间轴、音频、结果音频）
const hasExecutionResults = computed(() => {
  // 动态文本字段（来自 fieldMapping 或 algorithmResults/referenceParams）
  if (referenceTextFields.value.length > 0 || resultTextFields.value.length > 0) return true;
  // 时间轴数据
  if (hasTimelineData.value) return true;
  // 音频数据
  if (hasAudio.value) return true;
  // 结果音频
  if (hasResultAudioData.value) return true;
  return false;
});

// 动态参考文本字段
const referenceTextFields = computed(() => {
  // 优先使用 fieldMapping
  const refFields = (props.fieldMapping?.reference || [])
    .filter(f => f.param_type === 'text');
  if (refFields.length > 0) {
    const result = [];
    for (const field of refFields) {
      const text = getReferenceTextValue(field.param_code);
      if (text && text.trim() && text !== '无数据') {
        result.push({ ...field, text });
      }
    }
    return result;
  }

  // 回退：从 referenceParams 中提取 text 类型参数
  const refParams = props.referenceParams || {};
  const result = [];
  for (const [code, data] of Object.entries(refParams)) {
    if (!data || typeof data !== 'object') continue;
    if (data.type !== 'text') continue;
    const text = data.text || data.value || '';
    if (typeof text === 'string' && text.trim()) {
      result.push({ param_code: code, label: code, param_type: 'text', text });
    }
  }
  return result;
});

// 动态结果文本字段
const resultTextFields = computed(() => {
  // 优先使用 fieldMapping
  const fields = (props.fieldMapping?.result || [])
    .filter(f => f.param_type === 'text');
  if (fields.length > 0) {
    return fields.map(f => ({
      ...f,
      getValue: (device) => getResultTextValue(device, f.param_code)
    }));
  }

  // 回退：从 algorithmResults 数组中提取 text 类型项
  const algoResults = props.algorithmResults || [];
  if (!Array.isArray(algoResults)) return [];
  const textItems = [];
  const seenCodes = new Set();
  for (const item of algoResults) {
    if (item.param_type === 'text' && !seenCodes.has(item.param_code)) {
      seenCodes.add(item.param_code);
      textItems.push({
        param_code: item.param_code,
        label: item.label || item.param_code,
        param_type: 'text',
        getValue: (device) => getResultTextValue(device, item.param_code)
      });
    }
  }
  return textItems;
});

// 是否有结果音频
const hasResultAudioData = computed(() => {
  return props.resultAudios && Object.keys(props.resultAudios).length > 0;
});

const audioListWithTimeline = computed(() => {
  const list = props.audioList || [];
  if (list.length === 0) return [];
  
  // 只做字段归一化，不再自行计算时间轴位置
  // 后端已根据 overlap_rate/overlap_time 计算好 timelineStart/timelineEnd
  return list.map(a => ({
    ...a,
    timelineStart: a.timelineStart ?? a.timeline_start ?? 0,
    timelineEnd: a.timelineEnd ?? a.timeline_end ?? ((a.timelineStart ?? a.timeline_start ?? 0) + (a.duration || 0)),
    testType: a.testType ?? a.test_type ?? a.audio_type ?? 'api',
    playOrder: a.playOrder ?? a.play_order,
    playbackDeviceName: a.playbackDeviceName ?? a.device_name ?? a.playback_device_name,
  }));
});

const hasTimelineData = computed(() => {
  // 优先使用 fieldMapping 判断
  if (props.fieldMapping) {
    const hasResultTimeline = (props.fieldMapping.result || []).some(
      f => ['rttm', 'stm', 'json'].includes(f.param_type)
    );
    const hasRefTimeline = (props.fieldMapping.reference || []).some(
      f => ['rttm', 'stm', 'json'].includes(f.param_type)
    );
    if (hasResultTimeline || hasRefTimeline) return true;
  }

  // 检查 algorithmResults 数组
  const algoResults = props.algorithmResults;
  if (Array.isArray(algoResults)) {
    if (algoResults.some(item => ['rttm', 'stm', 'json'].includes(item.param_type))) {
      return true;
    }
  }

  // 检查 referenceParams 中的时间轴数据
  const refParams = props.referenceParams;
  if (refParams && typeof refParams === 'object') {
    const timelineKeyPattern = /rttm|stm/i;
    for (const [key, value] of Object.entries(refParams)) {
      if (timelineKeyPattern.test(key) && value) return true;
      if (value && typeof value === 'object' && ['rttm', 'stm'].includes(value.type)) return true;
    }
  }

  return false;
});

const audioUrl = computed(() => getAudioUrl(props.audioPath));

const resourceHeaderMap = computed(() => {
  const headers = Array.isArray(props.resourceHeaders) ? props.resourceHeaders : []
  const map = {}
  headers.forEach(h => {
    if (!h) return
    const key = h.key || h.resource
    const label = h.label || h.name || key
    if (key) map[String(key)] = String(label || key)
  })
  return map
})

const getDeviceName = (deviceId) => {
  const key = String(deviceId ?? '')
  const mapped = resourceHeaderMap.value?.[key]
  if (mapped) return mapped
  if (key.includes('_')) return key.split('_').slice(1).join('_')
  if (/^t\d+-\d{12}-/.test(key)) {
    const parts = key.split('-')
    if (parts.length >= 4) {
      const name = parts.slice(3).join('-')
      if (name) return name
    }
  }
  return key
};

const allMetricNames = computed(() => {
  if (!props.isComparison) return [];
  const names = new Set();
  Object.values(props.comparisonData).forEach(d => {
    if (d.metrics) Object.keys(d.metrics).forEach(m => names.add(m));
  });
  return Array.from(names);
});

const metricDecimalPlacesMap = computed(() => {
  const map = {}
  const list = Array.isArray(props.metricConfigs) ? props.metricConfigs : []
  list.forEach(m => {
    if (!m || !m.name) return
    const dp = m.decimalPlaces ?? m.decimal_places
    if (Number.isInteger(dp) && dp >= 0) map[String(m.name)] = dp
  })
  return map
})

const formatMetricForDisplay = (metricName, value) => {
  if (value === '-' || value === null || value === undefined) return '-'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return String(value)
  const dp = metricDecimalPlacesMap.value?.[String(metricName)]
  if (Number.isInteger(dp) && dp >= 0) return num.toFixed(dp)
  return String(num)
}

const getMetricRawValue = (device, metricName) => {
  return props.comparisonData[device]?.metrics?.[metricName] ?? '-'
}

const getMetricValue = (device, metricName) => {
  return formatMetricForDisplay(metricName, getMetricRawValue(device, metricName))
}

const comparisonTableColumns = computed(() => {
  const columns = [
    {
      key: 'metricName',
      label: '指标名称',
      resize: true,
      class: 'metric-name-column'
    }
  ]

  props.devices.forEach((device, index) => {
    columns.push({
      key: `device-${index}`,
      label: getDeviceName(device),
      resize: true,
      class: 'device-column',
      color: '#1677ff'
    })
  })

  return columns
})

const comparisonTableData = computed(() => {
  return allMetricNames.value.map(metricName => {
    const row = {
      metricName: metricName
    }

    props.devices.forEach((device, index) => {
      row[`device-${index}`] = getMetricValue(device, metricName)
    })

    return row
  })
})

const singleTableColumns = computed(() => {
  return [
    {
      key: 'metric',
      label: '指标名称',
      resize: true,
      class: 'metric-name-column'
    },
    {
      key: 'value',
      label: '指标数值',
      resize: true,
      class: 'value-column'
    },
    {
      key: 'score',
      label: '得分',
      resize: true,
      class: 'score-column'
    },
    {
      key: 'errorMessage',
      label: '详情/错误',
      resize: true,
      class: 'error-column'
    }
  ]
})

const singleTableData = computed(() => {
  return displayMetrics.value.map(item => {
    return {
      metric: item.metric,
      value: formatValue(item.value),
      rawValue: item.value,
      score: item.score ? `${item.score}分` : '-分',
      rawScore: item.score,
      errorMessage: item.errorMessage || '-',
      rawErrorMessage: item.errorMessage
    }
  })
})

// 从 referenceParams 中提取参考文本值
const getReferenceTextValue = (paramCode) => {
  const refParams = props.referenceParams || {};
  const data = refParams[paramCode];
  if (!data) return '';
  if (typeof data === 'string') return data;
  return data.text || data.value || '';
};

// 从结果数据中提取文本值（algorithmResults 现在是扁平数组）
const getResultTextValue = (device, paramCode) => {
  const items = props.algorithmResults || [];
  let item;
  if (props.isComparison && device !== 'default') {
    item = items.find(i => i.device === device && i.param_code === paramCode);
  } else {
    item = items.find(i => i.param_code === paramCode);
  }
  if (!item || item.value === undefined || item.value === null) return '无数据';
  const data = item.value;
  if (typeof data === 'string') return data;
  if (data.text) return data.text;
  if (data.value) return data.value;
  return JSON.stringify(data);
};

const expandedTexts = ref({});
const toggleText = (key) => {
  expandedTexts.value[key] = !expandedTexts.value[key];
};

const showAudioModal = ref(false);
const currentPlayingAudio = ref(null);
const audioLoadedStates = ref({});
const audioPageSize = 5;
const audioCurrentPage = ref(1);

const totalAudioPages = computed(() => {
  return Math.ceil(props.audioList.length / audioPageSize);
});

const paginatedAudioList = computed(() => {
  const start = (audioCurrentPage.value - 1) * audioPageSize;
  const end = start + audioPageSize;
  return props.audioList.slice(start, end);
});

const getGlobalAudioIndex = (localIndex) => {
  return (audioCurrentPage.value - 1) * audioPageSize + localIndex;
};

const formatDuration = (seconds) => {
  if (!seconds) return '';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const openAudioPlayer = (audio, index) => {
  currentPlayingAudio.value = { ...audio, index };
  showAudioModal.value = true;
};

const closeAudioModal = () => {
  showAudioModal.value = false;
  currentPlayingAudio.value = null;
};
</script>

<style scoped>
.test-case-report-detail {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.detail-section {
  background: white;
  border-radius: 8px;
}

.result-audio-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-audio-group {
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.result-audio-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary-color);
  margin-bottom: 8px;
}

.result-audio-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.result-audio-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--background-secondary);
  border-radius: 4px;
  font-size: 13px;
}

.result-audio-label {
  color: var(--text-primary);
}

.result-audio-link {
  color: var(--primary-color);
  text-decoration: none;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.result-audio-link:hover {
  text-decoration: underline;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
}

.metrics-table-wrapper {
  overflow-x: visible;
}

.modern-metrics-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  overflow: hidden;
  table-layout: auto;
}

.modern-metrics-table th {
  background-color: var(--background-secondary);
  text-align: left;
  padding: 10px 12px;
  color: var(--text-secondary);
  font-weight: 500;
  border-bottom: 1px solid var(--border-color);
  white-space: normal;
  word-break: break-word;
  max-width: 120px;
  line-height: 1.3;
}

.modern-metrics-table th:first-child {
  max-width: 150px;
}

.modern-metrics-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-color);
}

.modern-metrics-table td:first-child {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modern-metrics-table td:not(:first-child) {
  white-space: nowrap;
}

.dim-name {
  font-weight: 500;
  color: var(--text-primary);
}

.dim-value {
  color: var(--text-primary);
}

.dim-detail {
  color: var(--text-secondary);
  font-size: 12px;
  max-width: 400px;
}

.score-badge {
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.score-0 { background-color: #f5f5f5; color: #999; }
.score-1, .score-2 { background-color: #fff1f0; color: #f5222d; }
.score-3, .score-4 { background-color: #fff7e6; color: #fa8c16; }
.score-5 { background-color: #f6ffed; color: #52c41a; }

.audio-results-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.execution-results-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.result-subsection {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.subsection-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-color);
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--border-color);
  margin-bottom: 4px;
}

.audio-result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.audio-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}

.audio-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

.audio-meta-item i {
  font-size: 10px;
}

.audio-meta-item.spl {
  background-color: #e3f2fd;
  color: #1976d2;
}

.audio-meta-item.order {
  background-color: #fff3e0;
  color: #f57c00;
}

.audio-meta-item.noise-spl {
  background-color: #f3e5f5;
  color: #7b1fa2;
}

.audio-meta-item.device {
  background-color: #e8f5e9;
  color: #388e3c;
}

.result-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.modern-audio-player {
  width: 100%;
  height: 36px;
}

.audio-player-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 48px;
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f0ff 100%);
  border: 2px dashed #91d5ff;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  margin-top: 8px;
}

.audio-player-placeholder:hover {
  background: linear-gradient(135deg, #e6f0ff 0%, #d9eaff 100%);
  border-color: #1890ff;
  transform: scale(1.01);
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.15);
}

.placeholder-content {
  display: flex;
  align-items: center;
  gap: 10px;
}

.placeholder-icon {
  font-size: 24px;
  color: #1890ff;
}

.placeholder-text {
  font-size: 14px;
  font-weight: 500;
  color: #1890ff;
}

.placeholder-duration {
  font-size: 12px;
  color: #8c8c8c;
  padding: 2px 8px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}

.audio-item-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.audio-list-wrapper {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.no-audio-message {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: #8c8c8c;
  font-size: 14px;
}

.no-audio-message i {
  font-size: 18px;
}

.audio-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.pagination-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: white;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.pagination-btn:hover:not(:disabled) {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-info {
  font-size: 13px;
  color: var(--text-secondary);
}

.text-comparison-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.device-result-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.device-row-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--primary-color);
}

.text-comparison-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.reference-row {
  background: white;
  padding: 12px;
  border-radius: 8px;
}

.text-card {
  background: white;
  padding: 12px;
  border-radius: 6px;
  min-height: 80px;
}

.text-card.reference {
  background: white;
}

.text-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.collapsible-text {
  position: relative;
}

.text-content {
  line-height: 1.6;
  font-size: 13px;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.expanded .text-content {
  -webkit-line-clamp: unset;
  line-clamp: unset;
  display: block;
}

.expand-toggle {
  color: var(--primary-color);
  cursor: pointer;
  font-size: 12px;
  margin-top: 4px;
  font-weight: 500;
  text-align: right;
}

@media (max-width: 768px) {
  .text-comparison-grid {
    grid-template-columns: 1fr;
  }
}
</style>
