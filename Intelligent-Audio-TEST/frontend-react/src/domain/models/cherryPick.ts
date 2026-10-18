/**
 * 挑选合并功能域模型（18_挑选合并功能交互重设计.md §7.4，INT-600）。
 * 前端只见 camelCase Domain；snake_case 收敛在 infrastructure/adapters/dto。
 * 依赖规则：domain 零依赖（不 import application/infrastructure/interfaces）。
 */

/** 挑选层级（四级分组 + 结果行叶） */
export type PickLevel = 'task' | 'case' | 'device' | 'resultType'

/** 可挑选任务终态集合（cherry_pick_service.py PickableTaskStatus 实测） */
export const PICKABLE_TASK_STATUS = ['completed', 'failed', 'stopped'] as const
export type PickableTaskStatus = (typeof PICKABLE_TASK_STATUS)[number]

/** 候选叶（CherryPickCandidate，候选行转换后形态） */
export interface CherryPickCandidate {
  resultId: number
  taskId: number
  taskName: string
  caseId: string
  /** 缺名时显示用例 ID（§11-2 降级口径） */
  caseName: string | null
  /** 设备/API 二选一（TestResult.device_id / api_id 实测） */
  deviceId: number | null
  deviceName: string | null
  apiId: number | null
  apiName: string | null
  /** 结果类型（result_data 内解析，缺省 default；缺名时按缺省合并） */
  resultType: string
  executionStatus: string
  evaluationStatus: string
  evaluated: boolean
  createdAt: string
}

/** 挑选树节点——分支（分组级） */
export interface PickTreeBranch {
  kind: 'branch'
  key: string
  level: PickLevel
  name: string
  count: number
  /** 本节点全部子孙结果 id 快照（勾选/取消整组用） */
  resultIds: number[]
  children: PickTreeItem[]
}

/** 挑选树节点——叶（执行结果行） */
export interface PickTreeLeaf {
  kind: 'leaf'
  key: string
  resultId: number
  caseName: string
  deviceName: string | null
  apiName: string | null
  resultType: string
  executionStatus: string
  evaluationStatus: string
  createdAt: string
  /** R10 已加购标记（来自购物车 resultIdSet） */
  added: boolean
}

export type PickTreeItem = PickTreeBranch | PickTreeLeaf

/** 三态勾选态 */
export type SelectionState = 'checked' | 'indeterminate' | 'unchecked'

/** 购物车条目（CherryPickCartItem 快照转换后形态，§4.1） */
export interface PickCartEntry {
  itemId: string
  resultId: number
  sourceTaskId: number
  sourceTaskName: string
  sourceCaseId: string | null
  sourceCaseName: string | null
  sourceDeviceId: number | null
  sourceDeviceName: string | null
  sourceApiId: number | null
  sourceApiName: string | null
  /** §11-5 未补前为 null，result_type 级分组折叠为「结果类型待补充」 */
  sourceResultType: string | null
  executionStatus: string
  /** §11-5 未补前购物车条目后端不返评估状态 → null（界面不渲染该列） */
  evaluationStatus: string | null
  invalid: boolean
}

/** 购物车分组（按来源任务） */
export interface PickCartGroup {
  taskId: number
  taskName: string
  entries: PickCartEntry[]
}

/** 购物车树——分支（与挑选树同层级口径，§4.2） */
export interface CartTreeBranch {
  kind: 'branch'
  key: string
  level: PickLevel
  name: string
  count: number
  /** 本节点全部子孙条目 id 快照（批量移除用） */
  entryIds: string[]
  children: CartTreeItem[]
}

/** 购物车树——叶 */
export interface CartTreeLeaf {
  kind: 'leaf'
  key: string
  entryId: string
  caseName: string
  deviceName: string | null
  apiName: string | null
  resultType: string | null
  executionStatus: string
  evaluationStatus: string | null
  invalid: boolean
}

export type CartTreeItem = CartTreeBranch | CartTreeLeaf

/** 挑选集（另存为挑选集，可恢复进购物车/删除） */
export interface PickSet {
  setId: string
  name: string
  createdAt: string
  itemCount: number
  entries: PickCartEntry[]
}

/** 下单出口（cherry_pick_service.py:897-912 实测） */
export type CheckoutAction = 'merge' | 'reexecute' | 'reevaluate'

/** 复核摘要（POST /cart/preview 返回，§5.2） */
export interface PickPreview {
  totalResults: number
  invalidResultIds: number[]
  sourceTaskCount: number
  deviceIds: number[]
  caseCount: number
  executionStatusCounts: Record<string, number>
  /** 同设备同用例多来源组数 */
  duplicates: number
  configInconsistent: boolean
  configFields: string[]
  sourceConfigs: Record<string, unknown>[]
}

/** 合并容器（统一列表：整任务合并 merged=true ∪ 结果挑选 cherry_pick=true，§11-1） */
export type MergeType = 'whole' | 'picked'

export interface CherryPickSourceTask {
  id: number
  name: string
  resultCount: number
  status: string
}

export interface CherryPickContainer {
  id: number
  name: string
  description: string | null
  executionStatus: string
  evaluationStatus: string
  totalCases: number | null
  mergeType: MergeType
  sourceTaskCount: number
  sourceResultCount: number
  sourceTaskIds: number[]
  sourceTasks: CherryPickSourceTask[]
  createdAt: string
  isFavorite: boolean
}
