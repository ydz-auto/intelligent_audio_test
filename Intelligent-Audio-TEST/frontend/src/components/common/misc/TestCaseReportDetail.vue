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
import DataTable from '../data/DataTable.vue';
import TimelineComparison from '../../report/TimelineComparison.vue';
import AudioPlayerModal from '../audio/AudioPlayerModal.vue';
import AudioTimelineVisualization from '../audio/AudioTimelineVisualization.vue';
import { useTestCaseReportDetail } from './TestCaseReportDetail';

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

const {
  hasMetrics,
  comparisonTableColumns,
  comparisonTableData,
  singleTableColumns,
  singleTableData,
  formatValue,
  expandedTexts,
  toggleText,
  isMultiRound,
  multiRoundData,
  aggregatedMetrics,
  formatAggregatedValue,
  expandedRounds,
  toggleRound,
  getReferenceTextForRound,
  hasRoundEvaluation,
  roundEvalData,
  metricLabel,
  extractLlmReasoning,
  showAudioModal,
  currentPlayingAudio,
  closeAudioModal,
  openPathAudio,
  hasExecutionResults,
  referenceTextFields,
  resultTextFields,
  groupedResultTextFields,
  dimResultGroups,
  generalResultGroup,
  activeDimTab,
  getDeviceName,
  hasTimelineData,
  hasAudio,
  audioListWithTimeline,
  hasResultAudioData,
  isJsonString,
  formatJson,
} = useTestCaseReportDetail(props)
</script>

<style scoped>
@import './TestCaseReportDetail.css';
</style>
