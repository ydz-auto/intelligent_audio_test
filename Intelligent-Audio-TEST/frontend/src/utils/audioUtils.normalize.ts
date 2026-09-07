/**
 * audioUtils —— 音频 URL 构建与音频项归一化
 *
 * 提供播放 URL 构建（buildAudioUrl，统一处理 string / {url} / {id} / {path} 输入）、
 * 音频类型标签（getAudioTypeLabel）与 snake_case → camelCase 音频项归一化
 * （normalizeAudioItem / normalizeAudioFields）。
 */
import { TestType } from '@/domain/enums';
import { readCamel } from './keyTransform';
import { _apiBaseUrl, _apiBaseNoV1, AUDIO_STREAM_BY_PATH } from './audioUtils.constants';

/**
 * 根据音频对象构建播放 URL
 * 统一处理 string / {url} / {id} / {path} 等多种输入格式
 * @param audio - 路径字符串或音频对象
 * @returns 播放 URL
 */
export function buildAudioUrl(audio: any): string {
  if (!audio) return '';

  // 兼容直接传入路径字符串
  if (typeof audio === 'string') {
    return `${_apiBaseNoV1}${AUDIO_STREAM_BY_PATH}?path=${encodeURIComponent(audio)}`;
  }

  // 完整 URL（http 开头），直接返回
  if (audio.url && audio.url.startsWith('http')) {
    return audio.url;
  }

  // 后端返回的 /api 路径
  if (audio.url && audio.url.startsWith('/')) {
    // /api/audios/play/{id} 格式直接用
    if (audio.url.includes('/audios/play/')) {
      return audio.url;
    }
    // 其他 /api 开头路径拼接 baseUrl
    return `${_apiBaseNoV1}${audio.url}`;
  }

  // 优先使用 ID 获取音频
  if (audio.id) {
    const taskType = audio.type || TestType.API;
    return `${_apiBaseUrl}/audios/${audio.id}/stream?task_type=${taskType}`;
  }

  // 回退到路径
  if (audio.path) {
    return `${_apiBaseNoV1}${AUDIO_STREAM_BY_PATH}?path=${encodeURIComponent(audio.path)}`;
  }

  return '';
}

/**
 * 音频类型标签映射
 */
const AUDIO_TYPE_LABELS: Record<string, string> = {
  [TestType.API]: 'API测试音频',
  [TestType.E2E]: 'E2E测试音频',
  noise: '噪声',
  dry: '干声',
};

/**
 * 根据音频类型获取标签
 * @param audioType - 音频类型
 * @returns 标签文本
 */
export function getAudioTypeLabel(audioType: string): string {
  return AUDIO_TYPE_LABELS[audioType] || '测试音频';
}

/**
 * 归一化单个音频项：snake_case → camelCase，补充 timeline/playback 等字段
 * @param audio - 原始音频对象
 * @param fallbackTestType - 兜底类型（来自用例/任务级 testType）
 * @returns 归一化后的音频对象
 */
export function normalizeAudioItem(audio: any, fallbackTestType?: string): any {
  if (!audio || typeof audio !== 'object') return audio;

  const audioType = audio.testType ?? audio.audioType ?? fallbackTestType ?? TestType.API;
  const timelineStart = audio.timelineStart ?? 0;

  return {
    ...audio,
    id: audio.id,
    path: audio.url ?? audio.path,
    type: audioType,
    filename: audio.filename,
    duration: audio.duration,
    spl: audio.spl,
    testType: audioType,
    playOrder: audio.playOrder,
    noiseSpl: audio.noiseSpl,
    deviceId: audio.deviceId,
    deviceName: audio.deviceName,
    playbackDeviceName: audio.playbackDeviceName ?? audio.deviceName,
    timelineStart,
    timelineEnd: audio.timelineEnd ?? (timelineStart + (audio.duration || 0)),
    roundNumber: audio.roundNumber ?? audio.round ?? 1,
  };
}

/**
 * 从用例对象中提取并归一化音频列表
 * 当 caseItem.audios 存在时，将其映射为归一化的 audioList
 * @param caseItem - 用例对象
 * @param taskType - 兜底测试类型
 * @returns 带有 audioList 的用例对象副本
 */
export function normalizeAudioFields(caseItem: any, taskType?: string): any {
  if (!caseItem || typeof caseItem !== 'object') return caseItem;
  const normalized = { ...caseItem };

  const caseTestType = readCamel<string>(normalized, 'testType') ?? taskType ?? TestType.API;

  if (normalized.audios && Array.isArray(normalized.audios) && normalized.audios.length > 0) {
    normalized.audioList = normalized.audios.map((audio: any, idx: number) => {
      const item = normalizeAudioItem(audio, caseTestType);
      // label 兜底需要 idx
      if (!audio.label && !audio.filename) {
        item.label = `${getAudioTypeLabel(item.type)} ${idx + 1}`;
      }
      return item;
    });
  }

  return normalized;
}