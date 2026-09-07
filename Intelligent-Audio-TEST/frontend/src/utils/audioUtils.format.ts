/**
 * audioUtils —— 文件大小与音频时长格式化
 *
 * 提供文件大小展示、时长格式化（分:秒 / 天时分秒长格式）与时长字符串解析，
 * 以及原始音频数据的展示层格式化（formatAudioData）。
 */
import { SECONDS_PER_MINUTE, SECONDS_PER_HOUR, SECONDS_PER_DAY, FILE_SIZE_BASE } from './audioUtils.constants';

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

  while (currentSize >= FILE_SIZE_BASE && unitIndex < units.length - 1) {
    currentSize /= FILE_SIZE_BASE;
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
  const mins = Math.floor(seconds / SECONDS_PER_MINUTE);
  const secs = Math.floor(seconds % SECONDS_PER_MINUTE);
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
      return parts[0] * SECONDS_PER_MINUTE + parts[1];
    } else if (parts.length === 3) {
      return parts[0] * SECONDS_PER_HOUR + parts[1] * SECONDS_PER_MINUTE + parts[2];
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
  const days = Math.floor(seconds / SECONDS_PER_DAY);
  const hours = Math.floor((seconds % SECONDS_PER_DAY) / SECONDS_PER_HOUR);
  const mins = Math.floor((seconds % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  const secs = Math.floor(seconds % SECONDS_PER_MINUTE);
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
  filepath?: string;
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
  const filepath = audio.path ?? audio.filePath ?? '';
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
