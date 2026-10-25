// -*- coding: utf-8 -*-
/**
 * 挑选合并容器「组成」条目模型（INT-1833 · 《UX设计规范-VUE 18_挑选合并_合并后任务呈现》§4.1/§12.2）。
 *
 * 容器是既成事实：组成区只读呈现「合并后的任务长什么样」，条目 = 源结果一行。
 * 字段口径与购物车条目（PickCartItem）同形，不新造第二套字段；差异只在容器叶行展示所需的
 * 评估状态 / 源结果时间 / 用例组织字段。
 *
 * 降级口径（§4.6，§11-8 的 source.results[] 契约未落地前）：
 * - executionStatus / evaluated 取同 source_case_id 的容器用例行（statusFromCase /
 *   evaluationFromCase 记录来源，工具行据此显示一次性提示）；
 * - resultType 折叠为 null（展示「结果类型待补充」）；
 * - resultCreatedAt 只认 §11-8 的 result_created_at；未落地 → null，叶行时间位不渲染。
 *   严禁映射 source.results[].created_at——那是 task_cherry_pick_relations 关系行时间。
 */

/** 组成条目（source.groups[].results[] + 容器详情 cases[]/devices[]/apis[] join） */
export interface CompositionEntry {
  /** 源结果 ID（叶行「源结果 #{id}」） */
  resultId: number
  sourceTaskId: number
  sourceTaskName: string
  sourceCaseId: string | null
  /** 用例名；缺名 → null（展示降级「未知用例」，不裸显 UUID） */
  sourceCaseName: string | null
  sourceDeviceId: number | null
  sourceDeviceName: string | null
  sourceApiId: number | null
  sourceApiName: string | null
  /** 结果类型；缺值 → null（展示「结果类型待补充」） */
  resultType: string | null
  /** 执行状态（源结果状态；降级期取容器用例行） */
  executionStatus: string | null
  /** 评估状态：true 已评估 / false 未评估 / null 未知（不显示徽章） */
  evaluated: boolean | null
  /** 源结果已失效（源任务或结果已删除，仅保留溯源记录） */
  missing: boolean
  /** 源结果自身创建时间（§11-8 的 result_created_at）；未落地 → null，叶行时间位不渲染 */
  resultCreatedAt: string | null
  /** 用例分组名（详情 cases[].group_name；用例层组织数据源；缺值 → null 落「未分组」） */
  groupName: string | null
  /** 用例标签（详情 cases[].tags；缺值 → [] 落「未设置标签」） */
  tags: string[]
  /** 执行状态是否降级自容器用例行（§4.6 工具行提示判定） */
  statusFromCase: boolean
  /** 评估状态是否降级自容器用例行（§4.6 工具行提示判定） */
  evaluationFromCase: boolean
}

/** 组成摘要（按过滤后条目统计，§4.2 summarizeComposition） */
export interface CompositionSummary {
  /** 结果条数 */
  total: number
  /** 执行失败条数 */
  failed: number
  /** 未评估条数 */
  unevaluated: number
  /** 失效条数 */
  missing: number
  /** 来源任务数 */
  taskCount: number
  /** 用例数（去重 source_case_id） */
  caseCount: number
  /** 设备 / API 数（去重） */
  deviceCount: number
}

/** 工具行执行状态筛选（§4.2/§5：全部 / 已完成 / 已失败 / 已停止） */
export type CompositionExecutionFilter = 'all' | 'completed' | 'failed' | 'stopped'

/** 工具行评估状态筛选（全部 / 已评估 / 未评估） */
export type CompositionEvaluationFilter = 'all' | 'evaluated' | 'unevaluated'
