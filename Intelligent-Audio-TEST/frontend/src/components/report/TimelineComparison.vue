<template>
  <div class="timeline-comparison">
    <div class="timeline-header">
      <div class="timeline-title">
        <i class="fas fa-layer-group"></i>
        <span>时间轴对比</span>
      </div>
      <div class="timeline-controls">
        <select
          v-model="selectedResource"
          class="resource-select"
          @change="handleResourceChange"
        >
          <option v-for="res in resources" :key="res" :value="res">
            {{ formatResourceName(res) }}
          </option>
        </select>
        <div class="speaker-filters">
          <label class="speaker-filter-item">
            <input
              type="checkbox"
              :checked="selectedSpeakers.length === 0 || selectedSpeakers.includes('all')"
              @change="toggleAllSpeakers($event)"
            />
            <span>全部</span>
          </label>
          <label
            v-for="spk in speakerList"
            :key="spk"
            class="speaker-filter-item"
          >
            <input
              type="checkbox"
              :value="spk"
              v-model="selectedSpeakers"
            />
            <span>{{ spk }}</span>
          </label>
        </div>
        <div class="zoom-controls">
          <button @click="zoomOut" class="zoom-btn" title="缩小">-</button>
          <span class="zoom-level">{{ scale.toFixed(1) }}x</span>
          <button @click="zoomIn" class="zoom-btn" title="放大">+</button>
          <button @click="resetZoom" class="zoom-btn" title="重置">⟲</button>
        </div>
      </div>
    </div>

    <div class="timeline-content" v-if="hasTimelineData" @wheel.prevent="handleWheelZoom"
         :style="{ '--timeline-scale': scale }">
      <div
        v-for="speaker in getFilteredSpeakerList()"
        :key="speaker"
        class="speaker-row"
      >
        <div class="speaker-header">
          <span class="speaker-name">{{ speaker }}</span>
          <span v-if="speakerMapping[speaker]" class="speaker-mapping">
            → {{ speakerMapping[speaker] }}
          </span>
        </div>
        <div class="speaker-timeline">
          <div class="timeline-row reference-row">
            <div class="row-label">参考</div>
            <div class="track-segments">
              <div
                v-for="(seg, idx) in referenceSegmentsBySpeaker[speaker] || []"
                :key="'ref-' + speaker + '-' + idx"
                class="segment reference-segment"
                :style="getSegmentStyle(seg)"
                :title="seg.text"
              >
                <span class="segment-text">{{ seg.text }}</span>
              </div>
              <div v-if="(referenceSegmentsBySpeaker[speaker] || []).length === 0" class="no-segment">
                无数据
              </div>
            </div>
          </div>
          <div class="timeline-row result-row">
            <div class="row-label">结果</div>
            <div class="track-segments">
              <div
                v-for="(seg, idx) in getResultSegmentsForSpeaker(speaker)"
                :key="'res-' + speaker + '-' + idx"
                class="segment result-segment"
                :class="{ 'match-segment': isMatchSegment(speaker, seg) }"
                :style="getSegmentStyle(seg)"
                :title="seg.text"
              >
                <span class="segment-text">{{ seg.text }}</span>
              </div>
              <div v-if="getResultSegmentsForSpeaker(speaker).length === 0" class="no-segment">
                无数据
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="timeline-scale">
        <span class="scale-start">0s</span>
        <div class="scale-bar">
          <div
            v-for="(tick, idx) in timeTicks"
            :key="idx"
            class="scale-tick"
            :style="{ left: tick.percent + '%' }"
          >
            <span class="tick-label">{{ tick.label }}</span>
          </div>
        </div>
        <span class="scale-end">{{ effectiveDuration.toFixed(1) }}s</span>
      </div>
    </div>

    <div class="timeline-empty" v-else>
      <i class="fas fa-chart-line"></i>
      <span>暂无时间轴数据</span>
    </div>
  </div>
</template>

<script>
export default {
  name: 'TimelineComparison',
  props: {
    algorithmResults: {
      type: Object,
      default: () => ({})
    },
    referenceParams: {
      type: Object,
      default: () => ({})
    },
    algorithmType: {
      type: String,
      default: ''
    },
    results: {
      type: Array,
      default: () => []
    }
  },
  data() {
    return {
      selectedResource: null,
      selectedSpeakers: [],
      scale: 1,
      _wheelTimeout: null,
      _speakerMappingCache: null,
      _speakerMappingCacheKey: null,
      _mockReferenceData: [
        { speaker: 'spk1', start: 0.5, end: 3.2, text: '你好，欢迎光临' },
        { speaker: 'spk1', start: 5.8, end: 8.5, text: '今天天气不错' },
        { speaker: 'spk2', start: 2.8, end: 6.5, text: '请问有什么可以帮您' },
        { speaker: 'spk3', start: 0.0, end: 5.0, text: '我想查询一下订单' },
        { speaker: 'spk3', start: 7.2, end: 9.8, text: '谢谢您的帮助' }
      ],
      _mockResultData: [
        { speaker: 'spk1', start: 0.6, end: 3.1, text: '你好，欢迎光临' },
        { speaker: 'spk1', start: 5.9, end: 8.4, text: '今天天气不错' },
        { speaker: 'spk2', start: 2.9, end: 6.0, text: '请问有什么可以帮您' },
        { speaker: 'spk3', start: 0.1, end: 4.9, text: '我想查询一下订单' },
        { speaker: 'spk3', start: 7.3, end: 9.7, text: '谢谢您的帮助' },
        { speaker: 'spk4', start: 4.0, end: 5.2, text: '额外检测到的说话' }
      ]
    };
  },
  computed: {
    maxDuration() {
      const refData = this.getTimelineData('reference');
      const resData = this.getTimelineData('result');
      const allData = [...refData, ...resData];
      if (allData.length === 0) return 10;
      const max = Math.max(...allData.map(s => s.end || 0));
      return Math.ceil(max / 5) * 5 || 10;
    },

    effectiveDuration() {
      return this.maxDuration / this.scale;
    },

    timeTicks() {
      const duration = this.effectiveDuration;
      const ticks = [];
      const interval = duration <= 10 ? 2 : (duration <= 30 ? 5 : 10);
      for (let i = 0; i <= duration; i += interval) {
        ticks.push({
          label: `${i}s`,
          percent: (i / duration) * 100
        });
      }
      return ticks;
    },

    resources() {
      const results = this.results || [];
      
      if (results.length > 0) {
        return results.map(r => r.resource);
      }
      
      const algoResults = this.algorithmResults || {};
      const keys = Object.keys(algoResults);
      
      if (keys.length === 0) {
        return ['default'];
      }
      
      const firstValue = algoResults[keys[0]];
      if (firstValue && typeof firstValue === 'object') {
        const nestedKeys = Object.keys(firstValue);
        const hasTimelineData = nestedKeys.some(k => 
          ['rttm', 'stm', 'segment', 'timeline'].some(key => k.toLowerCase().includes(key))
        );
        if (hasTimelineData) {
          return keys.length > 1 ? keys : ['default'];
        }
      }
      
      return keys.length > 1 ? keys : ['default'];
    },
    hasTimelineData() {
      const refData = this.cachedReferenceData;
      const resData = this.cachedResultData;
      return (refData && refData.length > 0) || (resData && resData.length > 0);
    },
    timelineFields() {
      const fields = ['rttm_res', 'stm_res', 'rttm_ref', 'stm_ref', 'rttmRes', 'stmRes', 'rttmRef', 'stmRef'];
      const algoType = this.algorithmType?.toLowerCase() || '';
      if (algoType.includes('speaker') || algoType.includes('diarization')) {
        return ['rttm_res', 'stm_res', 'rttmRes', 'stmRes', 'rttm_ref', 'stm_ref', 'rttmRef', 'stmRef'];
      }
      return fields;
    },
    speakerList() {
      const refData = this.cachedReferenceData;
      const resData = this.cachedResultData;
      
      const refSpeakers = [];
      const resOnlySpeakers = [];
      
      if (refData && Array.isArray(refData) && refData.length > 0) {
        const uniqueRefSpeakers = [...new Set(refData.map(s => s && s.speaker ? s.speaker : 'spk0'))];
        refSpeakers.push(...uniqueRefSpeakers);
      }
      
      if (resData && Array.isArray(resData) && resData.length > 0) {
        const uniqueResSpeakers = [...new Set(resData.map(s => s && s.speaker ? s.speaker : 'spk0'))];
        const mappedResSpeakers = new Set(Object.values(this.speakerMapping));
        for (const spk of uniqueResSpeakers) {
          if (!mappedResSpeakers.has(spk)) {
            resOnlySpeakers.push(spk);
          }
        }
      }
      
      return [...refSpeakers.sort(), ...resOnlySpeakers.sort()];
    },
    cachedReferenceData() {
      return this.getTimelineData('reference');
    },
    cachedResultData() {
      return this.getTimelineData('result');
    },
    referenceSegmentsBySpeaker() {
      const data = this.cachedReferenceData || [];
      const grouped = {};
      data.forEach(s => {
        const speaker = s.speaker || 'spk0';
        if (!grouped[speaker]) grouped[speaker] = [];
        grouped[speaker].push(s);
      });
      return grouped;
    },
    resultSegmentsBySpeaker() {
      const data = this.cachedResultData || [];
      const grouped = {};
      data.forEach(s => {
        const speaker = s.speaker || 'spk0';
        if (!grouped[speaker]) grouped[speaker] = [];
        grouped[speaker].push(s);
      });
      return grouped;
    },
    speakerMapping() {
      const refData = this.cachedReferenceData || [];
      const resData = this.cachedResultData || [];
      const cacheKey = `${refData.length}-${resData.length}-${refData.map(s => s.speaker).join(',')}-${resData.map(s => s.speaker).join(',')}`;
      if (this._speakerMappingCacheKey === cacheKey && this._speakerMappingCache) {
        return this._speakerMappingCache;
      }
      const mapping = this.computeOptimalSpeakerMapping(refData, resData);
      this._speakerMappingCache = mapping;
      this._speakerMappingCacheKey = cacheKey;
      return mapping;
    }
  },
  mounted() {
  },
  watch: {
    resources: {
      immediate: true,
      handler(newResources) {
        if (newResources?.length > 0 && !this.selectedResource) {
          this.selectedResource = newResources[0];
        }
      }
    }
  },
  methods: {
    getFilteredSpeakerList() {
      if (!this.selectedSpeakers || this.selectedSpeakers.length === 0 || this.selectedSpeakers.includes('all')) {
        return this.speakerList;
      }
      return this.speakerList.filter(s => this.selectedSpeakers.includes(s));
    },

    computeOptimalSpeakerMapping(referenceSegments, resultSegments) {
      const refSpeakers = [...new Set(referenceSegments.map(s => s.speaker || 'spk0'))];
      const resSpeakers = [...new Set(resultSegments.map(s => s.speaker || 'spk0'))];
      
      if (refSpeakers.length === 0 || resSpeakers.length === 0) {
        return {};
      }
      
      if (refSpeakers.length === 1 && resSpeakers.length === 1) {
        return { [refSpeakers[0]]: resSpeakers[0] };
      }
      
      // 预计算每个说话人的片段
      const refSegsMap = {};
      const resSegsMap = {};
      for (const spk of refSpeakers) {
        refSegsMap[spk] = referenceSegments.filter(s => (s.speaker || 'spk0') === spk);
      }
      for (const spk of resSpeakers) {
        resSegsMap[spk] = resultSegments.filter(s => (s.speaker || 'spk0') === spk);
      }
      
      // 使用贪心算法计算最优匹配
      const overlaps = [];
      for (const refSpk of refSpeakers) {
        for (const resSpk of resSpeakers) {
          const overlapTime = this.computeOverlapTime(refSegsMap[refSpk], resSegsMap[resSpk]);
          overlaps.push({ refSpk, resSpk, overlapTime });
        }
      }
      
      // 按重叠时间降序排序
      overlaps.sort((a, b) => b.overlapTime - a.overlapTime);
      
      // 贪心选择
      const speakerMapping = {};
      const usedRef = new Set();
      const usedRes = new Set();
      
      for (const { refSpk, resSpk, overlapTime } of overlaps) {
        if (!usedRef.has(refSpk) && !usedRes.has(resSpk) && overlapTime > 0) {
          speakerMapping[refSpk] = resSpk;
          usedRef.add(refSpk);
          usedRes.add(resSpk);
        }
      }
      
      return speakerMapping;
    },

    computeOverlapTime(seg1, seg2) {
      let totalOverlap = 0;
      
      for (const a of seg1) {
        for (const b of seg2) {
          const overlapStart = Math.max(a.start || 0, b.start || 0);
          const overlapEnd = Math.min(a.end || 0, b.end || 0);
          if (overlapEnd > overlapStart) {
            totalOverlap += overlapEnd - overlapStart;
          }
        }
      }
      
      return totalOverlap;
    },

    hungarianAlgorithm(costMatrix) {
      const n = costMatrix.length;
      if (n === 0) return [];
      
      const m = costMatrix[0].length;
      const u = new Array(n + 1).fill(0);
      const v = new Array(m + 1).fill(0);
      const p = new Array(m + 1).fill(0);
      const way = new Array(m + 1).fill(0);
      
      for (let i = 1; i <= n; i++) {
        p[0] = i;
        let j0 = 0;
        const minv = new Array(m + 1).fill(Infinity);
        const used = new Array(m + 1).fill(false);
        
        do {
          used[j0] = true;
          const i0 = p[j0];
          let delta = Infinity;
          let j1 = 0;
          
          for (let j = 1; j <= m; j++) {
            if (!used[j]) {
              const cur = costMatrix[i0 - 1][j - 1] - u[i0] - v[j];
              if (cur < minv[j]) {
                minv[j] = cur;
                way[j] = j0;
              }
              if (minv[j] < delta) {
                delta = minv[j];
                j1 = j;
              }
            }
          }
          
          for (let j = 0; j <= m; j++) {
            if (used[j]) {
              u[p[j]] += delta;
              v[j] -= delta;
            } else {
              minv[j] -= delta;
            }
          }
          
          j0 = j1;
        } while (p[j0] !== 0);
        
        do {
          const j1 = way[j0];
          p[j0] = p[j1];
          j0 = j1;
        } while (j0 !== 0);
      }
      
      const result = new Array(n).fill(-1);
      for (let j = 1; j <= m; j++) {
        if (p[j] !== 0) {
          result[p[j] - 1] = j - 1;
        }
      }
      
      return result;
    },

    isTimelineField(key) {
      const timelineKeywords = ['rttm', 'stm', 'segment', 'timeline'];
      return timelineKeywords.some(k => key.toLowerCase().includes(k));
    },

    getTimelineData(type) {
      const algoResults = this.algorithmResults || {};
      const refParams = this.referenceParams || {};
      const selectedResource = this.selectedResource;
      
      const stmKeys = ['stmRes', 'stm_res', 'stmRef', 'stm_ref', 'stm_hyp', 'stmHyp'];
      const rttmKeys = ['rttmRes', 'rttm_res', 'rttmRef', 'rttm_ref', 'rttm_hyp', 'rttmHyp'];
      
      const processAlgoResult = (resultObj) => {
        if (!resultObj || typeof resultObj !== 'object') return null;
        
        for (const key of stmKeys) {
          if (resultObj[key]) {
            const data = this.parseTimelineData(resultObj[key]);
            if (Array.isArray(data) && data.length > 0) {
              return data;
            }
          }
        }
        
        for (const key of rttmKeys) {
          if (resultObj[key]) {
            const data = this.parseTimelineData(resultObj[key]);
            if (Array.isArray(data) && data.length > 0) {
              return data;
            }
          }
        }
        
        return null;
      };
      
      let algoKeys = Object.keys(algoResults);
      if (selectedResource && selectedResource !== 'default' && algoKeys.includes(selectedResource)) {
        algoKeys = [selectedResource];
      }
      
      if (type === 'result') {
        for (const algoKey of algoKeys) {
          const algoData = algoResults[algoKey];
          const result = processAlgoResult(algoData);
          if (result) {
            return [...result];
          }
        }
      }
      
      if (type === 'reference') {
        const result = processAlgoResult(refParams);
        if (result) {
          return [...result];
        }
      }

      return [];
    },

    parseTimelineData(data) {
      if (!data) return [];
      
      if (Array.isArray(data)) {
        return data;
      }
      
      if (typeof data === 'string') {
        try {
          const parsed = JSON.parse(data);
          if (Array.isArray(parsed)) return parsed;
          if (parsed.segments) return parsed.segments;
          return parsed;
        } catch (e) {
          const rttmResult = this.parseRttmText(data);
          if (rttmResult.length > 0) return rttmResult;
          return this.parseStmText(data);
        }
      }
      
      if (typeof data === 'object') {
        if (data.json) {
          if (Array.isArray(data.json)) {
            return data.json;
          }
          if (typeof data.json === 'string') {
            try {
              const parsed = JSON.parse(data.json);
              if (Array.isArray(parsed) && parsed.length > 0) return parsed;
            } catch (e) {
            }
          }
        }
        
        if (data.text && typeof data.text === 'string') {
          const rttmResult = this.parseRttmText(data.text);
          if (rttmResult.length > 0) return rttmResult;
          const stmResult = this.parseStmText(data.text);
          if (stmResult.length > 0) return stmResult;
        }
        
        const stmJson = data.stm_res?.json || data.stmRef?.json || data.stm?.json;
        if (stmJson) {
          if (Array.isArray(stmJson)) {
            return stmJson;
          }
          if (typeof stmJson === 'string') {
            try {
              const parsed = JSON.parse(stmJson);
              if (Array.isArray(parsed) && parsed.length > 0) return parsed;
            } catch (e) {
            }
          }
        }
        
        // STM text
        const stmText = data.stm_res?.text || data.stmRef?.text || data.stm?.text || 
                        data.stm_res?.e2e?.text || data.stmRef?.e2e?.text || data.stm?.e2e?.text ||
                        data.stm_res?.api?.text || data.stmRef?.api?.text || data.stm?.api?.text;
        if (stmText && typeof stmText === 'string') {
          const stmResult = this.parseStmText(stmText);
          if (stmResult.length > 0) {
            return stmResult;
          }
        }
        
        const rttmJson = data.rttm_res?.json || data.rttmRef?.json || data.rttm?.json;
        if (rttmJson) {
          if (Array.isArray(rttmJson)) {
            return rttmJson;
          }
          if (typeof rttmJson === 'string') {
            try {
              const parsed = JSON.parse(rttmJson);
              if (Array.isArray(parsed) && parsed.length > 0) return parsed;
            } catch (e) {
            }
          }
        }
        
        const rttmText = data.rttm_res?.text || data.rttmRef?.text || data.rttm?.text ||
                        data.rttm_res?.e2e?.text || data.rttmRef?.e2e?.text || data.rttm?.e2e?.text ||
                        data.rttm_res?.api?.text || data.rttmRef?.api?.text || data.rttm?.api?.text;
        if (rttmText && typeof rttmText === 'string') {
          const rttmResult = this.parseRttmText(rttmText);
          if (rttmResult.length > 0) {
            return rttmResult;
          }
        }
        
        if (data.json) {
          if (Array.isArray(data.json)) {
            return data.json;
          }
          if (typeof data.json === 'string') {
            try {
              const parsed = JSON.parse(data.json);
              if (Array.isArray(parsed) && parsed.length > 0) return parsed;
            } catch (e) {
            }
          }
        }
        
        if (data.text && typeof data.text === 'string') {
          const rttmResult = this.parseRttmText(data.text);
          if (rttmResult.length > 0) return rttmResult;
          return this.parseStmText(data.text);
        }
        if (data.e2e && data.e2e.text && typeof data.e2e.text === 'string') {
          const rttmResult = this.parseRttmText(data.e2e.text);
          if (rttmResult.length > 0) return rttmResult;
          return this.parseStmText(data.e2e.text);
        }
        if (data.api && data.api.text && typeof data.api.text === 'string') {
          const rttmResult = this.parseRttmText(data.api.text);
          if (rttmResult.length > 0) return rttmResult;
          return this.parseStmText(data.api.text);
        }
      }
      
      return [];
    },

    parseRttmText(text) {
      if (!text || typeof text !== 'string') return [];
      const lines = text.split('\n');
      const segments = [];

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        if (trimmed.startsWith('SPEAKER')) {
          const parts = trimmed.split(/\s+/);
          if (parts.length >= 8) {
            const startTime = parseFloat(parts[3]) || 0;
            const duration = parseFloat(parts[4]) || 0;
            const segment = {
              speaker: parts[7] || 'spk0',
              start: startTime,
              end: startTime + duration,
              text: ''
            };
            segments.push(segment);
          }
        }
      }
      
      return segments;
    },

    parseStmText(text) {
      if (!text || typeof text !== 'string') return [];
      const lines = text.split('\n');
      const segments = [];

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        
        if (trimmed.startsWith(';;')) continue;
        
        const parts = trimmed.split(/\s+/);
        if (parts.length >= 6) {
          const startTime = parseFloat(parts[3]) || 0;
          const endTime = parseFloat(parts[4]) || 0;
          const speaker = parts[2] || 'spk0';
          
          let textContent = '';
          const angleBracketIdx = parts.findIndex(p => p.startsWith('<'));
          if (angleBracketIdx !== -1 && angleBracketIdx < parts.length - 1) {
            textContent = parts.slice(angleBracketIdx + 1).join(' ').replace(/>\s*$/, '');
          }
          
          const segment = {
            speaker: speaker,
            start: startTime,
            end: endTime,
            text: textContent
          };
          segments.push(segment);
        }
      }
      
      return segments;
    },

    referenceSpeakers() {
      const data = this.getTimelineData('reference');
      return [...new Set(data.map(s => s.speaker || 'spk0'))].sort();
    },

    resultSpeakers() {
      const data = this.getTimelineData('result');
      return [...new Set(data.map(s => s.speaker || 'spk0'))].sort();
    },

    getSegmentStyle(seg) {
      const start = seg.start || 0;
      const end = seg.end || start + 1;
      const duration = end - start;
      const maxDur = this.maxDuration / this.scale;

      return {
        left: `${(start / maxDur) * 100}%`,
        width: `${Math.max((duration / maxDur) * 100, 3)}%`
      };
    },

    isMatchSegment(speaker, seg) {
      const mappedSpeaker = this.speakerMapping[speaker];
      if (!mappedSpeaker) return false;
      
      const resData = this.cachedResultData || [];
      const resSegments = resData.filter(s => (s.speaker || 'spk0') === mappedSpeaker);
      
      const tolerance = 0.5;
      return resSegments.some(resSeg =>
        Math.abs(resSeg.start - seg.start) < tolerance &&
        Math.abs(resSeg.end - seg.end) < tolerance
      );
    },

    getResultSegmentsForSpeaker(refSpeaker) {
      const mappedSpeaker = this.speakerMapping[refSpeaker];
      if (mappedSpeaker) {
        return this.resultSegmentsBySpeaker[mappedSpeaker] || [];
      }
      return this.resultSegmentsBySpeaker[refSpeaker] || [];
    },

    handleResourceChange(event) {
      this.selectedResource = event.target.value;
    },

    toggleAllSpeakers(event) {
      if (event.target.checked) {
        this.selectedSpeakers = [];
      }
    },

    handleWheelZoom(event) {
      const delta = event.deltaY > 0 ? -0.2 : 0.2;
      this.scale = Math.max(0.5, Math.min(5, this.scale + delta));
    },

    zoomIn() {
      this.scale = Math.min(5, this.scale + 0.2);
    },

    zoomOut() {
      this.scale = Math.max(0.5, this.scale - 0.2);
    },

    resetZoom() {
      this.scale = 1;
    },

    formatResourceName(res) {
      if (!res) return '未知资源';
      if (res.includes('_')) {
        return res.split('_').slice(1).join(' ');
      }
      return res;
    }
  }
};
</script>

<style scoped>
.timeline-comparison {
  background: white;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.timeline-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.timeline-title i {
  color: #1890ff;
}

.resource-select {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  background: #fff;
  cursor: pointer;
  min-width: 150px;
}

.resource-select:hover {
  border-color: #40a9ff;
}

.resource-select:focus {
  border-color: #40a9ff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

.speaker-select {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  background: #fff;
  cursor: pointer;
  min-width: 120px;
  height: 60px;
}

.speaker-select:hover {
  border-color: #40a9ff;
}

.speaker-select:focus {
  border-color: #40a9ff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

.speaker-filters {
  display: flex;
  gap: 12px;
  align-items: center;
}

.speaker-filter-item {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 14px;
  user-select: none;
}

.speaker-filter-item input[type="checkbox"] {
  cursor: pointer;
  width: 14px;
  height: 14px;
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.speaker-row {
  background: #fff;
  border-radius: 6px;
  padding: 12px;
  border: 1px solid #e8e8e8;
}

.speaker-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.speaker-name {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.speaker-mapping {
  font-size: 12px;
  color: #1677ff;
  margin-left: 8px;
}

.speaker-timeline {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.timeline-row {
  display: flex;
  align-items: center;
  min-height: 28px;
}

.row-label {
  width: 40px;
  font-size: 12px;
  font-weight: 500;
  color: #888;
  flex-shrink: 0;
}

.reference-row .row-label {
  color: #52c41a;
}

.result-row .row-label {
  color: #1890ff;
}

.reference-row .track-segments {
  background: #f6ffed;
  border: 1px dashed #b7eb8f;
}

.result-row .track-segments {
  background: #e6f7ff;
  border: 1px dashed #91d5ff;
}

.speaker-label {
  width: 80px;
  font-size: 12px;
  font-weight: 500;
  color: #888;
  flex-shrink: 0;
}

.track-segments {
  flex: 1;
  position: relative;
  height: 28px;
  background: #f5f5f5;
  border-radius: 4px;
  overflow: hidden;
}

.segment {
  position: absolute;
  height: 24px;
  top: 2px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  padding: 0 6px;
  overflow: hidden;
  cursor: pointer;
  transition: left 0.15s, width 0.15s, transform 0.2s;
}

.segment:hover {
  transform: scaleY(1.1);
  z-index: 10;
}

.reference-segment {
  background: #d9f7be;
  border: 1px solid #95de64;
}

.result-segment {
  background: #bae7ff;
  border: 1px solid #69c0ff;
}

.result-segment.match-segment {
  background: #ffd666;
  border-color: #ffc069;
}

.segment-text {
  font-size: 11px;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #999;
}

.timeline-empty i {
  font-size: 32px;
  margin-bottom: 8px;
  color: #d9d9d9;
}

.timeline-scale {
  display: flex;
  align-items: center;
  padding: 8px 0;
  font-size: 12px;
  color: #888;
}

.scale-start,
.scale-end {
  flex-shrink: 0;
  width: 30px;
}

.scale-bar {
  flex: 1;
  position: relative;
  height: 20px;
  border-bottom: 1px solid #d9d9d9;
}

.scale-tick {
  position: absolute;
  bottom: 0;
  transform: translateX(-50%);
}

.tick-label {
  font-size: 11px;
  color: #888;
}

.no-segment {
  color: #ccc;
  font-size: 12px;
  padding: 4px 8px;
}
</style>
