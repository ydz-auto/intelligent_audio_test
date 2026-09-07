/**
 * TestCaseReportDetail —— 评分指标与对比表格子模块
 * 职责：评分指标展示形状（displayMetrics）、对比/单设备指标表格（列 + 数据）、
 * 设备名解析与指标格式化辅助（formatValue / calculateScore / formatMetricLabel）
 */
import { computed } from 'vue';
import type {
  DisplayMetric,
  ReportDetailColumn,
  TestCaseReportDetailProps,
} from './testCaseReportDetail.types';

/**
 * 评分指标与对比表格编排
 */
export function useTestCaseReportDetailMetrics(props: TestCaseReportDetailProps) {
  const resourceHeaderMap = computed(() => {
    const headers = Array.isArray(props.resourceHeaders) ? props.resourceHeaders : []
    const map: Record<string, string> = {}
    headers.forEach(h => {
      if (!h) return
      const key = h.key || h.resource
      const label = h.label || h.name || key
      if (key) map[String(key)] = String(label || key)
    })
    return map
  })

  const getDeviceName = (deviceId: string) => {
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
    const names = new Set<string>();
    Object.values(props.comparisonData).forEach(d => {
      if (d.metrics) Object.keys(d.metrics).forEach(m => names.add(m));
    });
    // 排序：按维度基础名分组，组内按轮次（round:N 升序）在前、整体（@overall）在后
    return Array.from(names).sort((a, b) => {
      const parseKey = (k: string) => {
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
  const formatMetricLabel = (key: string) => {
    const m = key.match(/^(.*)@round:(\d+)$/);
    if (m) return `${m[1]} (第${m[2]}轮)`;
    const m2 = key.match(/^(.*)@overall$/);
    if (m2) return `${m2[1]} (整体)`;
    return key;
  };

  // 指标小数位配置映射（Domain decimalPlaces 唯一契约）
  const metricDecimalPlacesMap = computed<Record<string, number>>(() => {
    const map: Record<string, number> = {};
    for (const cfg of props.metricConfigs || []) {
      if (cfg?.name) map[cfg.name] = cfg.decimalPlaces ?? 2;
    }
    return map;
  });

  // 指标单位配置映射
  const metricUnitMap = computed<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const cfg of props.metricConfigs || []) {
      if (cfg?.name && cfg.unit) map[cfg.name] = cfg.unit;
    }
    return map;
  });

  // 对比模式：按指标配置的小数位格式化数值并追加单位
  const formatMetricForDisplay = (metricName: string, value: number | string) => {
    if (value === '-' || value === null || value === undefined) return '-';
    const num = typeof value === 'number' ? value : Number(value);
    if (isNaN(num)) return String(value);
    // 从带轮次后缀的 key 中提取基础维度名（如 "WER@round:1" → "WER"）
    const baseName = String(metricName).replace(/@round:\d+$|@overall$/, '');
    const decimals = metricDecimalPlacesMap.value[baseName] ?? metricDecimalPlacesMap.value[String(metricName)] ?? 2;
    const unit = metricUnitMap.value[baseName] ?? metricUnitMap.value[String(metricName)] ?? '';
    return `${num.toFixed(decimals)}${unit ? ` ${unit}` : ''}`;
  };

  // 对比模式：取设备某指标的原始值（兼容 null 缺省）
  const getMetricRawValue = (device: string, metricName: string) => {
    return props.comparisonData?.[device]?.metrics?.[metricName];
  };

  // 对比模式：取设备某指标展示值（对象 { value } 形状取内层）
  const getMetricValue = (device: string, metricName: string): number | string => {
    const raw = getMetricRawValue(device, metricName);
    if (raw === null || raw === undefined) return '-';
    if (typeof raw === 'object') return raw.value;
    return raw;
  };

  // 对比模式：取设备某指标展示值（小数位/单位格式化后）
  const getMetricDisplayValue = (device: string, metricName: string): number | string =>
    formatMetricForDisplay(metricName, getMetricValue(device, metricName));

  const displayMetrics = computed<DisplayMetric[]>(() => {
    if (props.dimensions && props.dimensions.length > 0) {
      return props.dimensions.map(dim => ({
        id: dim.id,
        metric: dim.name ?? '',
        value: dim.value ?? '',
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

  const calculateScore = (value: number | string | null | undefined) => {
    if (value === null || value === undefined || value === '-') return 0;
    const num = Number(value);
    if (isNaN(num)) return 0;
    if (num <= 5) return 5;
    if (num <= 10) return 4;
    if (num <= 20) return 3;
    if (num <= 30) return 2;
    return 1;
  };

  const formatValue = (value: number | string | null | undefined) => {
    if (value === null || value === undefined || value === '-') return '-';
    const num = Number(value);
    if (isNaN(num)) return String(value);
    return num.toFixed(2);
  };

  // 是否有评分指标数据
  const hasMetrics = computed(() => {
    if (props.isComparison) {
      return allMetricNames.value.length > 0;
    }
    return (props.dimensions && props.dimensions.length > 0) ||
           (props.metrics && props.metrics.length > 0);
  });

  // 对比模式表格列：指标名 + 每设备一列
  const comparisonTableColumns = computed<ReportDetailColumn[]>(() => {
    const columns: ReportDetailColumn[] = [
      { key: 'metricName', label: '指标', resize: true, class: 'col-metric', color: '#1677ff' },
    ];
    for (const device of props.devices || []) {
      columns.push({
        key: device,
        label: getDeviceName(device),
        resize: true,
        class: 'col-device',
      });
    }
    return columns;
  });

  // 对比模式表格数据（行 = 指标，列 = 设备）
  const comparisonTableData = computed(() =>
    allMetricNames.value.map(metricName => {
      const row: Record<string, number | string> = { metricName: formatMetricLabel(metricName) };
      for (const device of props.devices || []) {
        row[device] = formatMetricForDisplay(metricName, getMetricValue(device, metricName));
      }
      return row;
    })
  );

  // 单设备模式：指标表格列
  const singleTableColumns = computed<ReportDetailColumn[]>(() => [
    { key: 'metric', label: '指标', resize: true, class: 'col-metric', color: '#1677ff' },
    { key: 'value', label: '数值', resize: true, class: 'col-value' },
    { key: 'score', label: '评分', resize: true, class: 'col-score' },
    { key: 'errorMessage', label: '错误信息', resize: true, class: 'col-error' },
  ]);

  // 单设备模式：指标表格数据
  const singleTableData = computed(() =>
    displayMetrics.value.map(m => ({
      metric: m.metric,
      rawValue: m.value ?? null,
      rawScore: m.score ?? null,
      rawErrorMessage: m.errorMessage ?? null,
    }))
  );

  return {
    hasMetrics,
    allMetricNames,
    displayMetrics,
    comparisonTableColumns,
    comparisonTableData,
    singleTableColumns,
    singleTableData,
    formatValue,
    calculateScore,
    getDeviceName,
    getMetricValue,
    getMetricDisplayValue,
  };
}