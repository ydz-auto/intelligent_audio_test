import { ref, computed, watch } from 'vue';
import { buildAudioUrl, normalizeAudioItem } from '../../../utils/audioUtils';
import reportService from '../../../services/reportService';

export function useTestCaseReportDetail(props) {
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
    // 支持的显示类型：文本、时间戳、数值、布尔、JSON、音频文件
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

  // 维度 tab 状态
  const activeDimTab = ref(0);

  watch(dimResultGroups, (newGroups) => {
    if (activeDimTab.value >= newGroups.length) {
      activeDimTab.value = 0;
    }
  }, { flush: 'post' });

  // 是否有结果音频
  const hasResultAudioData = computed(() => {
    return props.resultAudios && Object.keys(props.resultAudios).length > 0;
  });

  const audioListWithTimeline = computed(() => {
    const list = props.audioList || [];
    if (list.length === 0) return [];

    // 只做字段归一化，不再自行计算时间轴位置
    // 后端已根据 overlap_rate/overlap_time 计算好 timelineStart/timelineEnd
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

  return {
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
  };
}
