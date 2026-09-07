/**
 * TestCaseReportDetail —— 动态文本字段子模块
 * 职责：从 referenceParams / algorithmResults / fieldMapping 提取参考文本与结果文本字段，
 * 并按维度分组（dimResultGroups / generalResultGroup）
 * 数据契约：camelCase ReadModel（经 Infrastructure adapter 归一化），直读即可；
 * referenceParams 字典键与 paramCode 值为后端数据 key，原样保留
 */
import { computed } from 'vue';
import type {
  AlgorithmResultItem,
  FieldMappingItem,
  ReferenceTextField,
  ResultFieldGroup,
  ResultTextField,
  TestCaseReportDetailProps,
} from './testCaseReportDetail.types';
import { FieldType } from '../../../domain/enums';

/**
 * 动态文本字段编排
 */

// 从结果/参考字段的 paramCode 或 roundNumber 提取轮次标记
// paramCode 形如 "answer@round:1" → 'round:1'；roundNumber 为数字(1-indexed) → 'round:N'；无 → null
export const parseFieldRoundTag = (field: { paramCode?: string; roundNumber?: number | null }) => {
  if (field.paramCode) {
    const m = field.paramCode.match(/@round:(\d+)$/);
    if (m) return `round:${m[1]}`;
  }
  const rn = field.roundNumber;
  if (rn !== null && rn !== undefined && !isNaN(Number(rn))) {
    return `round:${Number(rn)}`;
  }
  return null;
};

export function useTestCaseReportDetailTextFields(props: TestCaseReportDetailProps) {
  // 参考文本取值：referenceParams 字典（text/value 优先）+ 兜底空串
  const getReferenceTextValue = (paramCode: string) => {
    const item = props.referenceParams?.[paramCode];
    if (!item) return '';
    const text = item.text ?? item.value ?? '';
    if (typeof text === 'string') return text;
    if (typeof text === 'number' || typeof text === 'boolean') return String(text);
    return '';
  };

  // 结果文本取值：从 algorithmResults 中取设备某参数的值（text/timestamp/number/boolean/json/audio_file）
  const getResultTextValue = (device: string, paramCode: string) => {
    // 设备归属：无 device 字段的数据对所有设备可见；'default' 视图（单设备模式）纳入全部设备数据
    const pool = (props.algorithmResults || []).filter(i => {
      const d = i.device;
      if (d === null || d === undefined || d === '') return true;
      return String(device) === 'default' || String(d) === String(device);
    });
    const formatItemValue = (i: AlgorithmResultItem): string => {
      const v = i.value;
      if (typeof v === 'string') return v.trim();
      if (typeof v === 'number' || typeof v === 'boolean') return String(v);
      if (v && typeof v === 'object') return JSON.stringify(v);
      return '';
    };

    // 1. 精确匹配
    const exact = pool.find(i => i.paramCode === paramCode);
    if (exact) return formatItemValue(exact);

    // 2. @round:N 展开码 → 按 base 参数 + roundNumber 匹配
    const roundMatch = paramCode.match(/^(.*)@round:(\d+)$/);
    if (roundMatch) {
      const roundNum = Number(roundMatch[2]);
      const byRound = pool.find(i => i.paramCode === roundMatch[1] && Number(i.roundNumber) === roundNum);
      if (byRound) return formatItemValue(byRound);
    }

    // 3. 兜底：去掉 @round:N 后缀后取首条
    const fallbackBase = roundMatch ? roundMatch[1] : paramCode;
    const fallback = pool.find(i => i.paramCode === fallbackBase);
    if (fallback) return formatItemValue(fallback);

    return '-';
  };

  // 动态参考文本字段
  const referenceTextFields = computed<ReferenceTextField[]>(() => {
    const refParams = props.referenceParams || {};
    const result: ReferenceTextField[] = [];
    const seenCodes = new Set<string>();

    // 1. 从 referenceParams 字典里直接提取所有 text 参数（含多轮展开的 code@round:N）
    //    字典键为参数 code 数据 key（原样保留），条目字段为 camelCase
    for (const [code, data] of Object.entries(refParams)) {
      if (!data || typeof data !== 'object') continue;
      if (data.type !== 'text') continue;
      const text = data.text || data.value || '';
      if (typeof text !== 'string' || !text.trim()) continue;
      seenCodes.add(code);
      result.push({
        paramCode: code,
        label: String(data.label || (code.includes('@round:') ? `${code.split('@round:')[0]} (第${code.split('@round:')[1]}轮)` : code)),
        paramType: FieldType.TEXT,
        roundNumber: typeof data.roundNumber === 'number' ? data.roundNumber : undefined,
        text,
      });
    }

    // 2. 补充 fieldMapping 里定义但 referenceParams 未覆盖的 text 字段
    const refFields = (props.fieldMapping?.reference || [])
      .filter((f): f is FieldMappingItem & { paramCode: string } =>
        (f.paramType ?? FieldType.TEXT) === FieldType.TEXT
        && typeof f.paramCode === 'string' && f.paramCode !== '');
    for (const field of refFields) {
      if (!seenCodes.has(field.paramCode)) {
        const text = getReferenceTextValue(field.paramCode);
        if (text && text.trim() && text !== '无数据') {
          seenCodes.add(field.paramCode);
          result.push({
            ...field,
            text,
            label: field.label || field.paramCode,
            paramType: field.paramType ?? FieldType.TEXT,
            roundNumber: field.roundNumber ?? undefined,
          });
        }
      }
    }

    // 按轮次排序
    result.sort((a, b) => {
      const ra = a.roundNumber ?? 0;
      const rb = b.roundNumber ?? 0;
      if (ra !== rb) return ra - rb;
      return (a.paramCode || '').localeCompare(b.paramCode || '');
    });
    return result;
  });

  // 动态结果文本字段
  const resultTextFields = computed<ResultTextField[]>(() => {
    const algoResults = props.algorithmResults || [];

    // 1. 从 algorithmResults 中提取所有 text 类型项（包含 question@round / answer@round）
    // 排除元数据字段（非用户关心的结果内容）
    // META_CODES 持有 paramCode 数据 key 的集合；值原样保留，不做键名归一化
    const META_CODES = new Set([
      'testType',
      'algorithmType',
      'totalRounds',
      'aggregated',
      'multiRound',
      'sessionId',
      'contextMode',
      'error',
    ]);
    // 支持的显示类型：文本、时间戳、数值、布尔、JSON、音频文件
    const DISPLAY_TYPES = new Set<string>([FieldType.TEXT, FieldType.TIMESTAMP, FieldType.NUMBER, FieldType.BOOLEAN, FieldType.JSON, FieldType.AUDIO_FILE]);
    const textItems: ResultTextField[] = [];
    const seenCodes = new Set<string>();
    for (const item of algoResults) {
      const code = item.paramCode;
      if (DISPLAY_TYPES.has(item.paramType) && code && !META_CODES.has(code) && !code.startsWith('rounds') && !seenCodes.has(code)) {
        seenCodes.add(code);
        textItems.push({
          paramCode: code,
          label: item.label || code,
          paramType: item.paramType,
          roundNumber: item.roundNumber,
          dimensionName: item.dimensionName,
          getValue: (device: string) => getResultTextValue(device, code)
        });
      }
    }

    // 2. 补充 fieldMapping 里定义的 text/timestamp/number 字段（跳过 algorithmResults 已覆盖的）
    //    仅补充 algorithmResults 中有对应值的字段，避免显示"无数据"
    const fmFields = (props.fieldMapping?.result || [])
      .filter((f): f is FieldMappingItem & { paramCode: string } =>
        DISPLAY_TYPES.has(f.paramType ?? FieldType.TEXT)
        && typeof f.paramCode === 'string' && f.paramCode !== ''
        && !META_CODES.has(f.paramCode) && !f.paramCode.startsWith('rounds'));
    const allResultCodes = new Set(algoResults.map(i => i.paramCode));
    for (const f of fmFields) {
      if (!seenCodes.has(f.paramCode) && allResultCodes.has(f.paramCode)) {
        seenCodes.add(f.paramCode);
        textItems.push({
          ...f,
          paramType: f.paramType ?? FieldType.TEXT,
          roundNumber: f.roundNumber ?? undefined,
          label: f.label || f.paramCode,
          getValue: (device: string) => getResultTextValue(device, f.paramCode)
        });
      }
    }

    // 按轮次排序，question 在前 answer 在后
    textItems.sort((a, b) => {
      const ra = a.roundNumber ?? 0;
      const rb = b.roundNumber ?? 0;
      if (ra !== rb) return ra - rb;
      return (a.paramCode || '').localeCompare(b.paramCode || '');
    });
    return textItems;
  });

  // 子维度名 → 父维度名映射（从 comparisonData 指标归组信息提取）
  const subDimToParent = computed<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    Object.values(props.comparisonData || {}).forEach(d => {
      if (!d?.metrics) return;
      Object.entries(d.metrics).forEach(([key, info]) => {
        // 指标条目对象形态持有维度归组信息（前端视图模型 camelCase）
        if (info && typeof info === 'object'
          && info.dimensionType === 'sub'
          && info.parentDimensionName) {
          map[key] = String(info.parentDimensionName);
        }
      });
    });
    return map;
  });

  // 按维度分组结果文本字段（子维度归入父维度组）
  const groupFieldsByDimension = (
    fields: ResultTextField[],
    subDimParentMap: Record<string, string>
  ): ResultFieldGroup[] => {
    const groups = new Map<string | null, ResultTextField[]>();
    const order: (string | null)[] = [];

    for (const field of fields) {
      let dimName = field.dimensionName || null;
      // 子维度归入父维度组
      if (dimName && subDimParentMap[dimName]) {
        dimName = subDimParentMap[dimName];
      }
      const existing = groups.get(dimName);
      if (existing) {
        existing.push(field);
      } else {
        groups.set(dimName, [field]);
        order.push(dimName);
      }
    }

    // 通用分组（dimensionName 为 null 的）放最后
    const result: ResultFieldGroup[] = [];
    for (const key of order) {
      if (key !== null) {
        result.push({
          key: key,
          label: key,
          fields: groups.get(key)!
        });
      }
    }
    const generalFields = groups.get(null);
    if (generalFields) {
      result.push({
        key: '_general',
        label: '其他结果',
        fields: generalFields
      });
    }
    return result;
  };

  // 按维度分组结果文本字段
  const groupedResultTextFields = computed<ResultFieldGroup[]>(() => {
    return groupFieldsByDimension(resultTextFields.value, subDimToParent.value);
  });

  // 有维度归属的结果分组（维度评估结果）
  const dimResultGroups = computed(() => {
    return groupedResultTextFields.value.filter(g => g.key !== '_general');
  });

  // 无维度归属的结果分组（设备/API 执行结果）
  const generalResultGroup = computed<ResultFieldGroup>(() => {
    const found = groupedResultTextFields.value.find(g => g.key === '_general');
    return found || { key: '_general', label: '设备/API 执行结果', fields: [] };
  });

  return {
    referenceTextFields,
    resultTextFields,
    subDimToParent,
    groupFieldsByDimension,
    groupedResultTextFields,
    dimResultGroups,
    generalResultGroup,
  };
}
