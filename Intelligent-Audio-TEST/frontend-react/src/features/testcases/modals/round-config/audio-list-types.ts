/**
 * 音频列表步骤 mock 载体类型（11_用例域.md §5.1；展示层接口类型，面板与步骤页共用）。
 * 形态对照 api_gateway/schemas/audio.py 播放设备/音频文件字段；mock 态不接后端。
 */

/** 播放设备（Select「{设备名} (通道 {n}) [干声/噪声]」） */
export interface MockDevice {
  id: string
  name: string
  channel: number
  type: '干声' | '噪声'
}

/** 音频文件（卡头「音频 {n}｜文件名｜时长｜标签 chips」） */
export interface MockAudioFile {
  id: string
  name: string
  duration: string
  tags: string[]
}
