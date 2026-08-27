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

    <div v-if="isMultiRound" class="detail-section">
      <h4 class="section-title"><i class="fas fa-layer-group"></i> 多轮对话结果 ({{ multiRoundData.totalRounds }} 轮)</h4>
      <div v-if="aggregatedMetrics" class="multi-round-aggregated">
        <div class="aggregated-card" v-if="aggregatedMetrics.avg_wer != null">
          <span class="aggregated-label">平均 WER</span>
          <span class="aggregated-value">{{ formatAggregatedValue(aggregatedMetrics.avg_wer) }}</span>
        </div>
        <div class="aggregated-card" v-if="aggregatedMetrics.avg_llm_judge != null">
          <span class="aggregated-label">平均 LLM 评分</span>
          <span class="aggregated-value">{{ formatAggregatedValue(aggregatedMetrics.avg_llm_judge) }}</span>
        </div>
        <div class="aggregated-card" v-if="aggregatedMetrics.avg_latency != null">
          <span class="aggregated-label">平均延迟</span>
          <span class="aggregated-value">{{ formatAggregatedValue(aggregatedMetrics.avg_latency) }}s</span>
        </div>
        <div class="aggregated-card" v-if="aggregatedMetrics.interruption_count != null">
          <span class="aggregated-label">打断次数</span>
          <span class="aggregated-value">{{ aggregatedMetrics.interruption_count || 0 }}</span>
        </div>
      </div>
      <div class="round-list">
        <div v-for="(round, idx) in multiRoundData.rounds" :key="idx" class="round-item" :class="{ expanded: expandedRounds[idx] }">
          <div class="round-header" @click="toggleRound(idx)">
            <span class="round-number">第 {{ idx + 1 }} 轮</span>
            <span v-if="round.latency != null" class="round-latency">延迟: {{ formatAggregatedValue(round.latency) }}s</span>
            <span v-if="round.interruption?.detected" class="round-interruption-badge">打断</span>
            <span class="expand-icon">{{ expandedRounds[idx] ? '▼' : '▶' }}</span>
          </div>
          <div v-if="expandedRounds[idx]" class="round-detail">
            <div class="round-field" v-if="round.input?.audio_name">
              <span class="round-field-label">输入音频</span>
              <span class="round-field-value">{{ round.input.audio_name }}</span>
            </div>
            <div class="round-field" v-if="round.output?.asr_text">
              <span class="round-field-label">ASR 输出</span>
              <span class="round-field-value">{{ round.output.asr_text }}</span>
            </div>
            <div class="round-field" v-if="getReferenceTextForRound(idx)">
              <span class="round-field-label">参考文本</span>
              <span class="round-field-value">{{ getReferenceTextForRound(idx) }}</span>
            </div>
            <div class="round-field" v-if="round.latency != null">
              <span class="round-field-label">延迟</span>
              <span class="round-field-value">{{ formatAggregatedValue(round.latency) }}s</span>
            </div>
            <div class="round-field" v-if="round.interruption?.detected">
              <span class="round-field-label">打断</span>
              <span class="round-field-value">
                {{ round.interruption.timestamp != null ? formatAggregatedValue(round.interruption.timestamp) + 's' : '检测到打断' }}
              </span>
            </div>
            <div class="round-field" v-if="hasRoundEvaluation(round)">
              <span class="round-field-label">维度评分</span>
              <div class="round-eval-badges">
                <span v-for="(score, dim) in roundEvalData(round)" :key="dim" class="eval-badge">
                  {{ metricLabel(dim) }}: {{ formatAggregatedValue(score) }}
                </span>
              </div>
            </div>
            <div class="round-field" v-if="round.evaluation?.llm_judge">
              <span class="round-field-label">LLM 评语</span>
              <span class="round-field-value">{{ extractLlmReasoning(round.evaluation) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AudioPlayerModal
      v-if="showAudioModal && currentPlayingAudio"
      :visible="showAudioModal"
      :audioId="currentPlayingAudio.id"
      :audioPath="currentPlayingAudio.path"
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
        <!-- 参考数据表格 -->
        <div v-if="referenceTextFields.length > 0" class="result-subsection">
          <div class="subsection-label"><i class="fas fa-bookmark"></i> 参考数据</div>
          <div class="kv-table">
            <div class="kv-table-row" v-for="field in referenceTextFields" :key="'ref_' + field.param_code">
              <div class="kv-table-key">{{ field.label || field.param_code }}</div>
              <div class="kv-table-value">
                <pre v-if="isJsonString(field.text)" class="json-formatted">{{ formatJson(field.text) }}</pre>
                <span v-else-if="(field.text || '').length > 200" class="collapsible-text" :class="{ expanded: expandedTexts['ref_' + field.param_code] }">
                  <span class="text-content">{{ field.text }}</span>
                  <span class="expand-toggle" @click="toggleText('ref_' + field.param_code)">
                    {{ expandedTexts['ref_' + field.param_code] ? '收起' : '展开' }}
                  </span>
                </span>
                <span v-else>{{ field.text }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 评估结果（维度 tab 切换） -->
        <div v-if="dimResultGroups.length" class="result-subsection">
          <div class="subsection-label"><i class="fas fa-clipboard-list"></i> 评估结果</div>
          <div class="dim-tab-container">
            <div class="dim-tab-bar sub">
              <button
                v-for="(group, idx) in dimResultGroups"
                :key="group.key"
                class="dim-tab-btn sub"
                :class="{ active: activeDimTab === idx }"
                @click="activeDimTab = idx"
              >
                {{ group.label }}
              </button>
            </div>
            <div class="dim-tab-content">
              <!-- 对比模式：按设备列 -->
              <template v-if="isComparison">
                <div v-for="device in devices" :key="device" class="device-block">
                  <div class="device-block-title">{{ getDeviceName(device) }}</div>
                  <div class="kv-table">
                    <div class="kv-table-row" v-for="field in dimResultGroups[activeDimTab]?.fields" :key="device + '_' + field.param_code">
                      <div class="kv-table-key">{{ field.label || field.param_code }}</div>
                      <div class="kv-table-value">
                        <button v-if="field.param_type === 'audio_file'" class="audio-play-btn" @click="openPathAudio(field.getValue(device))">
                          <i class="fas fa-play-circle"></i> 播放音频
                        </button>
                        <pre v-else-if="isJsonString(field.getValue(device))" class="json-formatted">{{ formatJson(field.getValue(device)) }}</pre>
                        <span v-else-if="String(field.getValue(device)).length > 200" class="collapsible-text" :class="{ expanded: expandedTexts[device + '_' + field.param_code] }">
                          <span class="text-content">{{ field.getValue(device) }}</span>
                          <span class="expand-toggle" @click="toggleText(device + '_' + field.param_code)">
                            {{ expandedTexts[device + '_' + field.param_code] ? '收起' : '展开' }}
                          </span>
                        </span>
                        <span v-else>{{ field.getValue(device) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
              <!-- 单设备模式 -->
              <template v-else>
                <div class="kv-table">
                  <div class="kv-table-row" v-for="field in dimResultGroups[activeDimTab]?.fields" :key="'res_' + field.param_code">
                    <div class="kv-table-key">{{ field.label || field.param_code }}</div>
                    <div class="kv-table-value">
                      <button v-if="field.param_type === 'audio_file'" class="audio-play-btn" @click="openPathAudio(field.getValue('default'))">
                        <i class="fas fa-play-circle"></i> 播放音频
                      </button>
                      <pre v-else-if="isJsonString(field.getValue('default'))" class="json-formatted">{{ formatJson(field.getValue('default')) }}</pre>
                      <span v-else-if="String(field.getValue('default')).length > 200" class="collapsible-text" :class="{ expanded: expandedTexts['default_' + field.param_code] }">
                        <span class="text-content">{{ field.getValue('default') }}</span>
                        <span class="expand-toggle" @click="toggleText('default_' + field.param_code)">
                          {{ expandedTexts['default_' + field.param_code] ? '收起' : '展开' }}
                        </span>
                      </span>
                      <span v-else>{{ field.getValue('default') }}</span>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- 设备/API 执行结果（独立区域） -->
        <div v-if="generalResultGroup.fields.length" class="result-subsection">
          <div class="subsection-label"><i class="fas fa-mobile-alt"></i> 设备/API 执行结果</div>
          <template v-if="isComparison">
            <div v-for="device in devices" :key="device" class="device-block">
              <div class="device-block-title">{{ getDeviceName(device) }}</div>
              <div class="kv-table">
                <div class="kv-table-row" v-for="field in generalResultGroup.fields" :key="device + '_' + field.param_code">
                  <div class="kv-table-key">{{ field.label || field.param_code }}</div>
                  <div class="kv-table-value">
                    <button v-if="field.param_type === 'audio_file'" class="audio-play-btn" @click="openPathAudio(field.getValue(device))">
                      <i class="fas fa-play-circle"></i> 播放音频
                    </button>
                    <pre v-else-if="isJsonString(field.getValue(device))" class="json-formatted">{{ formatJson(field.getValue(device)) }}</pre>
                    <span v-else-if="String(field.getValue(device)).length > 200" class="collapsible-text" :class="{ expanded: expandedTexts[device + '_' + field.param_code] }">
                      <span class="text-content">{{ field.getValue(device) }}</span>
                      <span class="expand-toggle" @click="toggleText(device + '_' + field.param_code)">
                        {{ expandedTexts[device + '_' + field.param_code] ? '收起' : '展开' }}
                      </span>
                    </span>
                    <span v-else>{{ field.getValue(device) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="kv-table">
              <div class="kv-table-row" v-for="field in generalResultGroup.fields" :key="'res_' + field.param_code">
                <div class="kv-table-key">{{ field.label || field.param_code }}</div>
                <div class="kv-table-value">
                  <button v-if="field.param_type === 'audio_file'" class="audio-play-btn" @click="openPathAudio(field.getValue('default'))">
                    <i class="fas fa-play-circle"></i> 播放音频
                  </button>
                  <pre v-else-if="isJsonString(field.getValue('default'))" class="json-formatted">{{ formatJson(field.getValue('default')) }}</pre>
                  <span v-else-if="String(field.getValue('default')).length > 200" class="collapsible-text" :class="{ expanded: expandedTexts['default_' + field.param_code] }">
                    <span class="text-content">{{ field.getValue('default') }}</span>
                    <span class="expand-toggle" @click="toggleText('default_' + field.param_code)">
                      {{ expandedTexts['default_' + field.param_code] ? '收起' : '展开' }}
                    </span>
                  </span>
                  <span v-else>{{ field.getValue('default') }}</span>
                </div>
              </div>
            </div>
          </template>
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
import { ref, computed, watch } from 'vue';
import { buildAudioUrl, normalizeAudioItem } from '../../utils/audioUtils';
import DataTable from './DataTable.vue';
import TimelineComparison from '../report/TimelineComparison.vue';
import AudioPlayerModal from './AudioPlayerModal.vue';
import AudioTimelineVisualization from './AudioTimelineVisualization.vue';
import reportService from '../../services/reportService';

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

const multiRoundAlgorithmResult = computed(() => {
  const algoResults = props.algorithmResults || [];
  if (algoResults.length === 0) return null;
  const first = algoResults[0];
  if (first && reportService.parseMultiRoundResult(first).isMultiRound) return first;
  for (const item of algoResults) {
    if (item?.value && typeof item.value === 'object' && reportService.parseMultiRoundResult(item.value).isMultiRound) return item.value;
  }
  return null;
});

const isMultiRound = computed(() => multiRoundAlgorithmResult.value !== null);

const multiRoundData = computed(() => {
  if (!multiRoundAlgorithmResult.value) return { isMultiRound: false, rounds: [], aggregated: null, totalRounds: 0 };
  return reportService.parseMultiRoundResult(multiRoundAlgorithmResult.value);
});

const aggregatedMetrics = computed(() => {
  if (!multiRoundData.value.isMultiRound) return null;
  if (multiRoundData.value.aggregated) return multiRoundData.value.aggregated;
  const rounds = multiRoundData.value.rounds;
  if (!rounds || rounds.length === 0) return null;
  const evals = rounds.map(r => r.evaluation || r.round_evaluation).filter(Boolean);
  const result = {};
  if (evals.length > 0) {
    const werSum = evals.reduce((s, e) => s + (e.wer || 0), 0);
    result.avg_wer = werSum / evals.length;
    const llmSum = evals.reduce((s, e) => s + (e.llm_judge || 0), 0);
    if (llmSum > 0) result.avg_llm_judge = llmSum / evals.length;
  }
  const latencySum = rounds.reduce((s, r) => s + (r.latency || 0), 0);
  result.avg_latency = latencySum / rounds.length;
  const interruptionCount = rounds.filter(r => r.interruption?.detected).length;
  if (interruptionCount > 0) result.interruption_count = interruptionCount;
  return result;
});

const expandedRounds = ref({});

const toggleRound = (idx) => {
  expandedRounds.value[idx] = !expandedRounds.value[idx];
};

const metricLabel = (key) => {
  const labels = {
    avg_wer: '平均 WER',
    avg_latency: '平均延迟',
    avg_llm_judge: '平均 LLM 评分',
    interruption_count: '打断次数',
    total_latency: '总延迟',
    wer: 'WER',
    llm_judge: 'LLM 评分',
    latency: '延迟',
  };
  return labels[key] || key;
};

const roundEvalData = (round) => {
  return round.evaluation || round.round_evaluation || null;
};

const hasRoundEvaluation = (round) => {
  const evalData = roundEvalData(round);
  return evalData && typeof evalData === 'object' && Object.keys(evalData).length > 0;
};

const formatAggregatedValue = (value) => {
  if (value === null || value === undefined) return '—';
  const num = Number(value);
  if (isNaN(num)) return String(value);
  return num.toFixed(2);
};

const getReferenceTextForRound = (idx) => {
  const fields = referenceTextFields.value;
  if (fields.length > 0) return fields[0].text;
  return '';
};

const extractLlmReasoning = (evaluation) => {
  if (!evaluation) return '';
  if (evaluation.reasoning) return evaluation.reasoning;
  if (evaluation.raw_response) {
    try {
      const parsed = typeof evaluation.raw_response === 'string' ? JSON.parse(evaluation.raw_response) : evaluation.raw_response;
      return parsed.reasoning || parsed.analysis || '';
    } catch (_e) { return ''; }
  }
  return '';
};

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

const getAudioUrl = buildAudioUrl;

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
  const refParams = props.referenceParams || {};
  const result = [];
  const seenCodes = new Set();

  // 1. 从 referenceParams 字典里直接提取所有 text 参数（含多轮展开的 code@round:N）
  for (const [code, data] of Object.entries(refParams)) {
    if (!data || typeof data !== 'object') continue;
    if (data.type !== 'text') continue;
    const text = data.text || data.value || '';
    if (typeof text !== 'string' || !text.trim()) continue;
    seenCodes.add(code);
    result.push({
      param_code: code,
      label: data.label || (code.includes('@round:') ? `${code.split('@round:')[0]} (第${code.split('@round:')[1]}轮)` : code),
      param_type: 'text',
      round_number: data.round_number,
      text,
    });
  }

  // 2. 补充 fieldMapping 里定义但 referenceParams 未覆盖的 text 字段
  const refFields = (props.fieldMapping?.reference || [])
    .map(f => ({
      ...f,
      param_code: f.param_code ?? f.paramCode,
      param_type: f.param_type ?? f.paramType ?? 'text',
    }))
    .filter(f => f.param_type === 'text');
  for (const field of refFields) {
    if (!seenCodes.has(field.param_code)) {
      const text = getReferenceTextValue(field.param_code);
      if (text && text.trim() && text !== '无数据') {
        seenCodes.add(field.param_code);
        result.push({ ...field, text });
      }
    }
  }

  // 按轮次排序
  result.sort((a, b) => {
    const ra = a.round_number ?? 0;
    const rb = b.round_number ?? 0;
    if (ra !== rb) return ra - rb;
    return (a.param_code || '').localeCompare(b.param_code || '');
  });
  return result;
});

// 动态结果文本字段
const resultTextFields = computed(() => {
  // 归一化 algorithmResults（兼容 camelCase / snake_case）
  const algoResults = (props.algorithmResults || []).map(i => ({
    ...i,
    param_code: i.param_code ?? i.paramCode,
    param_type: i.param_type ?? i.paramType,
    round_number: i.round_number ?? i.roundNumber,
    dimension_name: i.dimension_name ?? i.dimensionName,
  }));

  // 1. 从 algorithmResults 中提取所有 text 类型项（包含 question@round / answer@round）
  // 排除元数据字段（非用户关心的结果内容）
  const META_CODES = new Set([
    'test_type', 'testType',
    'algorithm_type', 'algorithmType',
    'total_rounds', 'totalRounds',
    'aggregated',
    'multi_round', 'multiRound',
    'session_id', 'sessionId',
    'context_mode', 'contextMode',
    'error',
  ]);
  const DISPLAY_TYPES = new Set(['text', 'timestamp', 'number', 'boolean', 'json', 'audio_file']);
  const textItems = [];
  const seenCodes = new Set();
  for (const item of algoResults) {
    const code = item.param_code;
    if (DISPLAY_TYPES.has(item.param_type) && code && !META_CODES.has(code) && !code.startsWith('rounds') && !seenCodes.has(code)) {
      seenCodes.add(code);
      textItems.push({
        param_code: code,
        label: item.label || code,
        param_type: item.param_type,
        round_number: item.round_number,
        dimension_name: item.dimension_name,
        getValue: (device) => getResultTextValue(device, code)
      });
    }
  }

  // 2. 补充 fieldMapping 里定义的 text/timestamp/number 字段（跳过 algorithmResults 已覆盖的）
  //    仅补充 algorithmResults 中有对应值的字段，避免显示"无数据"
  const fmFields = (props.fieldMapping?.result || [])
    .map(f => ({
      ...f,
      param_code: f.param_code ?? f.paramCode,
      param_type: f.param_type ?? f.paramType ?? 'text',
    }))
    .filter(f => DISPLAY_TYPES.has(f.param_type)
      && f.param_code && !META_CODES.has(f.param_code) && !f.param_code.startsWith('rounds'));
  const allResultCodes = new Set(algoResults.map(i => i.param_code));
  for (const f of fmFields) {
    if (!seenCodes.has(f.param_code) && allResultCodes.has(f.param_code)) {
      seenCodes.add(f.param_code);
      textItems.push({
        ...f,
        getValue: (device) => getResultTextValue(device, f.param_code)
      });
    }
  }

  // 按轮次排序，question 在前 answer 在后
  textItems.sort((a, b) => {
    const ra = a.round_number ?? 0;
    const rb = b.round_number ?? 0;
    if (ra !== rb) return ra - rb;
    return (a.param_code || '').localeCompare(b.param_code || '');
  });
  return textItems;
});

// 按维度分组结果文本字段
const groupedResultTextFields = computed(() => {
  const groups = {};
  const order = [];

  for (const field of resultTextFields.value) {
    const dimName = field.dimension_name || null;
    if (!groups[dimName]) {
      groups[dimName] = [];
      order.push(dimName);
    }
    groups[dimName].push(field);
  }

  // 通用分组（dimension_name 为 null 的）放最后
  const result = [];
  for (const key of order) {
    if (key !== null) {
      result.push({
        key: key,
        label: key,
        fields: groups[key]
      });
    }
  }
  if (groups[null]) {
    result.push({
      key: '_general',
      label: '其他结果',
      fields: groups[null]
    });
  }
  return result;
});

// 有维度归属的结果分组（维度评估结果）
const dimResultGroups = computed(() => {
  return groupedResultTextFields.value.filter(g => g.key !== '_general');
});

// 无维度归属的结果分组（设备/API 执行结果）
const generalResultGroup = computed(() => {
  const found = groupedResultTextFields.value.find(g => g.key === '_general');
  return found || { key: '_general', label: '设备/API 执行结果', fields: [] };
});

// 是否有结果音频
const hasResultAudioData = computed(() => {
  return props.resultAudios && Object.keys(props.resultAudios).length > 0;
});

const audioListWithTimeline = computed(() => {
  const list = props.audioList || [];
  if (list.length === 0) return [];
  return list.map(a => normalizeAudioItem(a));
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
  // 排序：按维度基础名分组，组内按轮次（round:N 升序）在前、整体（@overall）在后
  return Array.from(names).sort((a, b) => {
    const parseKey = (k) => {
      const m = k.match(/^(.*)@(round:(\d+)|overall)$/);
      if (!m) return { base: k, order: -1, rn: -1 }; // 单轮/无后缀，最前
      if (m[2] === 'overall') return { base: m[1], order: 1, rn: 9999 };
      return { base: m[1], order: 0, rn: parseInt(m[3], 10) };
    };
    const pa = parseKey(a), pb = parseKey(b);
    if (pa.base !== pb.base) return pa.base.localeCompare(pb.base, 'zh');
    if (pa.order !== pb.order) return pa.order - pb.order;
    return pa.rn - pb.rn;
  });
});

// 友好显示指标名：把内部 key 转成带" (第N轮)"/" (整体)"的标签
const formatMetricLabel = (key) => {
  const m = key.match(/^(.*)@round:(\d+)$/);
  if (m) return `${m[1]} (第${m[2]}轮)`;
  const m2 = key.match(/^(.*)@overall$/);
  if (m2) return `${m2[1]} (整体)`;
  return key;
};

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
  const entry = props.comparisonData[device]?.metrics?.[metricName]
  if (entry === undefined || entry === null) return '-'
  // 兼容 { metric, value } 对象和裸值两种格式
  if (typeof entry === 'object') return entry.value ?? '-'
  return entry
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
      metricName: formatMetricLabel(metricName)
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
  const norm = i => ({
    ...i,
    param_code: i.param_code ?? i.paramCode,
    param_type: i.param_type ?? i.paramType,
  });
  const normed = items.map(norm);
  let item;
  if (props.isComparison && device !== 'default') {
    // 先尝试精确匹配，再回退到包含匹配（快照可能使用完整资源名如 "1-小艺通话-1.0.0"）
    item = normed.find(i => i.device === device && i.param_code === paramCode)
         || normed.find(i => i.device && (i.device.includes(device) || device.includes(i.device)) && i.param_code === paramCode);
  } else {
    item = normed.find(i => i.param_code === paramCode);
  }
  if (!item || item.value === undefined || item.value === null) return '无数据';
  const data = item.value;
  // 时间戳类型：尝试格式化为可读时间
  if (item.param_type === 'timestamp') {
    const ts = typeof data === 'string' ? data : String(data);
    // 纯数字时间戳（秒或毫秒）
    if (/^\d{10,13}$/.test(ts.trim())) {
      const ms = ts.trim().length === 10 ? Number(ts.trim()) * 1000 : Number(ts.trim());
      const d = new Date(ms);
      if (!isNaN(d.getTime())) {
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
      }
    }
    // ISO 格式字符串
    const d = new Date(ts);
    if (!isNaN(d.getTime())) {
      const pad = n => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }
    return ts;
  }
  // 数值类型：格式化数字
  if (item.param_type === 'number') {
    if (typeof data === 'number') {
      return Number.isInteger(data) ? String(data) : data.toFixed(2);
    }
    const num = Number(data);
    if (!isNaN(num)) {
      return Number.isInteger(num) ? String(num) : num.toFixed(2);
    }
    return String(data);
  }
  // 布尔类型
  if (item.param_type === 'boolean') {
    if (typeof data === 'boolean') return data ? '是' : '否';
    return String(data);
  }
  if (typeof data === 'string') {
    // 尝试解析 JSON 字符串并格式化
    try {
      const parsed = JSON.parse(data);
      if (typeof parsed === 'object' && parsed !== null) {
        return JSON.stringify(parsed, null, 2);
      }
    } catch {}
    return data;
  }
  if (data.text) return data.text;
  if (data.value) return data.value;
  return JSON.stringify(data, null, 2);
};

const expandedTexts = ref({});
const toggleText = (key) => {
  expandedTexts.value[key] = !expandedTexts.value[key];
};

// JSON 格式化辅助
const isJsonString = (val) => {
  if (!val || typeof val !== 'string') return false;
  const s = val.trim();
  if (!s) return false;
  return (s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'));
};

const formatJson = (val) => {
  if (!val) return val;
  try {
    const parsed = typeof val === 'string' ? JSON.parse(val) : val;
    return JSON.stringify(parsed, null, 2);
  } catch {
    return val;
  }
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

// 打开音频路径（通过 stream-by-path）
const openPathAudio = (path) => {
  currentPlayingAudio.value = {
    path: path,
    label: path.split('\\').pop().split('/').pop(),
    type: 'api'
  };
  showAudioModal.value = true;
};

// 维度 tab 状态
const activeDimTab = ref(0);

watch(dimResultGroups, (newGroups) => {
  if (activeDimTab.value >= newGroups.length) {
    activeDimTab.value = 0;
  }
}, { flush: 'post' });
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
  color: var(--primary-color);
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
  font-size: 13px;
  color: #333;
}

.dim-value {
  font-size: 13px;
  color: #333;
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
  gap: 8px;
}

.subsection-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary-color);
  padding-bottom: 3px;
  border-bottom: 1px solid #e8e8e8;
  margin-bottom: 2px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.subsection-label i {
  color: var(--primary-color);
  font-size: 12px;
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

/* KV Table - 键值对表格样式 */
.kv-table {
  width: 100%;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.kv-table-row {
  display: flex;
  border-bottom: 1px solid #f5f5f5;
  min-height: 34px;
  align-items: stretch;
}

.kv-table-row:last-child {
  border-bottom: none;
}

.kv-table-row:hover {
  background: #fafcff;
}

.kv-table-key {
  flex: 0 0 180px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 500;
  color: #8c8c8c;
  background: #fbfbfb;
  border-right: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
}

.kv-table-value {
  flex: 1;
  padding: 7px 12px;
  font-size: 13px;
  color: #333;
  display: flex;
  align-items: center;
  overflow: hidden;
  line-height: 1.5;
}

.kv-table-value pre.json-formatted {
  margin: 0;
  width: 100%;
}

.collapsible-text {
  position: relative;
  width: 100%;
}

.collapsible-text .text-content {
  line-height: 1.6;
  font-size: 13px;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.collapsible-text.expanded .text-content {
  -webkit-line-clamp: unset;
  line-clamp: unset;
  overflow: visible;
}

.json-formatted {
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  background: #f8f9fa;
  padding: 8px;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
  line-height: 1.5;
}

.expand-toggle {
  color: var(--primary-color);
  cursor: pointer;
  font-size: 12px;
  margin-top: 4px;
  font-weight: 500;
  display: inline-block;
  margin-left: 8px;
}

@media (max-width: 768px) {
  .kv-table-key {
    flex: 0 0 120px;
  }
  .multi-round-aggregated {
    flex-direction: column;
  }
}

.multi-round-aggregated {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.aggregated-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 20px;
  background: var(--background-secondary);
  border-radius: 6px;
  min-width: 120px;
}

.aggregated-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.aggregated-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--primary-color);
}

.round-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.round-item {
  border: 1px solid var(--border-color);
  border-radius: 6px;
  overflow: hidden;
}

.round-item.expanded {
  border-color: var(--primary-color);
}

.round-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  background: var(--background-secondary);
  transition: background 0.2s;
}

.round-header:hover {
  background: #e8edf3;
}

.round-number {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.round-latency {
  font-size: 12px;
  color: var(--text-secondary);
}

.round-interruption-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  background: #fff1f0;
  color: #f5222d;
  font-weight: 500;
}

.expand-icon {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary);
}

.round-detail {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.round-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.round-field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.round-field-value {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
}

.round-eval-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.eval-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  background: #f0f5ff;
  color: #1677ff;
  font-weight: 500;
}

/* 维度 Tab 切换 */
.dim-tab-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dim-tab-bar {
  display: flex;
  gap: 2px;
  border-bottom: 2px solid var(--primary-color);
  flex-wrap: wrap;
}

.dim-tab-btn {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid transparent;
  border-bottom: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px 4px 0 0;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 4px;
}

.dim-tab-btn:hover {
  background: #f0f5ff;
  color: var(--primary-color);
}

.dim-tab-btn.active {
  background: var(--primary-color);
  color: white;
  font-weight: 600;
}

.dim-tab-btn i {
  font-size: 12px;
}

/* 第二行子 tab */
.dim-tab-bar.sub {
  border-bottom: 1px solid #e8e8e8;
  padding-left: 8px;
}

.dim-tab-btn.sub {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
  border-bottom: none;
  margin-bottom: -1px;
  transition: all 0.2s ease;
  appearance: none;
  -webkit-appearance: none;
}

.dim-tab-btn.sub:hover {
  background: #fff5ef;
}

.dim-tab-btn.sub.active {
  background: rgba(255, 106, 0, 0.1);
  color: #FF6A00;
  border-color: rgba(255, 106, 0, 0.3);
  font-weight: 500;
}

.dim-tab-content {
  padding-top: 4px;
}

/* 对比模式维度块 */
.dimension-block {
  padding: 4px 0;
}

.dimension-block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary-color);
  background: #f0f5ff;
  padding: 4px 10px;
  border-radius: 4px;
  display: inline-block;
  margin-bottom: 6px;
}

.device-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 6px;
}

.device-block-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--primary-color);
  padding: 2px 0;
}

/* 音频播放按钮 */
.audio-play-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
  color: #595959;
  background: #f5f5f5;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.audio-play-btn:hover {
  background: #eff6ff;
  border-color: #91d5ff;
  color: #1890ff;
}

.audio-play-btn i {
  font-size: 14px;
}
</style>
