/**
 * 音频/上传表单 UI 常量（infrastructure 层；16_设备域.md §6.16/§6.17 上传选项数据源）。
 * 音频列表/标签/文件夹树数据已随 INT-645 切真实后端（见 infrastructure/api/audios-api.ts），
 * 此处仅保留无后端端点的静态表单选项：播放设备、用例分组、默认声压级。
 */

/** 播放设备（上传弹窗「播放设备」下拉；tester 无 playback:read 缺口见 §11-5） */
export const MOCK_PLAYBACK_DEVICES = [
  { id: 1, name: '干声测试音频接口 A', model: 'UA-22', channelIndex: 0, deviceType: 'dry' },
  { id: 2, name: '噪声测试音频接口 B', model: 'UA-44', channelIndex: 1, deviceType: 'noise' },
  { id: 3, name: '蓝牙音箱', model: 'SRS-XB13', channelIndex: 2, deviceType: 'dry' },
]

/** 上传完成默认声压级（30-120 默认 65） */
export const MOCK_DEFAULT_SPL = 65

/** 用例分组（§6.16 radio：根目录/文件夹名/自定义） */
export const MOCK_CASE_GROUP_OPTIONS = [
  { value: 'root', label: '根目录' },
  { value: 'folder', label: '文件夹名' },
  { value: 'custom', label: '自定义' },
]
