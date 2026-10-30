/**
 * 音频列表步骤的展示层载体类型（11_用例域.md §5.1；面板与步骤页共用）。
 * 数据源是真实接口：播放目标来自 GET /playback-devices/speaker-groups（逻辑音箱），
 * 音频行来自音频库列表，这里只承载展示投影，不含 mock 数据。
 */

/** 播放目标展示项（用例从此只关联逻辑音箱，label 为下拉/面板展示文案） */
export interface PlaybackDeviceOption {
  id: string
  name: string
  /** 展示文案（如「[逻辑音箱] 设备正面（0.5m+0°）」） */
  label: string
}

/** 音频文件展示项（卡头「音频 {n}｜文件名｜时长｜标签 chips」） */
export interface AudioFileOption {
  id: string
  name: string
  duration: string
  tags: string[]
}
