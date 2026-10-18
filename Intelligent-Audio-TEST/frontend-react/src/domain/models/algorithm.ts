/**
 * 全局算法切换器领域模型（domain 层）。
 * 真实数据源：GET /api/v1/algorithm/options（algorithm:read；仅在线算法）——
 * 选项项 `{ value=type 算法类型码, name }`（infrastructure/dto/algorithm.dto.ts
 * snake→camel 转换，value 与 useAlgorithmStore.algorithmId 同源）。
 * AlgorithmOption/MOCK_ALGORITHMS 为红线④ mock 常量（页面级「当前算法」chip 与
 * 测试执行步骤一按 id 查名的本地占位；壳切换器已切真实选项，页面 chip 待各页接线卡收口）。
 */

/** 真实算法选项（下拉框用；value=算法类型码，name=展示名） */
export type AlgorithmSwitchOption = {
  value: string
  name: string
}

/** mock 算法项（红线④；仅页面 chip/测试执行本地查名占位，不接真实端点） */
export type AlgorithmOption = {
  id: string
  name: string
  version: string
  description: string
  enabled: boolean
}

/** 测试执行算法选项（GET /algorithm/options 映射；INT-646 返修真实端点实测仅下发 value/name） */
export interface TestAlgorithmOption {
  id: string
  name: string
}

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
