/**
 * 全局算法切换器领域模型（domain 层）。
 * 真实数据源：GET /api/v1/algorithm/options（algorithm:read；仅在线算法）——
 * 选项项 `{ value=type 算法类型码, name }`（infrastructure/dto/algorithm.dto.ts
 * snake→camel 转换，value 与 useAlgorithmStore.algorithmId 同源）。
 * INT-1687：原红线④ mock 常量 MOCK_ALGORITHMS 已无消费方（页面 chip / 用例卡徽章
 * 均已切真实选项），随用例卡算法名接线一并移除，算法名统一取自本选项。
 */

/** 真实算法选项（下拉框用；value=算法类型码，name=展示名） */
export type AlgorithmSwitchOption = {
  value: string
  name: string
}

/** 测试执行算法选项（GET /algorithm/options 映射；INT-646 返修真实端点实测仅下发 value/name） */
export interface TestAlgorithmOption {
  id: string
  name: string
}
