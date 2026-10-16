/**
 * 用例域领域模型（domain 层；10_测试执行.md §9 落位 + 11_用例域.md §3.3 表格版式）。
 * 形态对照 api_gateway/schemas/testcase.py TestCaseListItem/TestCaseConfig 实测：
 * id/name/description/group_id/group_name/type/tags/algorithm_type/total_duration/updated_at
 * + INT-141 收藏/回收站字段（is_favorite/deleted/deleted_at/deleted_by_user_id）。
 * 执行类型子集（选择场景列裁剪）；完整用例管理页列表项 = TestCaseListItem。
 */

export type TestCaseType = 'e2e' | 'api'

/** 用例列表项（选择场景所需子集） */
export interface TestCase {
  id: string
  name: string
  description: string | null
  groupId: string | null
  groupName: string | null
  /** 执行类型（api/e2e）；schema type 字段实测 */
  type: TestCaseType | null
  tags: string[]
  algorithmType: string | null
  /** 轮次数（由 config.rounds 长度派生；展示「{n} 轮」） */
  rounds: number
  /** 总时长（秒，total_duration 实测；展示「{x}m {y}s」） */
  totalDuration: number | null
  updatedAt: string | null
}

/**
 * 用例列表项（11_用例域.md §3.3 表格版式，schemas/testcase.py:122 TestCaseListItem 实测）。
 * tags 为名称串（schema List[str]）；标签分类/色值经 infrastructure/api/tags-api 登记表
 * （TagItem{categoryId,categoryName,color}，INT-487 按分类呈现口径）名称→属性映射，接线不改。
 */
export interface TestCaseListItem {
  id: string
  name: string
  description: string | null
  groupId: string | null
  groupName: string | null
  /** 执行类型（api/e2e；残留 test_type 列，待 INT-79 废弃——正式类型维度=algorithmType） */
  type: TestCaseType | null
  tags: string[]
  algorithmType: string | null
  createdAt: string | null
  updatedAt: string | null
  /** INT-141 收藏 / 回收站 */
  isFavorite: boolean | null
  deleted: boolean | null
  deletedAt: string | null
  deletedByUserId: number | null
  /** 总时长（秒；展示「{x}m {y}s」，0 不显） */
  totalDuration: number | null
  /** 轮次数（由 config.rounds 长度派生；展示「{n} 轮」） */
  rounds: number
}

/** 评估维度简报（testcase.py TestCaseDimensionBrief） */
export interface EvaluationDimension {
  id: number
  name: string
  type: string | null
}
