/**
 * 全局算法切换器领域模型（domain 层）。
 * 形态对照算法配置域接口 schema；TODO(API 接线): 换 GET /algorithms 真实数据源。
 */

export type AlgorithmOption = {
  id: string
  name: string
  version: string
  description: string
  enabled: boolean
}

/** 红线④：mock 常量，不接真实后端 */
export const MOCK_ALGORITHMS: AlgorithmOption[] = [
  {
    id: 'asr-v3',
    name: '通用识别引擎',
    version: 'v3.2.0',
    description: '端到端语音识别基线模型',
    enabled: true,
  },
  {
    id: 'asr-stream',
    name: '流式识别引擎',
    version: 'v2.8.1',
    description: '低延迟流式转写引擎',
    enabled: true,
  },
  {
    id: 'eval-ensemble',
    name: '多维评估集成',
    version: 'v1.9.0',
    description: '多维度指标集成评估算法',
    enabled: true,
  },
  {
    id: 'asr-experimental',
    name: '实验识别引擎',
    version: 'v0.9.0-beta',
    description: '实验性模型，仅供内部验证',
    enabled: false,
  },
]
