/**
 * audioUtils —— 标注文件解析
 *
 * 提供音频配套 txt 文件解析（parseAudioTxtFile）、标注类型判定（determineAnnotationType）
 * 与标注文件解析（parseAnnotationFormat，支持 JSON / JSONL / RTTM / STM 格式）。
 */
import { DEFAULT_CONFIDENCE } from './audioUtils.constants';

/**
 * 解析音频对应的txt文件，提取ASR文本和翻译信息
 * @param content - txt文件内容
 * @returns 包含asrText和translations的对象
 */
export const parseAudioTxtFile = (content: string): {asrText: string, translations: Array<{ text: string, direction: string}>} => {
  const result : {asrText: string, translations: Array<{ text: string, direction: string}>} = {asrText: '', translations: []};

  if (!content) return result;

  const lines = content.split(/\r?\n/).map(line => line.trim()).filter(line => line.length > 0);
  if (lines.length === 0) return result;

  result.asrText = lines[0];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    
    let parts = line.split('\t').map(p => p.trim());
    
    if (parts.length < 2) {
      const lastSpaceIndex = line.lastIndexOf(' ');
      if (lastSpaceIndex !== -1) {
        const text = line.substring(0, lastSpaceIndex).trim();
        const direction = line.substring(lastSpaceIndex + 1).trim();
        parts = [text, direction];
      }
    }

    if (parts.length >= 2) {
      const [text, direction] = parts;
      if (text && direction) {
        const normalizedDirection = direction.replace(/_/g, '-').replace(/\//g, '-').replace(/2/g, '-').toLowerCase();
        result.translations.push({
          text: text,
          direction: normalizedDirection
        });
      }
    }
  }

  return result;
};

/**
 * 根据标注名称确定标注类型
 * @param name - 标注名称
 * @returns 标注类型 (asr/translation/diarization)
 */
export const determineAnnotationType = (name: string): string => {
  const lowerName = name.toLowerCase()
  if (lowerName === 'asr' || lowerName === 'reference') {
    return 'asr'
  }
  if (lowerName === 'translation') {
    return 'translation'
  }
  if (lowerName === 'diarization' || lowerName === 'speaker') {
    return 'diarization'
  }
  return 'asr'
}

/**
 * 解析标注文件（JSON/RTTM/STM/JSONL格式）
 * @param content - 标注文件内容
 * @param format - 标注格式 (json/rttm/stm/jsonl)
 * @returns 解析后的标注对象
 */
// 已知的顶层字段名，不属于此集合的字段会被收入 extra_fields
const KNOWN_TOP_KEYS = new Set([
  'name', 'code', 'type', 'source_language', 'target_language',
  'text', 'txt', 'annotations', 'timestamps', 'timestamps_global',
]);
// 已知的 txt/segment 字段名
const KNOWN_SEG_KEYS = new Set([
  'speaker', 'start', 'end', 'text', 'confidence',
]);
// 已知的 annotation 子字段名
const KNOWN_ANN_KEYS = new Set([
  'name', 'code', 'type', 'source_language', 'target_language', 'text', 'txt',
]);

export const parseAnnotationFormat = (content: string, format: string): {
  format: string;
  filename: string;
  name: string;
  code: string;
  type: string;
  source_language: string;
  target_language: string;
  segments: Array<Record<string, any>>;
  timestamps: number[][];
  timestamps_global: number[][];
  raw_data: any;
  extra_fields: Record<string, any>;
  annotations: Array<{
    name?: string;
    code: string;
    type?: string;
    source_language: string;
    target_language: string;
    segments: Array<Record<string, any>>;
    extra_fields: Record<string, any>;
  }>;
} => {
  const result = {
    format: format,
    filename: '',
    name: '',
    code: '',
    type: '',
    source_language: '',
    target_language: '',
    segments: [] as Array<Record<string, any>>,
    timestamps: [] as number[][],
    timestamps_global: [] as number[][],
    raw_data: {} as any,
    extra_fields: {} as Record<string, any>,
    annotations: [] as Array<{ name?: string; code: string; type?: string; source_language: string; target_language: string; segments: Array<Record<string, any>>, extra_fields: Record<string, any> }>
  };

  const formatLower = format.toLowerCase();

  if (formatLower === 'json' || formatLower === 'jsonl') {
    try {
      let data;
      if (formatLower === 'jsonl') {
        const lines = content.trim().split('\n').filter(line => line.trim());
        const segments = [];
        for (const line of lines) {
          try {
            const obj = JSON.parse(line);
            segments.push(obj);
          } catch (e) {
            continue;
          }
        }
        data = { txt: segments };
      } else {
        data = JSON.parse(content);
      }
      
      result.raw_data = data;

      if (data.code) {
        result.code = data.code;
      }

      if (data.source_language) {
        result.source_language = data.source_language;
      }
      
      if (data.target_language) {
        result.target_language = data.target_language;
      }
      
      if (Array.isArray(data.txt) && data.txt.length > 0) {
        // {txt: [...]} 分支：多段标注
        const txtList = data.txt;
        for (const item of txtList) {
          if (item && typeof item === 'object') {
            // 收集 txt 项中的未知字段，平铺到 segment 中
            const segExtra: Record<string, any> = {};
            for (const k of Object.keys(item)) {
              if (!KNOWN_SEG_KEYS.has(k)) {
                segExtra[k] = item[k];
              }
            }
            result.segments.push({
              speaker: item.speaker || '',
              start: parseFloat(item.start) || 0,
              end: parseFloat(item.end) || 0,
              text: item.text || '',
              confidence: parseFloat(item.confidence) || 1.0,
              ...segExtra
            });
          }
        }
        // txt 模式下 data 只保留元数据 + segments
        data.txt = undefined;
        data.segments = result.segments;
      } else {
        // 平铺 JSON 分支：{query, text, correctAnswer, ...} → 包装成 segments，清除顶层业务字段
        const segExtra: Record<string, any> = {};
        for (const k of Object.keys(data)) {
          if (!KNOWN_SEG_KEYS.has(k) && !KNOWN_TOP_KEYS.has(k)) {
            segExtra[k] = data[k];
          }
        }
        result.segments.push({
          speaker: '',
          start: 0,
          end: 0,
          text: data.text || '',
          confidence: DEFAULT_CONFIDENCE,
          ...segExtra
        });
        // 清除 data 顶层的业务字段（已移入 segments），避免 data 与 segments 重复
        for (const k of Object.keys(data)) {
          if (!KNOWN_TOP_KEYS.has(k) && k !== 'segments') {
            delete data[k];
          }
        }
        data.segments = result.segments;
      }
      
      if (data.annotations && Array.isArray(data.annotations)) {
        for (const ann of data.annotations) {
          const annSegments = [];
          if (ann.text && typeof ann.text === 'string') {
            annSegments.push({
              speaker: '',
              start: 0,
              end: 0,
              text: ann.text,
              confidence: DEFAULT_CONFIDENCE
            });
          } else if (ann.txt && Array.isArray(ann.txt)) {
            for (const item of ann.txt) {
              if (item && typeof item === 'object' && (item.speaker || item.text || item.start !== undefined)) {
                // 收集 annotation txt 项中的未知字段，平铺到 segment 中
                const segExtra: Record<string, any> = {};
                for (const k of Object.keys(item)) {
                  if (!KNOWN_SEG_KEYS.has(k)) {
                    segExtra[k] = item[k];
                  }
                }
                annSegments.push({
                  speaker: item.speaker || '',
                  start: parseFloat(item.start) || 0,
                  end: parseFloat(item.end) || 0,
                  text: item.text || '',
                  confidence: parseFloat(item.confidence) || 1.0,
                  ...segExtra
                });
              }
            }
          }
          if (annSegments.length > 0) {
            // 收集 annotation 中的未知字段（排除已处理的 txt/text）
            const annExtra: Record<string, any> = {};
            for (const k of Object.keys(ann)) {
              if (!KNOWN_ANN_KEYS.has(k)) {
                annExtra[k] = ann[k];
              }
            }
            result.annotations.push({
              code: ann.code || 'asr',
              source_language: (ann as any).source_language || '',
              target_language: (ann as any).target_language || '',
              segments: annSegments,
              extra_fields: annExtra
            });
          }
        }
      }
      
      if (data.timestamps) {
        result.timestamps = data.timestamps;
      }
      if (data.timestamps_global) {
        result.timestamps_global = data.timestamps_global;
      }

      // 收集顶层未知字段
      for (const k of Object.keys(data)) {
        if (!KNOWN_TOP_KEYS.has(k)) {
          result.extra_fields[k] = data[k];
        }
      }
    } catch (e) {
      console.error('JSON/JSONL parse error:', e);
    }
  } else if (formatLower === 'rttm' || formatLower === 'stm') {
    const lines = content.trim().split('\n');
    const segments = [];
    for (const line of lines) {
      const parts = line.trim().split(/\s+/);
      if (formatLower === 'rttm' && parts[0] === 'SPEAKER' && parts.length >= 8) {
        segments.push({
          speaker: parts[7] || '',
          start: parseFloat(parts[3]) || 0,
          end: (parseFloat(parts[3]) || 0) + (parseFloat(parts[4]) || 0),
          text: '',
          confidence: DEFAULT_CONFIDENCE
        });
      } else if (formatLower === 'stm' && parts.length >= 6) {
        segments.push({
          speaker: parts[1] || '',
          start: parseFloat(parts[2]) || 0,
          end: parseFloat(parts[3]) || 0,
          text: parts.slice(5).join(' ') || '',
          confidence: DEFAULT_CONFIDENCE
        });
      }
    }
    result.segments = segments;
    result.name = 'diarization';
    result.code = 'diarization';
    result.type = 'diarization';
  }

  return result;
};