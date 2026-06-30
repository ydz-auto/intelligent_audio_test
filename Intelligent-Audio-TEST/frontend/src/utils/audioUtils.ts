/**
 * 共享音频工具函数
 */

export const DB_MIN = -60;
export const DB_MAX = 0;

export function volumeToDb(volume: number, minDb: number = DB_MIN, maxDb: number = DB_MAX): number {
  if (volume < 0 || volume > 100) {
    console.warn(`[volumeToDb] 音量值 ${volume} 超出 0-100 范围，已裁剪`);
  }
  const clampedVolume = Math.max(0, Math.min(100, volume));
  return minDb + (clampedVolume / 100) * (maxDb - minDb);
}

export function dbToLinear(db: number): number {
  return Math.pow(10, db / 20);
}

export function volumeToLinear(volume: number, minDb: number = DB_MIN, maxDb: number = DB_MAX): number {
  const targetDb = volumeToDb(volume, minDb, maxDb);
  return dbToLinear(targetDb);
}

export function linearToDb(linear: number): number {
  if (linear <= 0) return -Infinity;
  return 20 * Math.log10(linear);
}

export function dbToVolume(db: number, minDb: number = DB_MIN, maxDb: number = DB_MAX): number {
  const clampedDb = Math.max(minDb, Math.min(maxDb, db));
  return ((clampedDb - minDb) / (maxDb - minDb)) * 100;
}

export interface GainCurvePoint {
  volume: number;
  db: number;
  linear: number;
}

export function generateGainCurve(
  minDb: number = DB_MIN,
  maxDb: number = DB_MAX,
  steps: number = 101
): GainCurvePoint[] {
  const curve: GainCurvePoint[] = [];
  for (let i = 0; i < steps; i++) {
    const volume = (i / (steps - 1)) * 100;
    const db = volumeToDb(volume, minDb, maxDb);
    const linear = dbToLinear(db);
    curve.push({ volume, db, linear });
  }
  return curve;
}

/**
 * 格式化文件大小
 * @param size - 文件大小（字节）
 * @returns 格式化后的文件大小
 */
export const formatFileSize = (size: number | string): string => {
  if (typeof size === 'string') {
    return size;
  }
  
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let currentSize = parseInt(size as unknown as string) || 0;
  let unitIndex = 0;
  
  while (currentSize >= 1024 && unitIndex < units.length - 1) {
    currentSize /= 1024;
    unitIndex++;
  }
  
  return `${currentSize.toFixed(2)} ${units[unitIndex]}`;
};

/**
 * 格式化音频时长
 * @param seconds - 音频时长（秒）
 * @returns 格式化后的时长（分:秒）
 */
export const formatDuration = (seconds: number | null | undefined): string => {
  if (!seconds) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

/**
 * 解析格式化时长字符串为秒数
 * @param durationStr - 格式化时长字符串（如 "1:30", "12:34"）或数字
 * @returns 总秒数
 */
export const parseDuration = (durationStr: string | number | null | undefined): number => {
  if (!durationStr) return 0;
  if (typeof durationStr === 'number') return durationStr;
  const str = String(durationStr).trim();
  if (!str) return 0;
  if (str.includes(':')) {
    const parts = str.split(':').map(p => parseInt(p, 10) || 0);
    if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    } else if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
  }
  const parsed = parseFloat(str);
  return isNaN(parsed) ? 0 : parsed;
};

/**
 * 格式化时长（长格式，含天时分秒）
 * @param seconds - 音频时长（秒）
 * @returns 格式化后的时长（D天H时M分S秒）
 */
export const formatDurationLong = (seconds: number | null | undefined): string => {
  if (!seconds) return '0秒';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const parts: string[] = [];
  if (days > 0) parts.push(`${days}天`);
  if (hours > 0) parts.push(`${hours}时`);
  if (mins > 0) parts.push(`${mins}分`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs}秒`);
  return parts.join('');
};

export interface AudioData {
  id: string | number;
  filename: string;
  path: string;
  format: string;
  size: string;
  duration: string;
  type: string;
  status: string;
  tags: string[];
}

/**
 * 格式化音频数据
 * @param audio - 原始音频数据
 * @returns 格式化后的音频数据
 */
export const formatAudioData = (audio: any): AudioData => {
  const filepath = audio.path || audio.filePath || audio.filepath || audio.file_path || '';
  return {
    id: audio.id,
    filename: audio.filename || audio.name || audio.originalFilename,
    filepath: filepath,
    path: filepath,
    format: audio.format || 'unknown',
    size: formatFileSize(audio.size),
    duration: formatDuration(audio.duration),
    type: audio.type || audio.audioType || 'dry',
    status: audio.status || 'active',
    tags: audio.tags || []
  };
};

export interface FolderNode {
  name: string;
  files: any[];
  folders: FolderNode[];
}

/**
 * 构建文件夹树结构
 * @param audios - 音频文件列表
 * @returns 文件夹树结构
 */
export const buildFolderTree = (audios: any[]): FolderNode => {
  const root : FolderNode = {name: '音频文件', files: [], folders: []};

  audios.forEach(audio => {
    const filePath = audio.filepath || audio.path || audio.filePath || audio.file_path;
    if (!filePath) {
      root.files.push(audio);
      return;
    }

    let pathParts = filePath.split('/').filter((part: string) => part);
    if (pathParts.length === 0) {
      root.files.push(audio);
      return;
    }

    // 跳过第一层目录（如 'audios'）
    if (pathParts.length > 1 && (pathParts[0] === 'audios' || pathParts[0] === 'audio')) {
      pathParts = pathParts.slice(1);
    }

    // 如果去掉第一层后只剩文件名，则放到根目录
    if (pathParts.length <= 1) {
      root.files.push(audio);
      return;
    }

    let currentFolder = root;
    for (let i = 0; i < pathParts.length - 1; i++) {
      const folderName = pathParts[i];
      let folder = currentFolder.folders.find(f => f.name === folderName);
      if (!folder) {
        folder = {name: folderName, files: [], folders: []};
        currentFolder.folders.push(folder);
      }
      currentFolder = folder;
    }
    currentFolder.files.push(audio);
  });

  return root;
};

/**
 * 提取所有不重复的标签
 * @param audios - 音频列表
 * @returns 标签数组
 */
export const extractAllTags = (audios: any[]): string[] => {
  const tagsSet = new Set<string>();
  audios.forEach(audio => {
    if (audio.tags && Array.isArray(audio.tags)) {
      audio.tags.forEach((tag: string) => tagsSet.add(tag));
    }
  });
  return Array.from(tagsSet);
};

/**
 * 切换文件夹展开状态
 * @param folder - 文件夹节点
 * @param expandedFolders - 展开文件夹集合
 */
export const toggleFolder = (folder: FolderNode, expandedFolders: Set<string>): void => {
  if (expandedFolders.has(folder.name)) {
    expandedFolders.delete(folder.name);
  } else {
    expandedFolders.add(folder.name);
  }
};

/**
 * 检查文件夹是否展开
 * @param folder - 文件夹节点
 * @param expandedFolders - 展开文件夹集合
 * @returns 是否展开
 */
export const isFolderOpen = (folder: FolderNode, expandedFolders: Set<string>): boolean => {
  return expandedFolders.has(folder.name);
};

/**
 * 筛选音频文件
 * @param audios - 音频列表
 * @param query - 搜索关键词
 * @param filters - 筛选条件
 * @param selectedTags - 选中的标签
 * @returns 筛选后的音频列表
 */
export const filterAudios = (
  audios: any[],
  query: string,
  filters: any,
  selectedTags: string[]
): any[] => {
  return audios.filter(audio => {
    const matchesSearch = !query || 
      (audio.filename && audio.filename.toLowerCase().includes(query.toLowerCase())) ||
      (audio.name && audio.name.toLowerCase().includes(query.toLowerCase()));
    
    if (!matchesSearch) return false;

    if (filters.audioType !== 'all' && audio.type !== filters.audioType) {
      return false;
    }

    if (selectedTags.length > 0) {
      // 处理标签过滤 - 支持数组类型和字符串类型的 tags
      let audioTags = [];
      if (Array.isArray(audio.tags)) {
        audioTags = audio.tags;
      } else if (typeof audio.tags === 'string') {
        audioTags = audio.tags.split(',').map((tag: string) => tag.trim());
      }
      
      // 使用 some 方法，只要音频包含至少一个选中的标签就匹配
      const hasMatchingTag = selectedTags.some(tag => audioTags.includes(tag));
      if (!hasMatchingTag) return false;
    }

    if (filters.duration !== 'all') {
      const duration = parseFloat(audio.duration) || 0;
      if (filters.duration === 'short' && duration > 30) return false;
      if (filters.duration === 'medium' && (duration <= 30 || duration > 300)) return false;
      if (filters.duration === 'long' && duration <= 300) return false;
    }

    if (filters.format !== 'all' && audio.format !== filters.format) {
      return false;
    }

    return true;
  });
};

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
    name: string;
    code: string;
    type: string;
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
    annotations: [] as Array<{ name: string; code: string; type: string; source_language: string; target_language: string; segments: Array<Record<string, any>>, extra_fields: Record<string, any> }>
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
      
      if (data.name) {
        result.name = data.name;
      }
      
      if (data.code) {
        result.code = data.code;
      }
      
      if (data.type) {
        result.type = data.type;
      }
      
      if (data.source_language) {
        result.source_language = data.source_language;
      }
      
      if (data.target_language) {
        result.target_language = data.target_language;
      }
      
      if (data.text && typeof data.text === 'string') {
        result.segments.push({
          speaker: '',
          start: 0,
          end: 0,
          text: data.text,
          confidence: 1.0
        });
      } else {
        const txtList = data.txt || [];
        for (const item of txtList) {
          if (item && typeof item === 'object' && (item.speaker || item.text || item.start !== undefined)) {
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
              confidence: 1.0
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
            const annName = ann.name || ann.code || 'asr'
            const annType = ann.type || determineAnnotationType(annName)
            // 收集 annotation 中的未知字段（排除已处理的 txt/text）
            const annExtra: Record<string, any> = {};
            for (const k of Object.keys(ann)) {
              if (!KNOWN_ANN_KEYS.has(k)) {
                annExtra[k] = ann[k];
              }
            }
            result.annotations.push({
              name: annName,
              code: ann.code || ann.name || 'asr',
              type: annType,
              source_language: ann.source_language || '',
              target_language: ann.target_language || '',
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
          confidence: 1.0
        });
      } else if (formatLower === 'stm' && parts.length >= 6) {
        segments.push({
          speaker: parts[1] || '',
          start: parseFloat(parts[2]) || 0,
          end: parseFloat(parts[3]) || 0,
          text: parts.slice(5).join(' ') || '',
          confidence: 1.0
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
