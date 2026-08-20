import type { TestCaseFormData } from '../shared/types';

/**
 * AlgorithmSelector 会把 schema 定义（caseAlgorithmParams / algorithmFormSchema）塞进 params 对象，
 * 这些不是参数值，传给后端会产生垃圾数据。此函数把 params 归一化为 [{field_code, field_value}] 并剔除 schema。
 * 接受对象、数组两种输入，返回数组。
 */
export function stripAlgorithmParamSchema(params: any): any[] {
  if (!params) return [];
  const SCHEMA_KEYS = new Set(['caseAlgorithmParams', 'algorithmFormSchema']);
  if (Array.isArray(params)) {
    return params
      .filter((p: any) => !SCHEMA_KEYS.has(p.field_code ?? p.fieldCode))
      .map((p: any) => ({
        field_code: p.field_code ?? p.fieldCode,
        field_value: p.field_value ?? p.fieldValue
      }))
      .filter((p: any) => p.field_code);
  }
  if (typeof params === 'object') {
    return Object.entries(params)
      .filter(([k]) => !SCHEMA_KEYS.has(k))
      .map(([fieldCode, fieldValue]) => ({ field_code: fieldCode, field_value: fieldValue }));
  }
  return [];
}

export function formatDate(date: string | Date | null | undefined, format: string = 'YYYY-MM-DD HH:mm:ss'): string {
  if (!date) return '';
  
  const d = new Date(date);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  const seconds = String(d.getSeconds()).padStart(2, '0');
  
  return format
    .replace('YYYY', String(year))
    .replace('MM', month)
    .replace('DD', day)
    .replace('HH', hours)
    .replace('mm', minutes)
    .replace('ss', seconds);
}

export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

export function debounce<T extends (...args: any[]) => any>(func: T, wait: number): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  return function executed_function(...args: Parameters<T>) {
    const later = () => {
      if (timeout) clearTimeout(timeout);
      func(...args);
    };
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

export function throttle<T extends (...args: any[]) => any>(func: T, limit: number): (...args: Parameters<T>) => void {
  let inThrottle: boolean = false;
  return function(this: any, ...args: Parameters<T>) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    if (!ok) throw new Error('execCommand copy failed');
    return true;
  } catch (err) {
    console.error('复制到剪贴板失败:', err);
    return false;
  }
}

export function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj;
  if (obj instanceof Date) return new Date(obj.getTime()) as unknown as T;
  if (Array.isArray(obj)) return obj.map(item => deepClone(item)) as unknown as T;
  
  const clonedObj = {} as any;
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      clonedObj[key] = deepClone((obj as any)[key]);
    }
  }
  return clonedObj as T;
}

export function getRandomColor(): string {
  const letters = '0123456789ABCDEF';
  let color = '#';
  for (let i = 0; i < 6; i++) {
    color += letters[Math.floor(Math.random() * 16)];
  }
  return color;
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function getFileExtension(filename: string): string {
  return filename.slice((filename.lastIndexOf('.') - 1 >>> 0) + 2);
}

export function getDaysBetween(date1: string | Date, date2: string | Date): number {
  const d1 = new Date(date1);
  const d2 = new Date(date2);
  const timeDiff = Math.abs(d2.getTime() - d1.getTime());
  return Math.ceil(timeDiff / (1000 * 3600 * 24));
}

export interface FormField {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  placeholder?: string;
  options?: Array<{ value: any; label: string; disabled?: boolean }>;
  defaultValue?: any;
  hint?: string;
  action?: string;
  text?: string;
  icon?: string;
  min?: number;
  max?: number;
  conditional?: {field: string; value: any};
  arrayItemType?: string;
  arrayItemTemplate?: any;
  disabled?: boolean;
}

/**
 * 归一化背景噪声配置，兼容多种存储格式：
 * - 标准 ID 格式：{audio_id, spl, device_ids, loop}
 * - 统一标注文件格式：{audio:"文件名.wav", spl, playback_device_names:["设备名1","设备名2"]}
 * - 旧单设备格式：{audio:"文件名.wav", spl, playback_device_name:"设备名"}
 * 输出统一为 {audioId, audioName, spl, deviceIds, deviceNames, loop, audio(文件名)}
 */
export function normalizeBackgroundNoise(bg: any) {
  if (!bg || typeof bg !== 'object') return undefined;
  const audioId = bg.audioId ?? bg.audio_id ?? '';
  const audioName = bg.audioName ?? bg.audio_name ?? '';
  const audioFile = typeof bg.audio === 'string' ? bg.audio : '';
  // 设备 ID 列表：优先 device_ids，其次从设备名反查（由调用方注入 devNameToId）
  const deviceIds: string[] = Array.isArray(bg.deviceIds)
    ? bg.deviceIds.map(String)
    : (Array.isArray(bg.device_ids) ? bg.device_ids.map(String) : []);
  // 设备名列表（统一标注文件格式）
  let deviceNames: string[] = [];
  if (Array.isArray(bg.playback_device_names)) {
    deviceNames = bg.playback_device_names;
  } else if (Array.isArray(bg.playbackDeviceNames)) {
    deviceNames = bg.playbackDeviceNames;
  } else if (Array.isArray(bg.device_names)) {
    deviceNames = bg.device_names;
  } else if (bg.playback_device_name || bg.playbackDeviceName) {
    deviceNames = [bg.playback_device_name ?? bg.playbackDeviceName];
  }
  return {
    audioId: String(audioId || ''),
    audioName: String(audioName || audioFile || ''),
    audio: audioFile, // 保留文件名（用于运行时解析或 UI 显示兜底）
    spl: bg.spl ?? null,
    deviceIds,
    deviceNames, // 保留设备名（用于 UI 显示兜底 / 反查 ID）
    loop: bg.loop ?? false,
  };
}

export function normalizeTestCaseConfig(config: Record<string, any>) {
  const rawConfig = config || {};

  // ---- rounds-based format (new architecture) ----
  if (rawConfig.rounds && Array.isArray(rawConfig.rounds)) {
    // case 级背景噪声（rounds 外层），优先级高于轮次级
    const caseBgNoise = rawConfig.backgroundNoise ?? rawConfig.background_noise;

    const normalizedRounds = rawConfig.rounds.map((round: any) => {
      // 轮次级背景噪声：case 级存在时直接用 case 级（轮次级不播放）
      const roundBgSrc = caseBgNoise ?? round.backgroundNoise ?? round.background_noise;
      // 归一化背景噪声：兼容 audio(文件名) / playback_device_names(设备名数组) / playback_device_name(单个)
      const bgNormalized = roundBgSrc ? normalizeBackgroundNoise(roundBgSrc) : undefined;

      return {
        roundNumber: round.roundNumber ?? round.round_number ?? 1,
        audios: Array.isArray(round.audios)
          ? round.audios.map((audio: any) => {
              const item: any = {
                audioId: audio?.audioId ?? audio?.audio_id ?? '',
                playbackDeviceId: audio?.playbackDeviceId ?? audio?.playback_device_id ?? '',
                spl: audio?.spl ?? 65,
                playOrder: audio?.playOrder ?? audio?.play_order ?? 0,
              };
              // 保留 segment 级背景噪声（归一化后）
              const segBg = audio?.backgroundNoise ?? audio?.background_noise;
              if (segBg) {
                item.backgroundNoise = normalizeBackgroundNoise(segBg);
              }
              // 保留 segment 级干扰人原值（交由 InterfererConfigEditor 兼容）
              if (Array.isArray(audio?.interferers) && audio.interferers.length > 0) {
                item.interferers = audio.interferers;
              }
              return item;
            })
          : [],
        backgroundNoise: bgNormalized,
        evaluation: round.evaluation ?? undefined,
        algorithmParams: Array.isArray(round.algorithmParams ?? round.algorithm_params)
          ? (round.algorithmParams ?? round.algorithm_params).map((p: any) => ({
              field_code: p.field_code ?? p.fieldCode ?? '',
              field_value: p.field_value ?? p.fieldValue ?? null,
            }))
          : [],
        referenceParamsPath: round.referenceParamsPath ?? round.reference_params_path ?? '',
      };
    });

    const rawDimensions = rawConfig.dimensions;
    const normalizedDimensions = Array.isArray(rawDimensions)
      ? rawDimensions
      : (rawDimensions?.dimensions ?? []);

    const result: Record<string, any> = {
      rounds: normalizedRounds,
      dimensions: normalizedDimensions || [],
      // case 级背景噪声也写入顶层（供 syncStructuredFields / 后端保存时使用）
      background_noise: caseBgNoise,
    };
    // 透传顶层非结构化字段（record_mode / voiceprint_config 等）
    for (const [k, v] of Object.entries(rawConfig)) {
      if (!(k in result) && k !== 'rounds' && k !== 'dimensions' && k !== 'audios' && k !== 'backgroundNoise' && k !== 'background_noise') {
        result[k] = v;
      }
    }
    return result;
  }

  // ---- legacy flat format fallback (audios + backgroundNoise) ----
  const rawBackgroundNoise =
    rawConfig.backgroundNoise ??
    (rawConfig.background_noise ? normalizeBackgroundNoise(rawConfig.background_noise) : undefined);

  const rawAudios: any[] = Array.isArray(rawConfig.audios) ? rawConfig.audios : [];
  const normalizedAudios = rawAudios.map((audio) => ({
    audioId: audio?.audioId ?? audio?.audio_id ?? '',
    playbackDeviceId: audio?.playbackDeviceId ?? audio?.playback_device_id ?? null,
    spl: audio?.spl ?? 65,
    playOrder: audio?.playOrder ?? audio?.play_order ?? 0,
  }));

  // Convert legacy flat audios into rounds grouped by testType
  const apiAudios = normalizedAudios.filter((a: any) => (a.testType ?? a.test_type ?? 'api') === 'api');
  const e2eAudios = normalizedAudios.filter((a: any) => (a.testType ?? a.test_type) === 'e2e');
  const legacyRounds: any[] = [];
  if (apiAudios.length > 0) {
    legacyRounds.push({
      roundNumber: 1,
      audios: apiAudios.map((a, i) => ({ ...a, playOrder: i })),
    });
  }
  if (e2eAudios.length > 0) {
    legacyRounds.push({
      roundNumber: legacyRounds.length + 1,
      audios: e2eAudios.map((a, i) => ({ ...a, playOrder: i })),
      backgroundNoise: rawBackgroundNoise
        ? {
            audioId: rawBackgroundNoise.audioId ?? null,
            spl: rawBackgroundNoise.spl ?? null,
            deviceIds: rawBackgroundNoise.deviceIds ?? [],
            loop: false,
          }
        : undefined,
    });
  }
  if (legacyRounds.length === 0) {
    legacyRounds.push({ roundNumber: 1, audios: [] });
  }

  const rawDimensions = rawConfig.dimensions;
  const normalizedDimensions = Array.isArray(rawDimensions)
    ? rawDimensions
    : (rawDimensions?.dimensions ?? []);

  return {
    rounds: legacyRounds,
    dimensions: normalizedDimensions || [],
  };
}

export function convertToSnakeCase<T extends Record<string, any>>(data: T): Record<string, any> {
  if (Array.isArray(data)) {
    return data.map(item => convertToSnakeCase(item));
  } else if (data !== null && typeof data === 'object') {
    const result: Record<string, any> = {};
    for (const [key, value] of Object.entries(data)) {
      const snakeKey = key.replace(/([A-Z])/g, '_$1').toLowerCase();
      result[snakeKey] = convertToSnakeCase(value);
    }
    return result;
  }
  return data;
}

export function convertToCamelCase<T extends Record<string, any>>(data: T): Record<string, any> {
  if (Array.isArray(data)) {
    return data.map(item => convertToCamelCase(item));
  } else if (data !== null && typeof data === 'object') {
    const result: Record<string, any> = {};
    for (const [key, value] of Object.entries(data)) {
      const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
      result[camelKey] = convertToCamelCase(value);
    }
    return result;
  }
  return data;
}

export function convertTestCaseFormData(formData: TestCaseFormData): Record<string, any> {
  const convertedData = {...formData};

  if (convertedData.config) {
    convertedData.config = normalizeTestCaseConfig(convertedData.config);
  }

  // ---- 算法参数独立列：按轮分组 [{round_number, params:[{field_code, field_value}]}] ----
  // 优先使用顶层 algorithm_params 独立列；若为空，则从 config.rounds[].algorithmParams 兼容提取
  let groupedAlgParams: any[] = Array.isArray((convertedData as any).algorithm_params)
    ? (convertedData as any).algorithm_params
    : [];

  // 兼容旧格式：如果顶层是 algorithmParams（对象或数组），归一化后合并
  if ((convertedData as any).algorithmParams) {
    const rawAlgParams = (convertedData as any).algorithmParams;
    if (!Array.isArray(rawAlgParams) && typeof rawAlgParams === 'object') {
      // 对象格式 → 单轮 params
      const params = Object.entries(rawAlgParams).map(([key, value]) => ({
        field_code: key,
        field_value: value,
      }));
      groupedAlgParams = [{ round_number: 1, params }];
    }
    delete (convertedData as any).algorithmParams;
  }

  // 从 config.rounds 兼容提取（子组件编辑期间仍写入 round.algorithmParams）
  const rounds = (convertedData.config as any)?.rounds;
  if (Array.isArray(rounds)) {
    for (const round of rounds) {
      const rn = round.roundNumber ?? 1;
      const existing = groupedAlgParams.find((e: any) => e.round_number === rn);
      if (round.algorithmParams && Array.isArray(round.algorithmParams)) {
        if (existing) {
          // 独立列已有该轮数据，用 round 上的补充缺失的 field_code
          for (const p of round.algorithmParams) {
            if (!existing.params.find((ep: any) => ep.field_code === p.field_code)) {
              existing.params.push({ field_code: p.field_code, field_value: p.field_value });
            }
          }
        } else {
          groupedAlgParams.push({
            round_number: rn,
            params: round.algorithmParams.map((p: any) => ({
              field_code: p.field_code,
              field_value: p.field_value,
            })),
          });
        }
        // 新设计：round 不含算法参数，从 round 上移除
        delete round.algorithmParams;
      }
    }
  }
  (convertedData as any).algorithm_params = groupedAlgParams;

  // ---- 参考参数独立列：按轮分组 [{round_number, reference_params_path}] ----
  let groupedRefParams: any[] = Array.isArray((convertedData as any).reference_params)
    ? (convertedData as any).reference_params
    : [];

  // 兼容旧格式
  if ((convertedData as any).referenceParams) {
    const rawRefParams = (convertedData as any).referenceParams;
    if (!Array.isArray(rawRefParams) && typeof rawRefParams === 'object') {
      if (Object.keys(rawRefParams).length === 0) {
        delete (convertedData as any).referenceParams;
      } else {
        groupedRefParams = Object.entries(rawRefParams).map(([key, value]: [string, any]) => ({
          round_number: Number(key) || 1,
          reference_params_path: typeof value === 'string' ? value : (value?.reference_params_path ?? ''),
        }));
      }
    }
    delete (convertedData as any).referenceParams;
  }

  // 从 config.rounds 兼容提取 referenceParamsPath
  if (Array.isArray(rounds)) {
    for (const round of rounds) {
      const rn = round.roundNumber ?? 1;
      if (round.referenceParamsPath) {
        const existing = groupedRefParams.find((e: any) => e.round_number === rn);
        if (existing) {
          existing.reference_params_path = round.referenceParamsPath;
        } else {
          groupedRefParams.push({ round_number: rn, reference_params_path: round.referenceParamsPath });
        }
        delete round.referenceParamsPath;
      }
    }
  }
  if (groupedRefParams.length > 0) {
    (convertedData as any).reference_params = groupedRefParams;
  } else {
    delete (convertedData as any).reference_params;
  }

  return convertToSnakeCase(convertedData);
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export function generateDeviceFields(deviceType: string): FormField[] {
  const baseFields: FormField[] = [
    { key: 'name', label: '设备名称', type: 'text', required: true, placeholder: '请输入设备名称' },
    { key: 'description', label: '设备描述', type: 'textarea', placeholder: '请输入设备描述信息' }
  ];

  switch (deviceType) {
    case 'test':
      return [
        ...baseFields, 
        { 
          key: 'keywords', 
          label: '驱动关键字', 
          type: 'select', 
          required: false, 
          placeholder: '请选择驱动匹配关键字', 
          hint: '用于在测试时选择对应的设备驱动',
          options: [],
          action: 'loadDriverKeywords'
        },
        {
          key: 'model',
          label: '设备型号',
          type: 'text',
          required: true,
          placeholder: '请输入设备型号'
        }, { 
          key: 'type',
          label: '设备类型',
          type: 'text',
          required: true,
          placeholder: '例如：smartphone'
        }, { 
          key: 'system',
          label: '设备系统',
          type: 'select',
          required: true,
          options: [
            { value: 'ios', label: 'iOS' },
            { value: 'android', label: 'Android' },
            { value: 'harmony', label: 'HarmonyOS' }
          ]
        }, { 
          key: 'systemVersion',
          label: '系统版本',
          type: 'text',
          required: true,
          placeholder: '例如：16.4.1'
        }, { 
          key: 'appName',
          label: '应用名称',
          type: 'text',
          required: true,
          placeholder: '请输入应用名称'
        }, { 
          key: 'appVersion',
          label: '应用版本',
          type: 'text',
          required: true,
          placeholder: '例如：1.0.0'
        }, { 
          key: 'connectionType',
          label: '连接方式',
          type: 'radio',
          required: true,
          options: [
            { value: 'usb', label: 'USB连接' },
            { value: 'remote', label: '远程连接' }
          ],
          defaultValue: 'usb'
        }, { 
          key: 'serialNumber',
          label: '设备序列号',
          type: 'text',
          required: true,
          placeholder: '由设备选择自动填充',
          disabled: true
        }, { 
          key: 'ipAddress',
          label: 'IP地址',
          type: 'text',
          required: false,
          placeholder: '请输入设备IP地址（远程连接时必填）',
          conditional: {field: 'connectionType', value: 'remote'}
        }, { 
          key: 'port',
          label: '端口',
          type: 'number',
          required: false,
          placeholder: '请输入设备端口（远程连接时必填）',
          min: 1,
          max: 65535,
          conditional: {field: 'connectionType', value: 'remote'}
        }, { 
          key: 'needs_prompt_audio',
          label: '是否需要提示词',
          type: 'switch',
          required: false,
          defaultValue: false,
          hint: '设备测试时是否需要播放提示词音频'
        }, {
          key: 'supportedAlgorithms',
          label: '算法类型',
          type: 'algorithmSelect',
          required: false,
          hint: '选择该设备关联的算法类型'
        }];
    
    case 'playback':
      return [...baseFields, {
        key: 'model',
        label: '设备型号',
        type: 'text',
        required: true,
        placeholder: '请输入设备型号' 
      }, {
        key: 'deviceType',
        label: '设备类型',
        type: 'select',
        required: true,
        options: [
          { value: 'dry', label: '干声设备' },
          { value: 'noise', label: '噪声设备' }
        ]
      }, { 
        key: 'deviceUniqueId',
        label: '系统唯一标识',
        type: 'text',
        required: true,
        placeholder: '由设备选择自动填充',
        disabled: true
      }, {
        key: 'channelIndex',
        label: '通道索引',
        type: 'number',
        required: false,
        placeholder: '请输入通道索引',
        min: 0,
        defaultValue: 0
      }, {
        key: 'sampleRate',
        label: '采样率',
        type: 'number',
        required: true,
        placeholder: '请输入采样率',
        min: 8000,
        max: 192000
      }, {
        key: 'currentSplMappingId',
        label: '声压映射',
        type: 'select',
        required: false,
        placeholder: '请选择声压映射',
        hint: '选择当前设备使用的声压级映射配置',
        options: [],
        action: 'loadSplMappings'
      }];
    
    case 'api':
      const defaultMaxProcess = 5;
      const defaultMaxTimeout = 30;
      const defaultMaxAudioDuration = 60;
      
      const apiBaseFields = baseFields.filter(field => field.key !== 'name');
      
      return [...apiBaseFields, {
        key: 'name',
        label: 'API名称',
        type: 'text',
        required: true,
        placeholder: '请输入API名称'
      }, {
        key: 'vendor',
        label: '供应商 (vendor)',
        type: 'text',
        required: false,
        placeholder: '请输入供应商名称 (如 volc_ast, ali, tencent)',
        hint: '指定 API 的服务供应商标识'
      }, {
        key: 'apiUrl',
        label: 'Master 入口 URL',
        type: 'text',
        required: false,
        placeholder: '请输入 Master 调度节点 URL (分布式架构必填)',
        hint: '在分布式架构中，作为 Master 节点的统一调度入口'
      }, {
        key: 'algorithmType',
        label: '算法类型',
        type: 'select',
        required: false,
        placeholder: '请选择算法类型',
        hint: '选择API对应的算法类型，用于筛选和分类',
        options: [],
        action: 'loadAlgorithmTypes'
      }, {
        key: 'meta',
        label: 'API元数据',
        type: 'apiMeta',
        required: true,
        hint: '配置API的协议、环境、版本等信息'
      }, {
        key: 'defaultMaxProcess',
        label: '默认最大进程数',
        type: 'number',
        required: false,
        placeholder: '请输入默认最大进程数',
        min: 1,
        max: 100,
        defaultValue: defaultMaxProcess,
        hint: '未单独设置时，所有端点将使用此默认值'
      }, {
        key: 'defaultMaxTimeout',
        label: '默认最大超时时间',
        type: 'number',
        required: false,
        placeholder: '请输入默认最大超时时间（秒）',
        min: 1,
        max: 300,
        defaultValue: defaultMaxTimeout,
        hint: '未单独设置时，所有端点将使用此默认值'
      }, {
        key: 'defaultMaxAudioDuration',
        label: '默认最大音频时长',
        type: 'number',
        required: false,
        placeholder: '请输入默认最大音频时长（秒）',
        min: 1,
        max: 3600,
        defaultValue: defaultMaxAudioDuration,
        hint: '未单独设置时，所有端点将使用此默认值'
      }, {
        key: 'endpoints',
        label: 'API端点列表',
        type: 'array',
        required: true,
        arrayItemType: 'apiEndpoint',
        arrayItemTemplate: {endpoint: '', name: '', priority: 1, maxProcess: defaultMaxProcess, maxTimeout: defaultMaxTimeout, maxAudioDuration: defaultMaxAudioDuration},
        hint: '配置API的各个端点，包括URL、名称和优先级、最大进程数、超时时间和音频时长。未单独设置的值将使用上方的默认值'
      }];
    
    default:
      return baseFields;
  }
}
