/**
 * 挑选合并功能域模型（18_挑选合并功能交互重设计.md §7.4，INT-600）。
 * 前端只见 camelCase Domain；snake_case 收敛在 infrastructure/adapters/dto。
 * 依赖规则：domain 零依赖（不 import application/infrastructure/interfaces）。
 */

/** 挑选层级（四级分组 + 用例层组织 + 结果行叶） */
export type PickLevel = 'task' | 'case' | 'device' | 'resultType' | 'caseOrg'

/** 用例层组织维度（分组视图 / 标签视图；INT-1694 组织层独立一层） */
export type PickCaseOrgDimension = 'group' | 'tag'

/** 用例层子视图（平铺 / 交叉：分组视图内按标签、标签视图内按用例分组） */
export type PickCaseOrgSubView = 'flat' | 'byTag' | 'byGroup'

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
  /** 用例标签（§11-7 候选真名；空数组 → 标签视图「未设置标签」兜底桶） */
  tags: string[]
  /** 用例分组（§11-7；groupId 为 null → 分组视图「未分组」兜底桶） */
  groupId: string | null
  groupName: string | null
  /** 用例时长（秒）/轮次（§11-7；compact 用例卡徽章数据源） */
  totalDuration: number | null
  rounds: number | null
  /** 设备/API 二选一（TestResult.device_id / api_id 实测） */
  deviceId: number | null
  deviceName: string | null
  apiId: number | null
  apiName: string | null
  /** 结果类型（result_data 内解析；后端候选未返 §11-2 → null 折叠为「结果类型待补充」） */
  resultType: string | null
  /** 算法类型（§11-2 候选行实测返回；用例级算法徽章数据源） */
  algorithmType: string | null
  executionStatus: string
  /** 结果级评估状态（候选仅返 evaluated 布尔，转换后 completed/pending） */
  evaluationStatus: string
  evaluated: boolean
  createdAt: string | null
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
  /** 用例级：case_id（CaseIdBadge 复制展示，§3.7.1） */
  caseId?: string
  /** 用例级：算法类型（§3.7.1 算法徽章） */
  algorithmType?: string | null
  /** 用例级：标签（§11-7 真实名；用例层标签视图聚合与用例卡标签行数据源） */
  tags?: string[]
  /** 用例级：用例分组 id/名（§11-7；分组视图聚合，groupId=null 落「未分组」桶） */
  groupId?: string | null
  groupName?: string | null
  /** 用例级：时长（秒）/轮次（§11-7；用例卡徽章数据源） */
  totalDuration?: number | null
  rounds?: number | null
  /** 组织层：当前维度（分组 / 标签；图标与移除文案数据源） */
  orgKind?: PickCaseOrgDimension
}

/** 挑选树节点——叶（执行结果行） */
export interface PickTreeLeaf {
  kind: 'leaf'
  key: string
  resultId: number
  /** §3.8.3 三视图叶行来源任务名消歧（阶段 1 承载任务维度后树内无任务级，叶行补任务名） */
  taskName: string
  caseName: string
  deviceName: string | null
  apiName: string | null
  resultType: string | null
  executionStatus: string
  evaluationStatus: string
  createdAt: string | null
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
  /** 用例标签/分组/时长/轮次（INT-1694：任务视图用例层组织数据源；INT-1693 后端补字段后
   *  由 adapter 映射，当前缺省 → 组织层落「未分组 / 未设置标签」兜底桶） */
  sourceTags?: string[]
  sourceGroupId?: string | null
  sourceGroupName?: string | null
  sourceTotalDuration?: number | null
  sourceRounds?: number | null
  executionStatus: string
  /** 快照未含评估状态 → null 显示「—」（对照原 Vue 购物车口径） */
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
  /** 用例级：sourceCaseId（§4.2 用例节点 CaseCard compact 展示） */
  caseId?: string
  /** 用例级：标签/分组/时长/轮次（INT-1694 任务视图用例层组织；缺省落兜底桶） */
  tags?: string[]
  groupId?: string | null
  groupName?: string | null
  totalDuration?: number | null
  rounds?: number | null
  /** 组织层：当前维度（分组 / 标签；图标与移除文案数据源） */
  orgKind?: PickCaseOrgDimension
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
  /** §4.2 三视图（INT-1128）：叶行来源任务名/ID 消歧（用例/设备/结果类型视图任务维度保留） */
  sourceTaskId: number
  sourceTaskName: string
}

export type CartTreeItem = CartTreeBranch | CartTreeLeaf

/** 挑选集（另存为挑选集，可恢复进购物车/删除） */
export interface PickSet {
  setId: string
  name: string
  createdAt: string | null
  itemCount: number
  entries: PickCartEntry[]
}

/** 下单出口（cherry_pick_service.py:897-912 实测） */
export type CheckoutAction = 'merge' | 'reexecute' | 'reevaluate'

/** 复核重复组（同设备同用例多来源，preview 返回数组逐项展示） */
export interface PickDuplicate {
  deviceId: number | null
  caseId: string | null
  count: number
}

/** 复核摘要（POST /tasks/cherry-picks/preview 返回，§5.2） */
export interface PickPreview {
  totalResults: number
  invalidResultIds: number[]
  sourceTaskCount: number
  deviceIds: number[]
  /** 预览接口返回的设备名（preview device_names 实测；排序与 device_ids 对齐） */
  deviceNames?: string[]
  caseCount: number
  executionStatusCounts: Record<string, number>
  /** 同设备同用例多来源组（后端逐组返回；前端展示组数） */
  duplicates: PickDuplicate[]
  /** 配置差异提示后端未返（§11 FEAT 待 INT-xxx）→ 可选，缺省不展示 */
  configInconsistent?: boolean
  configFields?: string[]
  sourceConfigs?: Record<string, unknown>[]
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
  /** 容器报告摘要（「查看报告」跳转 /report/:id 数据源；无报告时 null） */
  reports: { count: number; reports: { id: number; name: string | null }[] } | null
}

/** 可挑选任务（阶段 1 数据源，INT-1496 `GET /tasks/cherry-picks/pickable-tasks`）
 *  任务级聚合行：`count` = 该任务可挑结果行数（excluded=0），`executionStatus` 是**任务**状态。 */
export interface PickableTask {
  taskId: number
  taskName: string
  executionStatus: string
  createdAt: string | null
  count: number
}

/** 可挑选任务分页（`total` 为满足条件的任务总数，不受分页影响） */
export interface PickableTaskPage {
  items: PickableTask[]
  total: number
  page: number
  perPage: number
}

/** 可挑选任务排序键（服务端 sort_by 枚举，INT-1496 §8.1） */
export type PickableTaskSortBy = 'status' | 'name' | 'created_at'
export type PickableTaskSortOrder = 'asc' | 'desc'
