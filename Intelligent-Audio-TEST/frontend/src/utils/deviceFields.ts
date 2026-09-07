/** 动态表单字段（key/label 体系，原 FormField 改名）：
 * 区别于 domain/model/algorithm.ts 的算法参数 FormField（fieldCode 体系） */
export interface DynamicFormField {
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

// 兼容 re-export：保持既有 FormField 消费方 import 路径不变
export type { DynamicFormField as FormField };

/** 测试/播放/API 设备动态表单字段定义 */
export function generateDeviceFields(deviceType: string): DynamicFormField[] {
  const baseFields: DynamicFormField[] = [
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