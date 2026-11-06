/**
 * 逻辑音箱组领域模型（domain 层；零依赖）。
 * 一个逻辑音箱 = 一个物理位置（如「设备正面 0.5m」），组内每个实验室各挂一台实体播放设备；
 * N 个实验室共享同一逻辑音箱，执行时按「执行实验室」取出对应实体设备（后端换绑）。
 * 用例可直接关联逻辑音箱（config 内 playback_speaker_group_id），老用例仍可指定实体设备。
 */

/** 逻辑音箱在某实验室对应的实体播放设备 */
export interface PlaybackSpeakerGroupItem {
  id: number | null
  groupId: number
  labId: number
  playbackDeviceId: number
}

/** 逻辑音箱（组） */
export interface PlaybackSpeakerGroup {
  id: number
  name: string
  description: string | null
  items: PlaybackSpeakerGroupItem[]
  createdAt: string | null
  updatedAt: string | null
}

/** 逻辑音箱组新建/编辑入参 */
export interface PlaybackSpeakerGroupInput {
  name: string
  description?: string | null
}

/** 某实验室在组内的对应设备入参 */
export interface PlaybackSpeakerGroupItemInput {
  labId: number
  playbackDeviceId: number
}

/** 用例音频「播放设备」选项：逻辑音箱（组）与实体设备二选一 */
export const SPEAKER_GROUP_OPTION_PREFIX = 'group:'

/** 逻辑音箱选项值（与实体设备 id 区分） */
export const speakerGroupOptionValue = (groupId: number): string =>
  `${SPEAKER_GROUP_OPTION_PREFIX}${groupId}`

/** 解析选项值中的逻辑音箱 id（非组选项返回 null） */
export const speakerGroupIdOfOption = (value: string): number | null => {
  if (!value.startsWith(SPEAKER_GROUP_OPTION_PREFIX)) return null
  const id = Number(value.slice(SPEAKER_GROUP_OPTION_PREFIX.length))
  return Number.isFinite(id) && id > 0 ? id : null
}
