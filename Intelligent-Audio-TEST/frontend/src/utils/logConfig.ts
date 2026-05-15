/**
 * 日志配置文件
 * 从shared目录导入日志类型定义，并提供前端使用的具体选项数据
 */

export interface OptionItem {
  value: string;
  label: string;
}

export const logCategoryOptions: OptionItem[] = [
  { value: 'all', label: '所有' },
  { value: 'frontend', label: '前端' },
  { value: 'backend', label: '后端' },
  { value: 'execution', label: '执行' },
  { value: 'system', label: '系统' },
  { value: 'test', label: '测试' },
  { value: 'device', label: '设备' },
  { value: 'api', label: 'API' },
  { value: 'audio', label: '音频' },
  { value: 'user', label: '用户' }
];

export const logModuleOptions: OptionItem[] = [
  { value: 'all', label: '所有' },
  { value: 'test', label: '测试' },
  { value: 'device', label: '设备' },
  { value: 'system', label: '系统' },
  { value: 'user', label: '用户' },
  { value: 'api', label: 'API' },
  { value: 'audio', label: '音频' },
  { value: 'execution', label: '执行' },
  { value: 'task', label: '任务' }
];

export const logLevelOptions: OptionItem[] = [
  { value: 'debug', label: 'DEBUG' },
  { value: 'info', label: 'INFO' },
  { value: 'warning', label: 'WARNING' },
  { value: 'error', label: 'ERROR' }
];

export const logMarkOptions: OptionItem[] = [
  { value: 'all', label: '所有标记' },
  { value: 'yellow', label: '黄色' },
  { value: 'red', label: '红色' },
  { value: 'green', label: '绿色' },
  { value: 'blue', label: '蓝色' },
  { value: 'unmarked', label: '未标记' }
];

export const logLevelMap: Record<string, string> = {debug: 'DEBUG', info: 'INFO', warning: 'WARN', error: 'ERROR'};

export const logLevelReverseMap: Record<string, string> = {DEBUG: 'debug', INFO: 'info', WARN: 'warning', ERROR: 'error'};

export const logCategoryMap: Record<string, string> = {frontend: 'frontend', backend: 'backend', execution: 'execution', system: 'system', test: 'test', task: 'task', device: 'device', api: 'api', audio: 'audio', user: 'user'};
