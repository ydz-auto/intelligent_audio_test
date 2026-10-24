/**
 * 播放设备选项（application 层；GET /playback-devices 真实数据，INT-1512）。
 * 上传选项弹窗与音频试听弹窗共用同一 queryKey ['playback-devices']，缓存互复用，
 * 两处下拉的设备条目/默认值口径一致，不再各自维护一份静态列表。
 */
import { useQuery } from '@tanstack/react-query'

import {
  fetchPlaybackDevices,
  type PlaybackDeviceOption,
} from '@/infrastructure/api/audio-upload-api'

export function usePlaybackDevices() {
  return useQuery<PlaybackDeviceOption[]>({
    queryKey: ['playback-devices'],
    queryFn: fetchPlaybackDevices,
    staleTime: 5 * 60_000,
  })
}
