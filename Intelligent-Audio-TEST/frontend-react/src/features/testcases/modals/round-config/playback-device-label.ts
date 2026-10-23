/**
 * 播放设备选项文案（用例域噪声/声压等设备 chips 共用）。
 * 与设备域「{设备名} (通道 {n}) [干声/噪声]」同口径（GET /playback-devices 真实字段）。
 */
import type { PlaybackDevice } from '@/domain/models/playbackDevice'

export const playbackDeviceLabel = (d: PlaybackDevice): string =>
  `${d.name} (通道 ${d.channelIndex ?? '—'}) [${
    d.deviceType === 'dry' ? '干声' : d.deviceType === 'noise' ? '噪声' : d.deviceType ?? '未知'
  }]`
