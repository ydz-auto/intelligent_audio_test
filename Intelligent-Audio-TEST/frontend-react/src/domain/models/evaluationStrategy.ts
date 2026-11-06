/**
 * 用例评估配置领域模型（domain 层）：整体评估维度 + 全局背景噪声两项用例级配置。
 * 评估策略（策略复用/引用/覆盖）已从前端下线，用例直载 config.dimensions / config.background_noise。
 * snake_case 仅存在于 infrastructure 层，前端 Domain 一律 camelCase。
 */

/** 用例维度配置项（TestCaseDimensionItem，schemas/testcase.py 实测 {id,name,weight,threshold,device_type}） */
export interface TestCaseDimensionItem {
  id: number | string
  name: string
  weight: number
  threshold: number
  /** 历史 LLM Judge 配置残留（旧数据原样透传，前端不再写新值；INT-1681） */
  llmJudgeConfig?: {
    model: string
    promptTemplate: string
  }
}

/** 全局背景噪声（TestCaseBackgroundNoiseItem，schemas/testcase.py:68-82 实测，extra='allow' 兼容文件名/设备名格式） */
export interface TestCaseBackgroundNoiseItem {
  audioId?: number | string | null
  audioName?: string | null
  /** 冗余音频简报（mock 侧携带 name/duration/tags；接线后由 audioId 解析或直接省略） */
  audio?: {
    id: number | string
    name: string
    duration?: number | null
    tags?: string[]
  } | null
  /** 声压级（dB） */
  spl?: number | null
  /** 历史字段：实体播放设备 id（用例只关联逻辑音箱后不再写入） */
  deviceIds?: Array<number | string>
  /** 逻辑音箱组 id（全局噪声可多选；用例唯一可选的播放目标） */
  speakerGroupIds?: Array<number | string>
  /** 播放设备名（旧配置残留名；未匹配到 ID 时黄色警示 chip） */
  playbackDeviceNames?: string[]
  playbackDeviceName?: string | null
  deviceNames?: string[]
  /** 循环播放 */
  loop?: boolean
}


