import type { TestCaseFormData } from '../shared/types';

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
    await navigator.clipboard.writeText(text);
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

export function normalizeTestCaseConfig(config: Record<string, any>) {
  const rawConfig = config || {};

  const rawBackgroundNoise =
    rawConfig.backgroundNoise ??
    (rawConfig.background_noise
      ? {
          audioId: rawConfig.background_noise.audioId ?? rawConfig.background_noise.audio_id ?? null,
          spl: rawConfig.background_noise.spl ?? null,
          deviceIds: rawConfig.background_noise.deviceIds ?? rawConfig.background_noise.device_ids ?? []
        }
      : undefined);

  const rawAudios: any[] = Array.isArray(rawConfig.audios) ? rawConfig.audios : [];
  const normalizedAudios = rawAudios.map((audio) => ({
    audioId: audio?.audioId ?? audio?.audio_id ?? '',
    testType: audio?.testType ?? audio?.test_type ?? 'api',
    spl: audio?.spl ?? null,
    playbackDeviceId: audio?.playbackDeviceId ?? audio?.playback_device_id ?? null,
    playOrder: audio?.playOrder ?? audio?.play_order ?? 0
  }));

  const rawDimensions = rawConfig.dimensions;
  const normalizedDimensions =
    Array.isArray(rawDimensions)
      ? { api: rawDimensions, e2e: rawDimensions }
      : {
          api: rawDimensions?.api ?? rawDimensions?.api_dimensions ?? rawConfig.apiEvaluationDimensions ?? [],
          e2e: rawDimensions?.e2e ?? rawDimensions?.e2e_dimensions ?? rawConfig.e2eEvaluationDimensions ?? []
        };

  const baseConfig: NonNullable<TestCaseFormData['config']> = {
    backgroundNoise: {
      audioId: rawBackgroundNoise?.audioId ?? rawConfig?.noiseAudio ?? null,
      spl: rawBackgroundNoise?.spl ?? rawConfig?.noiseAudioSpl ?? null,
      deviceIds: rawBackgroundNoise?.deviceIds ?? rawConfig?.noiseAudioDeviceIds ?? []
    },
    audios: normalizedAudios,
    dimensions: {
      api: normalizedDimensions.api || [],
      e2e: normalizedDimensions.e2e || []
    }
  };

  if (baseConfig.audios.length === 0) {
    if (rawConfig?.apiAudio) {
      baseConfig.audios.push({ 
        audioId: rawConfig.apiAudio, 
        testType: 'api', 
        spl: null, 
        playbackDeviceId: null, 
        playOrder: 1 
      });
    }
    if (rawConfig?.dryAudios && Array.isArray(rawConfig.dryAudios)) {
      rawConfig.dryAudios.forEach((dryAudio: {file: string; spl: number | null; device: string | null}) => {
        baseConfig.audios.push({ 
          audioId: dryAudio.file, 
          testType: 'e2e', 
          spl: dryAudio.spl, 
          playbackDeviceId: dryAudio.device, 
          playOrder: baseConfig.audios.length + 1 
        });
      });
    }
  }

  const apiAudios = baseConfig.audios.filter((a: any) => a.testType === 'api');
  const dryAudios = baseConfig.audios.filter((a: any) => a.testType === 'e2e');

  return {...baseConfig, apiAudios, dryAudios};
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
    delete convertedData.config.apiAudios;
    delete convertedData.config.dryAudios;
  }

  if (convertedData.algorithmParams && typeof convertedData.algorithmParams === 'object' && !Array.isArray(convertedData.algorithmParams)) {
    const params = convertedData.algorithmParams as Record<string, any>;
    convertedData.algorithmParams = Object.entries(params).map(([key, value]) => ({
      fieldCode: key,
      fieldValue: value
    }));
  }

  if (convertedData.referenceParams && typeof convertedData.referenceParams === 'object' && !Array.isArray(convertedData.referenceParams)) {
    const params = convertedData.referenceParams as Record<string, any>;
    if (Object.keys(params).length === 0) {
      delete convertedData.referenceParams;
    } else {
      convertedData.referenceParams = Object.entries(params).map(([key, value]) => ({
        code: key,
        ...value
      }));
    }
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
