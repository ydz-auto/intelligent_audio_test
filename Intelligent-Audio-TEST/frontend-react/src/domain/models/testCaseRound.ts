/**
 * 用例轮次配置领域模型（domain 层；11_用例域.md §5.1 RoundConfigEditor）。
 * 编辑抽屉轮次草稿（RoundDraft）携带评估草稿（RoundEvaluationDraft）、音频草稿
 * （RoundAudioDraft）与算法参数/噪声草稿（RoundAlgorithmParamItem/RoundNoiseDraft）；
 * 保存侧序列化为后端 config.rounds[]（schemas/testcase.py RoundConfigItem：
 * round_number/audios/evaluation）+ algorithm_params 独立列。
 * 音频草稿字段对照 TestCaseAudioConfigItem（audio_id/audio_name/spl/
 * playback_device_id/playback_device_name）真实回填 + 编辑变更（INT-877 P1-1）；
 * 算法参数/噪声草稿由 INT-996 引入（独立列 params + segment 级 noise 序列化）。
 */

/** 单轮评估草稿（§5.1 评估维度步骤；params 按维度 id 存权重/阈值，没有模型 / Prompt 配置） */
export interface RoundEvaluationDraft {
  /** 启用本轮评估（首轮默认开；addRound 复制上一轮 enabled） */
  enabled: boolean
  selectedIds: number[]
  params: Record<number, { weight: number; threshold: number }>
}

/** 默认新轮评估草稿（enabled=false：新轮次默认关闭，首轮由调用方置 true） */
export const newRoundEvaluation = (): RoundEvaluationDraft => ({
  enabled: false,
  selectedIds: [],
  params: {},
})

/**
 * 单轮音频草稿（§5.1 音频列表步骤；受控于抽屉保存侧）。
 * audioId/audioName 由 config.rounds[].audios 真实回填（schemas/testcase.py
 * TestCaseAudioConfigItem：audio_id/audio_name/spl/playback_device_id/playback_device_name），
 * 变更并入 handleSave 的 config.rounds[].audios（INT-877 P1-1）。
 */
export interface RoundAudioDraft {
  /** 本地行身份（React key；复制/标签交错时经 newId 克隆独立行） */
  id: string
  /** 真实音频 id（audio_id；未关联=null） */
  audioId: number | string | null
  /** 音频文件名（audio_name；真实回填/子弹窗选择） */
  audioName: string | null
  /** 声压级 dB */
  spl: number
  /** 播放设备 id（string 归一；playback_device_id 接受 int|str） */
  deviceId: string
  /** 播放设备名（playback_device_name；Select 值回退展示） */
  deviceName: string | null
  /** 播放顺序（play_order 保留回传） */
  playOrder?: number | null
  /** 音频时长（秒；子弹窗选择回填，卡头展示） */
  duration?: number | null
  /** 标签（子弹窗选择回填；批量标签工具数据源） */
  tags?: string[]
}

/** 算法参数项（后端 AlgorithmParamItem：{field_code, field_value}；INT-996 独立列 params 数组元素） */
export interface RoundAlgorithmParamItem {
  field_code: string
  field_value: unknown
}

/** 轮次级背景噪声草稿（INT-996；保存写入 config.rounds[].audios[].background_noise） */
export interface RoundBackgroundNoiseDraft {
  audioId: number | string | null
  audioName?: string | null
  /** 冗余音频简报（音频选择弹窗回填 name/duration/tags；保存侧序列化时剔除） */
  audio?: {
    id: number | string
    name: string
    duration?: number | null
    tags?: string[]
  } | null
  /** 声压级（dB；§5.3.4 建议值 94） */
  spl: number
  /** 播放设备 id 列表（真实 /playback-devices） */
  deviceIds: Array<number | string>
  /** 循环播放 */
  loop: boolean
}

/** 轮次声纹注册草稿（INT-996；保存写入 algorithm_params 独立列 field_code='voiceprint'） */
export interface RoundVoiceprintDraft {
  enabled: boolean
  audioId: number | string | null
  audioName?: string | null
  playbackDeviceId: number | string | null
  /** 播放声压级（dB） */
  spl: number
  /** 注册后等待秒数（0-60） */
  waitSec: number
}

/** 单个干扰人草稿（INT-996；保存写入 config.rounds[].audios[].interferers） */
export interface RoundInterfererDraft {
  /** 本地行 id（仅渲染 key/删除定位用；保存序列化时剔除） */
  id: string
  audioId: number | string | null
  audioName?: string | null
  playbackDeviceId: number | string | null
  /** 声压级（dB） */
  spl: number
  /** 开始延迟秒 */
  startDelay: number
  /** 循环播放 */
  loop: boolean
}

/** 轮次噪声与干扰草稿（INT-996；算法参数步骤排除的 voiceprint/interferers/背景噪声集中在此） */
export interface RoundNoiseDraft {
  backgroundNoise: RoundBackgroundNoiseDraft | null
  voiceprint: RoundVoiceprintDraft
  interferers: RoundInterfererDraft[]
}

/** 默认空声纹草稿（§5.1 声纹注册配置节：播放声压级默认 75、等待 5s） */
export const emptyVoiceprint = (): RoundVoiceprintDraft => ({
  enabled: false,
  audioId: null,
  audioName: null,
  playbackDeviceId: null,
  spl: 75,
  waitSec: 5,
})

/** 默认空噪声与干扰草稿（背景噪声未配置 + 声纹关闭 + 无干扰人） */
export const emptyRoundNoise = (): RoundNoiseDraft => ({
  backgroundNoise: null,
  voiceprint: emptyVoiceprint(),
  interferers: [],
})

/**
 * 轮次草稿（左 RoundNav 180px 摘要 + 右步骤区五步表单共用）。
 * INT-877/INT-996 合流：同时携带音频草稿（audios，真实回填+保存）与
 * 算法参数/噪声草稿（algorithmParams 独立列 + noise segment 级序列化）。
 */
export interface RoundDraft {
  number: number
  audioCount: number
  dimensionCount: number
  evaluation: RoundEvaluationDraft
  /** 音频草稿（真实回填 + 编辑变更；保存时序列化为 config.rounds[].audios） */
  audios: RoundAudioDraft[]
  /** INT-996 算法参数独立列 params（[{field_code, field_value}]；DynamicForm 排除声纹/干扰人/音频选择类字段） */
  algorithmParams: RoundAlgorithmParamItem[]
  /** INT-996 噪声与干扰草稿（背景噪声/声纹/干扰人） */
  noise: RoundNoiseDraft
}
