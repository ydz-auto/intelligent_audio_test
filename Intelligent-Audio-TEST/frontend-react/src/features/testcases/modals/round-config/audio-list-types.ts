/**
 * 音频列表步骤的展示层载体类型（11_用例域.md §5.1；面板与步骤页共用）。
 * 数据源是真实接口：播放设备来自 GET /playback-devices、音频行来自音频库列表，
 * 这里只承载展示投影，不含 mock 数据。
 */

/** 播放设备展示项（Select「{设备名} (通道 {n}) [干声/噪声]」，由 PlaybackDevice 投影而来） */
export interface PlaybackDeviceOption {
  id: string
  name: string
  channel: number
  type: '干声' | '噪声'
}

/** 音频文件展示项（卡头「音频 {n}｜文件名｜时长｜标签 chips」） */
export interface AudioFileOption {
  id: string
  name: string
  duration: string
  tags: string[]
}
